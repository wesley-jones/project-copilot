"""
Link pipeline - derives deterministic GraphEdge relationships between artifacts and chunks.
"""
from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING, Any

from backend.app.services.graph.linker import Linker

if TYPE_CHECKING:
    from backend.app.services.knowledge_service import KnowledgeService


class LinkPipeline:
    """Run the Phase 3 rule-based linker for one artifact or the full corpus."""

    def __init__(self, linker: Linker | None = None) -> None:
        self._linker = linker if linker is not None else Linker()

    def run(
        self,
        run_id: str,
        service: "KnowledgeService",
        artifact_id: str | None = None,
        **kwargs: Any,
    ) -> dict[str, int]:
        """Link one artifact or all artifacts and return summary counts."""
        if artifact_id:
            edges = self._linker.link_artifact(service, artifact_id, run_id=run_id)
            return {
                "artifacts_seen": 1,
                "artifacts_linked": 1,
                "edges_created": len(edges),
                "artifacts_failed": 0,
            }
        return self._linker.link_all(service, run_id=run_id)


@lru_cache
def get_link_pipeline() -> LinkPipeline:
    return LinkPipeline()
