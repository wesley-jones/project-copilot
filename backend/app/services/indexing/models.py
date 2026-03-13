"""Pydantic models for the lightweight lexical index."""
from __future__ import annotations

from pydantic import BaseModel, Field, RootModel


class TokenPosting(BaseModel):
    """Posting entry for a token in the inverted chunk index."""

    chunk_id: str
    artifact_id: str
    term_frequency: int = Field(ge=1)


class IndexedChunk(BaseModel):
    """Chunk metadata persisted for retrieval and result reconstruction."""

    chunk_id: str
    artifact_id: str
    chunk_index: int
    section_title: str | None = None
    text: str
    artifact_title: str
    project_key: str | None = None
    source_system: str
    artifact_kind: str
    url: str | None = None


class ChunkIndexStats(BaseModel):
    """Simple counters describing the current lexical index."""

    chunks_indexed: int = 0
    artifacts_indexed: int = 0
    unique_terms: int = 0


class ChunkIndexFile(BaseModel):
    """Persisted lexical index for chunk retrieval."""

    tokens: dict[str, list[TokenPosting]] = Field(default_factory=dict)
    chunks: dict[str, IndexedChunk] = Field(default_factory=dict)
    stats: ChunkIndexStats = Field(default_factory=ChunkIndexStats)


class ArtifactChunkMap(RootModel[dict[str, list[str]]]):
    """Mapping of artifact IDs to deterministic ordered chunk IDs."""
