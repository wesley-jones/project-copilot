"""
Knowledge layer router — debug/inspection and ingestion trigger endpoints for Phase 0–1.

All endpoints are under /api/knowledge and return JSON.
No auth is applied (consistent with other API routers in this project).
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query

from backend.app.config import get_settings
from backend.app.schemas_knowledge import AppianIngestRequest, JiraIngestRequest, LocalDocsIngestRequest
from backend.app.services.graph.models import ArtifactKind, SourceSystem
from backend.app.services.knowledge_service import get_knowledge_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


def _svc():
    return get_knowledge_service()


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


@router.get("/health")
def knowledge_health():
    """Return a basic health response confirming the knowledge layer is reachable."""
    return {"status": "ok", "storage": "file-based", "layer": "knowledge", "phase": 0}


# ---------------------------------------------------------------------------
# Ingestion runs
# ---------------------------------------------------------------------------


@router.get("/runs")
def list_runs():
    """List all ingestion runs."""
    return [r.model_dump(mode="json") for r in _svc().list_runs()]


# ---------------------------------------------------------------------------
# Artifacts
# ---------------------------------------------------------------------------


@router.get("/artifacts")
def list_artifacts():
    """List all ingested artifacts."""
    return [r.model_dump(mode="json") for r in _svc().list_artifacts()]


@router.get("/artifacts/search")
def search_artifacts(
    project_key: str | None = Query(default=None),
    source_system: SourceSystem | None = Query(default=None),
    artifact_kind: ArtifactKind | None = Query(default=None),
    title_contains: str | None = Query(default=None),
):
    """Search artifacts by project_key, source_system, artifact_kind, and/or title substring."""
    results = _svc().search_artifacts(
        project_key=project_key,
        source_system=source_system,
        artifact_kind=artifact_kind,
        title_contains=title_contains,
    )
    return [r.model_dump(mode="json") for r in results]


@router.get("/artifacts/{artifact_id}")
def get_artifact(artifact_id: str):
    """Return a single artifact by ID, or 404 if not found."""
    record = _svc().get_artifact(artifact_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Artifact '{artifact_id}' not found.")
    return record.model_dump(mode="json")


# ---------------------------------------------------------------------------
# Chunks
# ---------------------------------------------------------------------------


@router.get("/chunks")
def list_chunks(artifact_id: str | None = None):
    """List chunks, optionally filtered to a single artifact_id query param."""
    return [r.model_dump(mode="json") for r in _svc().list_chunks(artifact_id=artifact_id)]


@router.post("/chunk/{artifact_id}")
def chunk_artifact(artifact_id: str):
    """Chunk a single artifact and return a summary."""
    try:
        chunks = _svc().chunk_artifact(artifact_id)
        return {
            "artifact_id": artifact_id,
            "chunk_count": len(chunks),
            "chunk_ids": [chunk.chunk_id for chunk in chunks[:10]],
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("chunk_artifact: %s", exc)
        raise HTTPException(status_code=500, detail=f"Chunking error: {exc}") from exc


@router.post("/chunk-all")
def chunk_all_artifacts():
    """Chunk all artifacts and return summary counters."""
    try:
        return _svc().chunk_all_artifacts()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("chunk_all_artifacts: %s", exc)
        raise HTTPException(status_code=500, detail=f"Chunking error: {exc}") from exc


@router.post("/index/rebuild")
def rebuild_index():
    """Rebuild the lexical chunk index and return basic stats."""
    try:
        return _svc().rebuild_index()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("rebuild_index: %s", exc)
        raise HTTPException(status_code=500, detail=f"Index rebuild error: {exc}") from exc


@router.get("/search")
def search_chunks(
    q: str = Query(...),
    project_key: str | None = Query(default=None),
    source_system: SourceSystem | None = Query(default=None),
    artifact_kind: ArtifactKind | None = Query(default=None),
    artifact_id: str | None = Query(default=None),
    limit: int | None = Query(default=None),
):
    """Search indexed chunks using the Phase 2 lexical retriever."""
    try:
        settings = get_settings()
        resolved_limit = limit if limit is not None else settings.knowledge_search_default_limit
        resolved_limit = max(1, min(resolved_limit, settings.knowledge_search_max_limit))
        return _svc().search_chunks(
            q=q,
            project_key=project_key,
            source_system=source_system,
            artifact_kind=artifact_kind,
            artifact_id=artifact_id,
            limit=resolved_limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("search_chunks: %s", exc)
        raise HTTPException(status_code=500, detail=f"Search error: {exc}") from exc


# ---------------------------------------------------------------------------
# Edges
# ---------------------------------------------------------------------------


@router.get("/edges")
def list_edges():
    """List all graph edges."""
    return [e.model_dump(mode="json") for e in _svc().list_edges()]


@router.post("/link/{artifact_id}")
def link_artifact(artifact_id: str):
    """Run rule-based linking for a single artifact and return summary counts."""
    try:
        return _svc().link_artifact(artifact_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("link_artifact: %s", exc)
        raise HTTPException(status_code=500, detail=f"Linking error: {exc}") from exc


@router.post("/link-all")
def link_all_artifacts():
    """Run rule-based linking across all artifacts and return summary counts."""
    try:
        return _svc().link_all_artifacts()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("link_all_artifacts: %s", exc)
        raise HTTPException(status_code=500, detail=f"Linking error: {exc}") from exc


@router.get("/related/{artifact_id}")
def related_artifacts(artifact_id: str, limit: int = Query(default=10)):
    """Return conservative related-artifact results for inspection/debugging."""
    try:
        return _svc().get_related_artifacts(artifact_id, limit=max(1, limit))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("related_artifacts: %s", exc)
        raise HTTPException(status_code=500, detail=f"Related artifact error: {exc}") from exc


@router.get("/entities/{artifact_id}")
def get_artifact_entities(artifact_id: str):
    """Return extracted artifact and chunk entities for inspection/debugging."""
    try:
        return _svc().get_artifact_entities(artifact_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("get_artifact_entities: %s", exc)
        raise HTTPException(status_code=500, detail=f"Entity extraction error: {exc}") from exc


# ---------------------------------------------------------------------------
# Bootstrap (dev only)
# ---------------------------------------------------------------------------


@router.get("/bootstrap")
def bootstrap():
    """Create deterministic sample records for Phase 0 local validation. Idempotent."""
    ids = _svc().bootstrap_sample_data()
    logger.info("knowledge bootstrap: created sample records %s", ids)
    return ids


# ---------------------------------------------------------------------------
# Ingestion triggers (Phase 1 — local dev only)
# ---------------------------------------------------------------------------


@router.post("/ingest/jira")
def ingest_jira(body: JiraIngestRequest):
    """Trigger a Jira ingestion run. Returns the completed IngestionRun as JSON."""
    try:
        run = _svc().run_jira_ingestion(
            project_key=body.project_key,
            jql=body.jql,
            max_results=body.max_results,
        )
        return run.model_dump(mode="json")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("ingest_jira: %s", exc)
        raise HTTPException(status_code=500, detail=f"Ingestion error: {exc}") from exc


@router.post("/ingest/local-docs")
def ingest_local_docs(body: LocalDocsIngestRequest):
    """Trigger a local document ingestion run. Returns the completed IngestionRun as JSON."""
    try:
        run = _svc().run_local_docs_ingestion(
            root_dir=body.root_dir,
            project_key=body.project_key,
            recursive=body.recursive,
        )
        return run.model_dump(mode="json")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("ingest_local_docs: %s", exc)
        raise HTTPException(status_code=500, detail=f"Ingestion error: {exc}") from exc


@router.post("/ingest/appian")
def ingest_appian(body: AppianIngestRequest):
    """Trigger an Appian XML/ZIP ingestion run. Returns the completed IngestionRun as JSON."""
    try:
        settings = get_settings()
        run = _svc().run_appian_ingestion(
            root_dir=body.root_dir,
            project_key=body.project_key,
            recursive=(
                body.recursive
                if body.recursive is not None
                else settings.knowledge_appian_extract_recursive
            ),
        )
        return run.model_dump(mode="json")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("ingest_appian: %s", exc)
        raise HTTPException(status_code=500, detail=f"Ingestion error: {exc}") from exc
