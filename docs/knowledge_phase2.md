# Knowledge Layer - Phase 2

Phase 2 adds deterministic chunking, a lightweight lexical index, and chunk-level retrieval
on top of the Phase 0/1 file-based knowledge layer.

No vector database, embeddings, or LLM-driven inference are introduced in this phase.

---

## What Phase 2 Adds

| Component | Purpose |
|-----------|---------|
| `services/chunking/chunker.py` | Deterministic text chunking for `ArtifactRecord.text_content` |
| `pipelines/chunk_pipeline.py` | Real chunking pipeline replacing the Phase 0 stub |
| `services/indexing/tokenizer.py` | Stable lexical tokenization and keyword extraction |
| `services/indexing/indexer.py` | Rebuilds the lexical chunk index from stored chunks |
| `services/indexing/retriever.py` | Ranked lexical retrieval over indexed chunks |
| `services/indexing/index_store.py` | JSON persistence under `local_data/knowledge/indexes/` |
| `routers/knowledge.py` | Debug endpoints for chunking, index rebuild, and lexical search |

---

## Chunking Strategy

- Artifact text is normalized to LF line endings and trimmed.
- Chunking prefers markdown heading sections first.
- If headings are not present, chunking falls back to paragraph blocks.
- Oversized sections are split into overlapping character windows.
- Chunk IDs are deterministic: `<artifact_id>-chunk-<zero-padded-index>`.
- Re-chunking deletes prior chunks for the artifact before saving replacements.

Chunk metadata includes:
- `chunk_type`
- `token_estimate`
- `section_title`
- `keywords`
- `entities` as an empty list for now
- `extra.char_start`, `extra.char_end`, and `extra.truncated`

---

## Tokenizer and Indexing Strategy

- Tokenization splits on non-word boundaries.
- Tokens are lowercased by default unless `KNOWLEDGE_INDEX_CASE_SENSITIVE=true`.
- Very short tokens and a small stopword list are removed.
- The lexical index is stored at:
  - `local_data/knowledge/indexes/chunks_index.json`
  - `local_data/knowledge/indexes/artifact_chunk_map.json`
- The MVP may rebuild the full index after chunk ingestion instead of doing partial updates.

---

## Endpoint Usage

### Chunk one artifact

```bash
curl -X POST http://localhost:8000/api/knowledge/chunk/local-req-001
```

### Chunk all artifacts

```bash
curl -X POST http://localhost:8000/api/knowledge/chunk-all
```

### Rebuild the lexical index

```bash
curl -X POST http://localhost:8000/api/knowledge/index/rebuild
```

### Search indexed chunks

```bash
curl "http://localhost:8000/api/knowledge/search?q=requirement"
curl "http://localhost:8000/api/knowledge/search?q=login&source_system=jira&limit=10"
```

---

## How To Test Locally

### 1. Start the server

```bash
uvicorn backend.app.main:app --reload
```

### 2. Ingest sample artifacts

```bash
curl -X POST http://localhost:8000/api/knowledge/ingest/local-docs -H "Content-Type: application/json" -d '{}'
curl -X POST http://localhost:8000/api/knowledge/ingest/jira -H "Content-Type: application/json" -d '{"max_results": 5}'
```

### 3. Chunk and index

```bash
curl -X POST http://localhost:8000/api/knowledge/chunk-all
curl -X POST http://localhost:8000/api/knowledge/index/rebuild
```

### 4. Search chunks

```bash
curl "http://localhost:8000/api/knowledge/search?q=requirement"
```

### 5. Verify files on disk

```bash
ls local_data/knowledge/chunks/
ls local_data/knowledge/indexes/
```

---

## Deferred To Later Phases

- Embeddings and vector search
- Semantic reranking
- Entity extraction and graph linking
- Similarity-based edges
- External search engines or database-backed indexing
