"""
File-based session workspace storage.

Each session lives in:  local_data/<session_id>/
Files inside:
  - workspace.json   — SessionWorkspace fields (sans uploaded_docs content)
  - docs/<filename>  — uploaded supporting documents
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from backend.app.config import get_settings
from backend.app.schemas import SessionWorkspace

logger = logging.getLogger(__name__)


class DocumentStore:
    def __init__(self) -> None:
        self._settings = get_settings()

    def _session_dir(self, session_id: str) -> Path:
        d = self._settings.local_data_dir / session_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _docs_dir(self, session_id: str) -> Path:
        d = self._session_dir(session_id) / "docs"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _workspace_path(self, session_id: str) -> Path:
        return self._session_dir(session_id) / "workspace.json"

    # ------------------------------------------------------------------
    # Workspace CRUD
    # ------------------------------------------------------------------

    def load_workspace(self, session_id: str) -> SessionWorkspace:
        path = self._workspace_path(session_id)
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            return SessionWorkspace(**data)
        return SessionWorkspace(session_id=session_id)

    def save_workspace(self, workspace: SessionWorkspace) -> None:
        path = self._workspace_path(workspace.session_id)
        path.write_text(workspace.model_dump_json(indent=2), encoding="utf-8")
        logger.debug("Saved workspace for session %s", workspace.session_id)

    # ------------------------------------------------------------------
    # Document upload
    # ------------------------------------------------------------------

    def save_doc(self, session_id: str, filename: str, content: bytes) -> str:
        """Save an uploaded document. Returns the stored filename."""
        # Sanitize filename
        safe_name = Path(filename).name
        dest = self._docs_dir(session_id) / safe_name
        dest.write_bytes(content)
        logger.debug("Saved doc %s for session %s", safe_name, session_id)
        return safe_name

    def load_all_docs_text(self, session_id: str) -> str:
        """Return concatenated text content of all uploaded docs."""
        docs_dir = self._docs_dir(session_id)
        parts: list[str] = []
        for f in sorted(docs_dir.iterdir()):
            if f.suffix.lower() in (".txt", ".md"):
                parts.append(f"--- Document: {f.name} ---\n" + f.read_text(encoding="utf-8", errors="replace"))
            else:
                logger.debug("Skipping unsupported doc format: %s", f.name)
        return "\n\n".join(parts)

    def list_docs(self, session_id: str) -> list[str]:
        docs_dir = self._docs_dir(session_id)
        if not docs_dir.exists():
            return []
        return [f.name for f in sorted(docs_dir.iterdir())]


def get_document_store() -> DocumentStore:
    return DocumentStore()
