# Knowledge Layer - Phase 3

Phase 3 adds the first graph-aware layer to DIP along with baseline Appian export ingestion.

This phase is intentionally rule-based and conservative:
- no semantic graph reasoning
- no graph database
- no embeddings or vector search
- no advanced Appian semantic reconstruction

---

## What Phase 3 Adds

| Component | Purpose |
|-----------|---------|
| `services/parsers/xml_parser.py` | Baseline XML parsing for Appian exports |
| `services/ingestion/appian_ingestor.py` | Ingest Appian XML files and ZIP exports into `ArtifactRecord`s |
| `services/graph/entity_extractor.py` | Heuristic entity/reference extraction |
| `services/graph/linker.py` | Rule-based `GraphEdge` generation |
| `services/graph/related.py` | Related-artifact inspection helper |
| `services/pipelines/link_pipeline.py` | Real Phase 3 link pipeline |
| `routers/knowledge.py` | Debug endpoints for Appian ingestion, linking, related artifacts, and entities |

---

## Appian Ingestion Behavior

- Supports standalone `.xml` files and `.zip` packages containing XML members.
- Uses stdlib XML parsing only.
- Produces one normalized `ArtifactRecord` per meaningful XML document/member.
- Normalization is conservative:
  - `source_system = appian`
  - `source_type = xml`
  - `artifact_kind` guessed from tags, filenames, and object names
  - `text_content` is a flattened, readable representation of the XML
  - `extra` includes root tag, guessed object type, extracted refs, identifiers, and ZIP-member context

### Raw Capture Tradeoff

- Standalone XML files are copied into `local_data/knowledge/raw/appian/<run_id>/`.
- ZIP inputs are copied once.
- ZIP-member artifacts point back to the copied ZIP using `raw_ref#member=...`.
- Phase 3 does not store every ZIP member as a separate raw file.

---

## Entity Extraction Heuristics

Entity extraction is deterministic and rule-based. It looks for:
- Jira keys such as `ABC-123`
- snake_case, camelCase, and SCREAMING_SNAKE tokens
- capitalized multi-word business terms
- XML/Appian-like identifiers and names

This is not full semantic NER. It is meant to support conservative linking and debug inspection.

---

## Linking Strategy

Phase 3 creates deterministic, explainable edges such as:
- `contains` for artifact -> chunk
- `references_artifact` for explicit Jira key references
- `same_project` for shared project key
- `related_to` for conservative keyword overlap
- `mentions` for obvious entity/title or entity/id matches
- `uses_object` / `calls` for matched Appian object references
- `same_appian_package` for Appian artifacts that came from the same ZIP package

Edge IDs are deterministic and re-linking replaces prior edges touching the target artifact.

---

## Endpoint Usage

### Ingest Appian exports

```bash
curl -X POST http://localhost:8000/api/knowledge/ingest/appian \
     -H "Content-Type: application/json" \
     -d '{}'
```

### Link one artifact

```bash
curl -X POST http://localhost:8000/api/knowledge/link/appian-sample-object
```

### Link all artifacts

```bash
curl -X POST http://localhost:8000/api/knowledge/link-all
```

### Inspect related artifacts

```bash
curl "http://localhost:8000/api/knowledge/related/appian-sample-object?limit=10"
```

### Inspect extracted entities

```bash
curl "http://localhost:8000/api/knowledge/entities/appian-sample-object"
```

---

## How To Test Locally

### 1. Prepare sample Appian exports

Place `.xml` files or `.zip` packages containing XML members under:

```bash
local_data/appian_exports/
```

### 2. Start the server

```bash
uvicorn backend.app.main:app --reload
```

### 3. Ingest Appian exports

```bash
curl -X POST http://localhost:8000/api/knowledge/ingest/appian \
     -H "Content-Type: application/json" \
     -d '{}'
```

### 4. Optionally chunk and rebuild the lexical index

```bash
curl -X POST http://localhost:8000/api/knowledge/chunk-all
curl -X POST http://localhost:8000/api/knowledge/index/rebuild
```

### 5. Run linking

```bash
curl -X POST http://localhost:8000/api/knowledge/link-all
```

### 6. Inspect artifacts, edges, related results, and entities

```bash
curl http://localhost:8000/api/knowledge/artifacts
curl http://localhost:8000/api/knowledge/edges
curl "http://localhost:8000/api/knowledge/related/<artifact_id>?limit=10"
curl "http://localhost:8000/api/knowledge/entities/<artifact_id>"
```

---

## Deferred To Later Phases

- Graph reasoning beyond deterministic rules
- Graph database integration
- Semantic entity resolution
- Impact analysis and context-pack generation
- Requirements Studio and QA Studio features
