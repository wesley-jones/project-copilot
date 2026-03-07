"""
Power Mode router — project discovery + SSE streaming agent run.
"""
from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from backend.app.schemas import PowerDiscoverRequest, PowerDiscoverResponse, PowerRunRequest
from backend.app.services.jira_client import JiraError
from backend.app.services.power_agent import get_power_agent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/power", tags=["Power"])


@router.post("/discover", response_model=PowerDiscoverResponse)
async def power_discover(req: PowerDiscoverRequest) -> PowerDiscoverResponse:
    """Run project-scoped discovery and store normalized context in the session workspace."""
    agent = get_power_agent()
    try:
        return agent.discover_project(req.session_id)
    except JiraError as exc:
        raise HTTPException(status_code=exc.status_code or 502, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("power_discover unexpected error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


async def _event_generator(session_id: str, goal: str):
    """Bridge sync PowerAgent generator to async SSE stream via asyncio.Queue."""
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def _run() -> None:
        agent = get_power_agent()
        try:
            for event in agent.run(session_id, goal):
                loop.call_soon_threadsafe(queue.put_nowait, event)
        except Exception as exc:
            logger.exception("PowerAgent run error: %s", exc)
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)  # sentinel

    loop.run_in_executor(None, _run)

    while True:
        event = await queue.get()
        if event is None:
            break
        yield f"data: {json.dumps(event.model_dump(exclude_none=True))}\n\n"


@router.post("/run")
async def power_run(req: PowerRunRequest) -> StreamingResponse:
    """Stream agent step events as Server-Sent Events."""
    return StreamingResponse(
        _event_generator(req.session_id, req.goal),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
