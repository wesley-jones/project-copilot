"""
File-based store for GraphEdge objects.

Storage: local_data/knowledge/edges/{edge_id}.json
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from backend.app.services.graph import paths
from backend.app.services.graph.models import GraphEdge

logger = logging.getLogger(__name__)


class EdgeStore:
    """Read/write GraphEdge objects to the local filesystem."""

    def _ensure_dirs(self) -> None:
        paths.ensure_knowledge_dirs()

    @property
    def _dir(self) -> Path:
        return paths.edges_dir()

    def save(self, edge: GraphEdge) -> None:
        """Persist *edge* to disk, overwriting any existing file for that edge_id."""
        self._ensure_dirs()
        path = self._dir / f"{edge.edge_id}.json"
        paths.atomic_write(path, edge.model_dump_json(indent=2))
        logger.debug("EdgeStore: saved %s", edge.edge_id)

    def get(self, edge_id: str) -> GraphEdge | None:
        """Return the GraphEdge for *edge_id*, or None if not found."""
        path = self._dir / f"{edge_id}.json"
        if not path.exists():
            return None
        try:
            return GraphEdge(**json.loads(path.read_text(encoding="utf-8")))
        except Exception as exc:
            logger.warning("EdgeStore: failed to load %s (%s)", edge_id, exc)
            return None

    def list_all(self) -> list[GraphEdge]:
        """Return all stored GraphEdges, sorted by edge_id. Skips malformed files."""
        self._ensure_dirs()
        edges: list[GraphEdge] = []
        for p in sorted(self._dir.glob("*.json")):
            try:
                edges.append(GraphEdge(**json.loads(p.read_text(encoding="utf-8"))))
            except Exception as exc:
                logger.warning("EdgeStore: skipping malformed file %s (%s)", p.name, exc)
        return edges

    def delete_by_artifact(self, artifact_id: str) -> int:
        """Delete edges touching *artifact_id* or its deterministic chunk IDs."""
        removed = 0
        chunk_prefix = f"{artifact_id}-chunk-"
        for edge in self.list_all():
            if not (
                edge.from_id == artifact_id
                or edge.to_id == artifact_id
                or edge.from_id.startswith(chunk_prefix)
                or edge.to_id.startswith(chunk_prefix)
            ):
                continue
            path = self._dir / f"{edge.edge_id}.json"
            try:
                if path.exists():
                    path.unlink()
                    removed += 1
            except Exception as exc:
                logger.warning("EdgeStore: failed to delete %s (%s)", path.name, exc)
        return removed


def get_edge_store() -> EdgeStore:
    return EdgeStore()
