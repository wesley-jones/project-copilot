"""Ranked lexical retrieval over the persisted chunk index."""
from __future__ import annotations

from functools import lru_cache
import logging

from backend.app.config import get_settings
from backend.app.services.graph.models import ArtifactKind, SourceSystem
from backend.app.services.indexing.index_store import IndexStore, get_index_store
from backend.app.services.indexing.models import IndexedChunk
from backend.app.services.indexing.tokenizer import Tokenizer, get_tokenizer

logger = logging.getLogger(__name__)


class Retriever:
    """Search the persisted lexical index and return ranked chunk results."""

    def __init__(self, store: IndexStore | None = None, tokenizer: Tokenizer | None = None) -> None:
        self._store = store if store is not None else get_index_store()
        self._tokenizer = tokenizer if tokenizer is not None else get_tokenizer()
        self._case_sensitive = get_settings().knowledge_index_case_sensitive

    def search(
        self,
        q: str,
        project_key: str | None = None,
        source_system: SourceSystem | None = None,
        artifact_kind: ArtifactKind | None = None,
        artifact_id: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, object]]:
        """Search indexed chunks using simple lexical scoring."""
        if not q or not q.strip():
            raise ValueError("Search query must not be empty.")

        query_tokens = list(dict.fromkeys(self._tokenizer.tokenize(q)))
        if not query_tokens:
            raise ValueError("Search query did not contain any searchable terms.")

        index = self._store.load_index()
        if not index.tokens or not index.chunks:
            return []

        requested_limit = limit if limit is not None else get_settings().knowledge_search_default_limit
        effective_limit = max(1, requested_limit)
        query_text = q if self._case_sensitive else q.lower()

        candidate_scores: dict[str, dict[str, object]] = {}
        for token in query_tokens:
            postings = index.tokens.get(token, [])
            for posting in postings:
                entry = index.chunks.get(posting.chunk_id)
                if entry is None or not self._matches_filters(
                    entry,
                    project_key=project_key,
                    source_system=source_system,
                    artifact_kind=artifact_kind,
                    artifact_id=artifact_id,
                ):
                    continue

                candidate = candidate_scores.setdefault(
                    posting.chunk_id,
                    {
                        "entry": entry,
                        "term_frequency": 0,
                        "matched_terms": set(),
                    },
                )
                candidate["term_frequency"] = int(candidate["term_frequency"]) + posting.term_frequency
                candidate["matched_terms"].add(token)

        ranked_results: list[dict[str, object]] = []
        for chunk_id, candidate in candidate_scores.items():
            entry = candidate["entry"]
            matched_terms = sorted(candidate["matched_terms"])
            score = float(candidate["term_frequency"])
            score += float(len(matched_terms) * 2)

            title_text = entry.artifact_title if self._case_sensitive else entry.artifact_title.lower()
            score += sum(0.5 for term in matched_terms if term in title_text)
            if artifact_id and entry.artifact_id == artifact_id:
                score += 2.0
            if query_text == (entry.artifact_id if self._case_sensitive else entry.artifact_id.lower()):
                score += 3.0

            ranked_results.append(
                {
                    "chunk_id": chunk_id,
                    "artifact_id": entry.artifact_id,
                    "score": round(score, 4),
                    "matched_terms": matched_terms,
                    "chunk_index": entry.chunk_index,
                    "section_title": entry.section_title,
                    "snippet": self._make_snippet(entry.text, matched_terms),
                    "artifact": {
                        "title": entry.artifact_title,
                        "project_key": entry.project_key,
                        "source_system": entry.source_system,
                        "artifact_kind": entry.artifact_kind,
                        "url": entry.url,
                    },
                }
            )

        ranked_results.sort(
            key=lambda item: (
                -float(item["score"]),
                str(item["artifact_id"]),
                int(item["chunk_index"]),
                str(item["chunk_id"]),
            )
        )
        return ranked_results[:effective_limit]

    def _matches_filters(
        self,
        entry: IndexedChunk,
        *,
        project_key: str | None,
        source_system: SourceSystem | None,
        artifact_kind: ArtifactKind | None,
        artifact_id: str | None,
    ) -> bool:
        if project_key is not None and entry.project_key != project_key:
            return False
        if source_system is not None and entry.source_system != source_system.value:
            return False
        if artifact_kind is not None and entry.artifact_kind != artifact_kind.value:
            return False
        if artifact_id is not None and entry.artifact_id != artifact_id:
            return False
        return True

    def _make_snippet(self, text: str, matched_terms: list[str]) -> str:
        if not text:
            return ""

        haystack = text if self._case_sensitive else text.lower()
        start_index = 0
        for term in matched_terms:
            index = haystack.find(term if self._case_sensitive else term.lower())
            if index >= 0:
                start_index = max(0, index - 60)
                break

        end_index = min(len(text), start_index + 240)
        snippet = text[start_index:end_index].strip()
        if start_index > 0:
            snippet = f"...{snippet}"
        if end_index < len(text):
            snippet = f"{snippet}..."
        return snippet


@lru_cache
def get_retriever() -> Retriever:
    return Retriever()
