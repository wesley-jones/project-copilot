# ADR 0004 - Phase 3: Graph Foundations and Appian Baseline Extraction

## Status

Accepted

## Context

Phase 2 added chunk-level lexical retrieval, but the knowledge layer still lacks a first-pass
graph of artifact relationships and baseline Appian export coverage. Before later impact analysis
and context-pack features can exist, DIP needs deterministic graph edges, inspectable related
artifact results, and normalized Appian XML/ZIP ingestion.

## Decisions

### D1: Introduce deterministic graph edges before advanced graph intelligence

Phase 3 creates `GraphEdge` records using conservative, rule-based logic only. Edge creation is
deterministic, explainable, and safe to re-run.

### D2: Use heuristic entity/reference extraction, not full semantic NER

Entity extraction is intentionally lightweight and pattern-based. It supports obvious Jira keys,
Appian/XML-style identifiers, and business-like names without claiming complete entity resolution.

### D3: Add baseline Appian XML and ZIP ingestion without full schema modeling

Appian exports are normalized into searchable `ArtifactRecord`s by parsing XML safely and flattening
obvious metadata and references. This phase does not attempt full semantic Appian reconstruction.

### D4: Keep graph storage file-based

Graph edges continue to be stored in the existing JSON-backed edge store. No graph database or
additional infrastructure is introduced.

### D5: Capture original Appian sources, not every ZIP member

Raw capture stores standalone XML files directly and original ZIP files once. ZIP-member artifacts
reference the captured ZIP via `raw_ref#member=...` to preserve provenance without adding heavy
member-level raw-copy logic.

## Consequences

**Positive:**
- Appian exports become searchable and linkable in the same knowledge layer as Jira and local docs.
- Related artifact results are inspectable and explainable.
- Re-linking remains deterministic and overwrite-safe.

**Negative / deferred:**
- Entity extraction remains heuristic and can miss or over-match some references.
- Appian object understanding is intentionally shallow in this phase.
- Graph reasoning, advanced impact analysis, and semantic linking remain deferred.
