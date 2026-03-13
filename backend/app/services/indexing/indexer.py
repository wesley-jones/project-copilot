"""Build and persist a lightweight lexical index over stored ChunkRecords."""
from __future__ import annotations

from collections import Counter
from functools import lru_cache
import logging
from typing import TYPE_CHECKING

from backend.app.services.graph.models import ArtifactRecord, ChunkRecord
from backend.app.services.indexing.index_store import IndexStore, get_index_store
from backend.app.services.indexing.models import (
    ArtifactChunkMap,
    ChunkIndexFile,
    ChunkIndexStats,
    IndexedChunk,
    TokenPosting,
)
from backend.app.services.indexing.tokenizer import Tokenizer, get_tokenizer

if TYPE_CHECKING:
    from backend.app.services.knowledge_service import KnowledgeService

logger = logging.getLogger(__name__)


class Indexer:
    """Build the JSON-backed lexical retrieval index.

    The MVP implementation keeps `index_chunks()` honest by rebuilding the full
    index when a KnowledgeService instance is provided.
    """

    def __init__(self, store: IndexStore | None = None, tokenizer: Tokenizer | None = None) -> None:
        self._store = store if store is not None else get_index_store()
        self._tokenizer = tokenizer if tokenizer is not None else get_tokenizer()

    def rebuild(self, service: "KnowledgeService") -> dict[str, int]:
        """Rebuild the full lexical index from all currently stored chunks."""
        chunks = sorted(
            service.list_chunks(),
            key=lambda chunk: (chunk.artifact_id, chunk.chunk_index, chunk.chunk_id),
        )
        artifacts = {artifact.metadata.artifact_id: artifact for artifact in service.list_artifacts()}
        return self._build_and_save(chunks, artifacts)

    def index_chunks(
        self,
        chunks: list[ChunkRecord],
        service: "KnowledgeService" | None = None,
    ) -> dict[str, int]:
        """Index provided chunks.

        When *service* is provided, the MVP implementation rebuilds the full
        index to keep replacement and deletion behavior correct.
        """
        if service is not None:
            return self.rebuild(service)
        return self._build_and_save(chunks, {})

    def _build_and_save(
        self,
        chunks: list[ChunkRecord],
        artifacts: dict[str, ArtifactRecord],
    ) -> dict[str, int]:
        token_map: dict[str, list[TokenPosting]] = {}
        chunk_map: dict[str, IndexedChunk] = {}
        artifact_chunk_map: dict[str, list[str]] = {}
        artifact_ids: set[str] = set()

        for chunk in sorted(chunks, key=lambda item: (item.artifact_id, item.chunk_index, item.chunk_id)):
            artifact = artifacts.get(chunk.artifact_id)
            if artifacts and artifact is None:
                logger.warning("Indexer: skipping orphan chunk %s", chunk.chunk_id)
                continue

            metadata = artifact.metadata if artifact is not None else None
            chunk_map[chunk.chunk_id] = IndexedChunk(
                chunk_id=chunk.chunk_id,
                artifact_id=chunk.artifact_id,
                chunk_index=chunk.chunk_index,
                section_title=chunk.section_title,
                text=chunk.text,
                artifact_title=metadata.title if metadata is not None else chunk.artifact_id,
                project_key=metadata.project_key if metadata is not None else None,
                source_system=metadata.source_system.value if metadata is not None else "unknown",
                artifact_kind=metadata.artifact_kind.value if metadata is not None else "unknown",
                url=metadata.url if metadata is not None else None,
            )
            artifact_chunk_map.setdefault(chunk.artifact_id, []).append(chunk.chunk_id)
            artifact_ids.add(chunk.artifact_id)

            frequencies = Counter(self._tokenizer.tokenize(chunk.text))
            for token, frequency in sorted(frequencies.items()):
                token_map.setdefault(token, []).append(
                    TokenPosting(
                        chunk_id=chunk.chunk_id,
                        artifact_id=chunk.artifact_id,
                        term_frequency=frequency,
                    )
                )

        sorted_token_map = {
            token: sorted(postings, key=lambda posting: (posting.artifact_id, posting.chunk_id))
            for token, postings in sorted(token_map.items())
        }
        sorted_chunk_map = dict(sorted(chunk_map.items()))
        sorted_artifact_chunk_map = ArtifactChunkMap(
            {artifact_id: chunk_ids for artifact_id, chunk_ids in sorted(artifact_chunk_map.items())}
        )
        index = ChunkIndexFile(
            tokens=sorted_token_map,
            chunks=sorted_chunk_map,
            stats=ChunkIndexStats(
                chunks_indexed=len(sorted_chunk_map),
                artifacts_indexed=len(artifact_ids),
                unique_terms=len(sorted_token_map),
            ),
        )
        self._store.save(index, sorted_artifact_chunk_map)
        return index.stats.model_dump()


@lru_cache
def get_indexer() -> Indexer:
    return Indexer()
