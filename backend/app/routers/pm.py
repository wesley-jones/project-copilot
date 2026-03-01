from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from backend.app.schemas import PMQueryRequest, PMQueryResponse
from backend.app.services.jira_client import JiraError, get_jira_client
from backend.app.services.llm_client import LLMError, get_llm_client
from backend.app.services.pm_agent import PMAgent
from backend.app.services.prompt_loader import get_prompt_loader

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/pm", tags=["PM"])


def _agent() -> PMAgent:
    return PMAgent(
        llm=get_llm_client(),
        prompt_loader=get_prompt_loader(),
        jira=get_jira_client(),
    )


@router.post("/jira/query", response_model=PMQueryResponse)
async def pm_jira_query(
    req: PMQueryRequest,
    agent: PMAgent = Depends(_agent),
) -> PMQueryResponse:
    try:
        return agent.query(req.session_id, req.query)
    except LLMError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except JiraError as exc:
        code = exc.status_code or 502
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Unexpected error in PM router")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal error") from exc
