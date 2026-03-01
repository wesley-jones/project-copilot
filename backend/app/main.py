"""
Project Delivery Copilot — Phase 1 MVP
FastAPI application with Jinja2 server-rendered UI.
"""
from __future__ import annotations

import logging
import os
import uuid
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from backend.app.config import get_settings
from backend.app.routers import ba, jira, pm
from backend.app.services.ba_agent import BAAgent
from backend.app.services.document_store import get_document_store
from backend.app.services.jira_client import get_jira_client
from backend.app.services.llm_client import LLMError, get_llm_client
from backend.app.services.pm_agent import PMAgent
from backend.app.services.prompt_loader import get_prompt_loader

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# App & static assets
# ---------------------------------------------------------------------------
settings = get_settings()

app = FastAPI(title="Project Delivery Copilot", version="1.0.0")

_base = Path(__file__).resolve().parent.parent.parent  # repo root

app.mount(
    "/static",
    StaticFiles(directory=str(_base / "frontend" / "static")),
    name="static",
)

templates = Jinja2Templates(directory=str(_base / "frontend" / "templates"))

# ---------------------------------------------------------------------------
# API routers
# ---------------------------------------------------------------------------
app.include_router(ba.router)
app.include_router(pm.router)
app.include_router(jira.router)

# ---------------------------------------------------------------------------
# UI helpers
# ---------------------------------------------------------------------------


def _new_sid() -> str:
    return uuid.uuid4().hex


def _get_or_create_session(request: Request) -> str:
    sid = request.cookies.get("session_id")
    if not sid:
        sid = _new_sid()
    return sid


def _set_session(response, sid: str):
    response.set_cookie("session_id", sid, httponly=True)
    return response


# ---------------------------------------------------------------------------
# UI pages
# ---------------------------------------------------------------------------


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    sid = _get_or_create_session(request)
    store = get_document_store()
    ws = store.load_workspace(sid)
    response = templates.TemplateResponse(
        "index.html",
        {"request": request, "session_id": sid, "workspace": ws},
    )
    response.set_cookie("session_id", sid, httponly=True)
    return response


@app.get("/ba/requirements", response_class=HTMLResponse)
async def ba_requirements_page(request: Request):
    sid = _get_or_create_session(request)
    store = get_document_store()
    ws = store.load_workspace(sid)
    response = templates.TemplateResponse(
        "ba_requirements.html",
        {"request": request, "session_id": sid, "workspace": ws, "result": None, "error": None},
    )
    response.set_cookie("session_id", sid, httponly=True)
    return response


@app.post("/ba/requirements", response_class=HTMLResponse)
async def ba_requirements_post(
    request: Request,
    action: str = Form(...),
    session_id: str = Form(...),
    raw_notes: str = Form(""),
    edit_instruction: str = Form(""),
):
    store = get_document_store()
    agent = BAAgent(llm=get_llm_client(), prompt_loader=get_prompt_loader(), store=store)
    result = None
    error = None
    try:
        if action == "generate":
            result = agent.generate_requirements(session_id, raw_notes)
        elif action == "update":
            result = agent.update_requirements(session_id, edit_instruction)
    except (LLMError, ValueError, FileNotFoundError) as exc:
        error = str(exc)

    ws = store.load_workspace(session_id)
    response = templates.TemplateResponse(
        "ba_requirements.html",
        {
            "request": request,
            "session_id": session_id,
            "workspace": ws,
            "result": result,
            "error": error,
            "submitted_raw_notes": raw_notes,
        },
    )
    response.set_cookie("session_id", session_id, httponly=True)
    return response


@app.get("/ba/stories", response_class=HTMLResponse)
async def ba_stories_page(request: Request):
    sid = _get_or_create_session(request)
    store = get_document_store()
    ws = store.load_workspace(sid)
    response = templates.TemplateResponse(
        "story_set.html",
        {"request": request, "session_id": sid, "workspace": ws, "result": None, "error": None},
    )
    response.set_cookie("session_id", sid, httponly=True)
    return response


@app.post("/ba/stories", response_class=HTMLResponse)
async def ba_stories_post(
    request: Request,
    action: str = Form(...),
    session_id: str = Form(...),
    edit_instruction: str = Form(""),
):
    store = get_document_store()
    agent = BAAgent(llm=get_llm_client(), prompt_loader=get_prompt_loader(), store=store)
    result = None
    error = None
    try:
        if action == "generate":
            result = agent.generate_stories(session_id)
        elif action == "update":
            result = agent.update_stories(session_id, edit_instruction)
    except (LLMError, ValueError, FileNotFoundError) as exc:
        error = str(exc)

    ws = store.load_workspace(session_id)
    response = templates.TemplateResponse(
        "story_set.html",
        {
            "request": request,
            "session_id": session_id,
            "workspace": ws,
            "result": result,
            "error": error,
        },
    )
    response.set_cookie("session_id", session_id, httponly=True)
    return response


@app.get("/ba/readiness", response_class=HTMLResponse)
async def ba_readiness_page(request: Request):
    sid = _get_or_create_session(request)
    store = get_document_store()
    ws = store.load_workspace(sid)
    response = templates.TemplateResponse(
        "readiness.html",
        {"request": request, "session_id": sid, "workspace": ws, "result": None, "jira_result": None, "error": None},
    )
    response.set_cookie("session_id", sid, httponly=True)
    return response


@app.post("/ba/readiness", response_class=HTMLResponse)
async def ba_readiness_post(
    request: Request,
    action: str = Form(...),
    session_id: str = Form(...),
    dry_run: str = Form("true"),
):
    store = get_document_store()
    agent = BAAgent(llm=get_llm_client(), prompt_loader=get_prompt_loader(), store=store)
    result = None
    jira_result = None
    error = None
    try:
        if action == "check":
            result = agent.check_readiness(session_id)
        elif action in ("jira_dry", "jira_create"):
            from backend.app.schemas import JiraCreateRequest
            from backend.app.routers.jira import create_story_set
            is_dry = action == "jira_dry"
            req = JiraCreateRequest(session_id=session_id, dry_run=is_dry)
            jira_result = await create_story_set(req, store=store, jira=get_jira_client())
    except (LLMError, ValueError, FileNotFoundError) as exc:
        error = str(exc)
    except HTTPException as exc:
        error = exc.detail

    ws = store.load_workspace(session_id)
    response = templates.TemplateResponse(
        "readiness.html",
        {
            "request": request,
            "session_id": session_id,
            "workspace": ws,
            "result": result,
            "jira_result": jira_result,
            "error": error,
        },
    )
    response.set_cookie("session_id", session_id, httponly=True)
    return response


@app.post("/ba/docs/upload", response_class=HTMLResponse)
async def ba_docs_upload_ui(
    request: Request,
    session_id: str = Form(...),
    file: UploadFile = File(...),
):
    import os
    store = get_document_store()
    error = None
    message = None
    allowed = {".txt", ".md"}
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in allowed:
        error = f"Only {allowed} files are supported."
    else:
        content = await file.read()
        filename = store.save_doc(session_id, file.filename or "upload.txt", content)
        ws = store.load_workspace(session_id)
        if filename not in ws.uploaded_docs:
            ws.uploaded_docs.append(filename)
        store.save_workspace(ws)
        message = f"Uploaded {filename} successfully."

    ws = store.load_workspace(session_id)
    response = templates.TemplateResponse(
        "ba_requirements.html",
        {
            "request": request,
            "session_id": session_id,
            "workspace": ws,
            "result": None,
            "error": error,
            "upload_message": message,
        },
    )
    response.set_cookie("session_id", session_id, httponly=True)
    return response


@app.get("/pm", response_class=HTMLResponse)
async def pm_page(request: Request):
    sid = _get_or_create_session(request)
    store = get_document_store()
    ws = store.load_workspace(sid)
    response = templates.TemplateResponse(
        "pm_mode.html",
        {"request": request, "session_id": sid, "workspace": ws, "result": None, "error": None},
    )
    response.set_cookie("session_id", sid, httponly=True)
    return response


@app.post("/pm", response_class=HTMLResponse)
async def pm_post(
    request: Request,
    session_id: str = Form(...),
    query: str = Form(...),
):
    pm_agent = PMAgent(
        llm=get_llm_client(),
        prompt_loader=get_prompt_loader(),
        jira=get_jira_client(),
    )
    result = None
    error = None
    try:
        result = pm_agent.query(session_id, query)
    except (LLMError, ValueError, FileNotFoundError) as exc:
        error = str(exc)
    except Exception as exc:
        error = f"Unexpected error: {exc}"

    store = get_document_store()
    ws = store.load_workspace(session_id)
    response = templates.TemplateResponse(
        "pm_mode.html",
        {
            "request": request,
            "session_id": session_id,
            "workspace": ws,
            "result": result,
            "error": error,
        },
    )
    response.set_cookie("session_id", session_id, httponly=True)
    return response


# ---------------------------------------------------------------------------
# Global exception handler
# ---------------------------------------------------------------------------


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception: %s", exc)
    return templates.TemplateResponse(
        "error.html",
        {"request": request, "detail": str(exc)},
        status_code=500,
    )
