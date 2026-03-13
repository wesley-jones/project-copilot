"""
Chunk pipeline - splits ArtifactRecord text into ChunkRecords and refreshes the index.
"""
from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING, Any

from backend.app.config import get_settings
from backend.app.services.graph.models import ChunkRecord
from backend.app.services.chunking import get_chunker

if TYPE_CHECKING:
    from backend.app.services.knowledge_service import KnowledgeService


class ChunkPipeline:
    """Chunk one artifact and persist the resulting ChunkRecords."""

    def run(
        self,
        run_id: str,
        artifact_id: str,
        service: "KnowledgeService",
        **kwargs: Any,
    ) -> list[ChunkRecord]:
        """Chunk the artifact identified by *artifact_id* and return saved chunks."""
        artifact = service.get_artifact(artifact_id)
        if artifact is None:
            raise ValueError(f"Artifact '{artifact_id}' not found.")

        rebuild_index = kwargs.get("rebuild_index")
        if rebuild_index is None:
            rebuild_index = get_settings().knowledge_rebuild_index_on_chunk_ingest

        service.delete_chunks_by_artifact(artifact_id)
        chunks = get_chunker().chunk_artifact(artifact)
        for chunk in chunks:
            chunk.extra["run_id"] = run_id
            service.save_chunk(chunk)

        if rebuild_index:
            from backend.app.services.indexing import get_indexer

            get_indexer().rebuild(service)

        return chunks


@lru_cache
def get_chunk_pipeline() -> ChunkPipeline:
    return ChunkPipeline()
