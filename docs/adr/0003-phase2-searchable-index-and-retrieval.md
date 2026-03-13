# ADR 0003 - Phase 2: Searchable Index and Retrieval

## Status

Accepted

## Context

Phase 1 established repeatable ingestion into `ArtifactRecord` objects, but retrieval is
still limited to artifact-level metadata filtering. Before semantic retrieval or graph
linking can be introduced, DIP needs a lightweight, local-first way to chunk artifact text,
index it, and retrieve relevant chunks by query text.

## Decisions

### D1: Introduce chunk-level retrieval before semantic search

Phase 2 chunks artifact text into deterministic `ChunkRecord` objects and retrieves at the
chunk level. This improves precision without introducing embeddings or external services.

### D2: Use a file-based lexical inverted index

The MVP stores a JSON-backed inverted index under `local_data/knowledge/indexes/`. This
keeps infrastructure requirements aligned with the Phase 0/1 file-based architecture.

### D3: Re-chunking replaces prior chunks for an artifact

Chunk IDs are deterministic (`<artifact_id>-chunk-<zero-padded-index>`). Before re-saving,
existing chunks for the artifact are deleted so stale extra chunks do not remain on disk.

### D4: Full index rebuilds are acceptable in the MVP

To keep indexing logic safe and honest, chunk-triggered indexing may rebuild the full index
instead of performing partial in-place updates. This is sufficient for local development and
small datasets.

### D5: Lexical scoring only

Ranking is based on lexical signals such as term frequency, unique matched terms, and a small
artifact-title bonus. Embeddings, semantic reranking, and graph-based retrieval remain deferred.

## Consequences

**Positive:**
- No new infrastructure dependencies are introduced.
- Chunking and retrieval remain deterministic and inspectable on disk.
- The index format is simple enough for local debugging and later migration.

**Negative / deferred:**
- Full rebuild indexing will not scale indefinitely.
- Retrieval quality is bounded by lexical matching.
- Entity extraction, embeddings, and semantic retrieval are intentionally deferred.
