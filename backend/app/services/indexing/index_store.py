"""Filesystem persistence for the Phase 2 lexical retrieval index."""
from __future__ import annotations

import json
import logging
from pathlib import Path

from backend.app.services.graph import paths
from backend.app.services.indexing.models import ArtifactChunkMap, ChunkIndexFile

logger = logging.getLogger(__name__)


class IndexStore:
    """Read/write lexical retrieval index JSON files under local_data/knowledge/indexes/."""

    def _ensure_dirs(self) -> None:
        paths.ensure_knowledge_dirs()

    @property
    def _chunks_index_path(self) -> Path:
        return paths.indexes_dir() / "chunks_index.json"

    @property
    def _artifact_chunk_map_path(self) -> Path:
        return paths.indexes_dir() / "artifact_chunk_map.json"

    def save(self, index: ChunkIndexFile, artifact_chunk_map: ArtifactChunkMap) -> None:
        """Persist the lexical index and artifact-chunk map atomically."""
        self._ensure_dirs()
        paths.atomic_write(self._chunks_index_path, index.model_dump_json(indent=2))
        paths.atomic_write(
            self._artifact_chunk_map_path,
            artifact_chunk_map.model_dump_json(indent=2),
        )

    def load_index(self) -> ChunkIndexFile:
        """Return the stored chunk index, or an empty index if missing or malformed."""
        if not self._chunks_index_path.exists():
            return ChunkIndexFile()
        try:
            return ChunkIndexFile(**json.loads(self._chunks_index_path.read_text(encoding="utf-8")))
        except Exception as exc:
            logger.warning("IndexStore: failed to load %s (%s)", self._chunks_index_path.name, exc)
            return ChunkIndexFile()

    def load_artifact_chunk_map(self) -> ArtifactChunkMap:
        """Return the stored artifact-chunk map, or an empty one if missing or malformed."""
        if not self._artifact_chunk_map_path.exists():
            return ArtifactChunkMap({})
        try:
            return ArtifactChunkMap(json.loads(self._artifact_chunk_map_path.read_text(encoding="utf-8")))
        except Exception as exc:
            logger.warning(
                "IndexStore: failed to load %s (%s)",
                self._artifact_chunk_map_path.name,
                exc,
            )
            return ArtifactChunkMap({})


def get_index_store() -> IndexStore:
    return IndexStore()
