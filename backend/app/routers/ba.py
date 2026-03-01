from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from backend.app.schemas import (
    DocUploadResponse,
    ReadinessResponse,
    RequirementsGenerateRequest,
    RequirementsResponse,
    RequirementsUpdateRequest,
    StoriesGenerateRequest,
    StoriesResponse,
    StoriesUpdateRequest,
)
from backend.app.services.ba_agent import BAAgent
from backend.app.services.document_store import DocumentStore, get_document_store
from backend.app.services.llm_client import LLMError, get_llm_client
from backend.app.services.prompt_loader import get_prompt_loader

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/ba", tags=["BA"])


def _agent(store: DocumentStore = Depends(get_document_store)) -> BAAgent:
    return BAAgent(
        llm=get_llm_client(),
        prompt_loader=get_prompt_loader(),
        store=store,
    )


def _handle_error(exc: Exception) -> HTTPException:
    if isinstance(exc, LLMError):
        return HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    logger.exception("Unexpected error in BA router")
    return HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal error")


# ---------------------------------------------------------------------------
# Requirements
# ---------------------------------------------------------------------------


@router.post("/requirements/generate", response_model=RequirementsResponse)
async def generate_requirements(
    req: RequirementsGenerateRequest,
    agent: BAAgent = Depends(_agent),
) -> RequirementsResponse:
    try:
        return agent.generate_requirements(req.session_id, req.raw_notes)
    except Exception as exc:
        raise _handle_error(exc) from exc


@router.post("/requirements/update", response_model=RequirementsResponse)
async def update_requirements(
    req: RequirementsUpdateRequest,
    agent: BAAgent = Depends(_agent),
) -> RequirementsResponse:
    try:
        return agent.update_requirements(req.session_id, req.edit_instruction)
    except Exception as exc:
        raise _handle_error(exc) from exc


# ---------------------------------------------------------------------------
# Stories
# ---------------------------------------------------------------------------


@router.post("/stories/generate", response_model=StoriesResponse)
async def generate_stories(
    req: StoriesGenerateRequest,
    agent: BAAgent = Depends(_agent),
) -> StoriesResponse:
    try:
        return agent.generate_stories(req.session_id)
    except Exception as exc:
        raise _handle_error(exc) from exc


@router.post("/stories/update", response_model=StoriesResponse)
async def update_stories(
    req: StoriesUpdateRequest,
    agent: BAAgent = Depends(_agent),
) -> StoriesResponse:
    try:
        return agent.update_stories(req.session_id, req.edit_instruction)
    except Exception as exc:
        raise _handle_error(exc) from exc


# ---------------------------------------------------------------------------
# Readiness
# ---------------------------------------------------------------------------


@router.post("/readiness/check", response_model=ReadinessResponse)
async def check_readiness(
    req: StoriesGenerateRequest,  # reuse — just needs session_id
    agent: BAAgent = Depends(_agent),
) -> ReadinessResponse:
    try:
        return agent.check_readiness(req.session_id)
    except Exception as exc:
        raise _handle_error(exc) from exc


# ---------------------------------------------------------------------------
# Document upload
# ---------------------------------------------------------------------------


@router.post("/docs/upload", response_model=DocUploadResponse)
async def upload_doc(
    session_id: str = Form(...),
    file: UploadFile = File(...),
    store: DocumentStore = Depends(get_document_store),
) -> DocUploadResponse:
    allowed = {".txt", ".md"}
    import os
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in allowed:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Only {allowed} files are supported in Phase 1.",
        )
    content = await file.read()
    filename = store.save_doc(session_id, file.filename or "upload.txt", content)
    ws = store.load_workspace(session_id)
    if filename not in ws.uploaded_docs:
        ws.uploaded_docs.append(filename)
    store.save_workspace(ws)
    return DocUploadResponse(
        session_id=session_id,
        filename=filename,
        message=f"Uploaded {filename} successfully.",
    )
