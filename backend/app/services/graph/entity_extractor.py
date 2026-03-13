"""Deterministic, heuristic entity extraction for artifacts and chunks."""
from __future__ import annotations

from functools import lru_cache
import re

from backend.app.config import get_settings
from backend.app.services.graph.models import ArtifactRecord, ChunkRecord

_JIRA_KEY_RE = re.compile(r"\b[A-Z][A-Z0-9]+-\d+\b")
_SNAKE_CASE_RE = re.compile(r"\b[a-z]+(?:_[a-z0-9]+)+\b")
_CAMEL_CASE_RE = re.compile(r"\b[a-z]+(?:[A-Z][a-z0-9]+)+\b")
_SCREAMING_RE = re.compile(r"\b[A-Z][A-Z0-9_]{2,}\b")
_CAPITALIZED_PHRASE_RE = re.compile(r"\b[A-Z][a-z0-9]+(?:\s+[A-Z][a-z0-9]+){1,4}\b")
_XML_NAME_RE = re.compile(r"\b[a-zA-Z_][\w.-]{2,}\b")
_WHITESPACE_RE = re.compile(r"\s+")


class EntityExtractor:
    """Extract deterministic, de-duplicated entity-like terms from text."""

    def __init__(self) -> None:
        settings = get_settings()
        self._min_len = max(1, settings.knowledge_entity_min_token_len)
        self._max_results = max(1, settings.knowledge_entity_max_per_chunk)

    def extract_from_text(self, text: str) -> list[str]:
        """Return stable, de-duplicated entities extracted from *text*."""
        candidates: list[str] = []
        for pattern in (
            _JIRA_KEY_RE,
            _CAPITALIZED_PHRASE_RE,
            _SNAKE_CASE_RE,
            _CAMEL_CASE_RE,
            _SCREAMING_RE,
            _XML_NAME_RE,
        ):
            candidates.extend(match.group(0).strip() for match in pattern.finditer(text or ""))

        seen: set[str] = set()
        results: list[str] = []
        for candidate in candidates:
            candidate = self._clean_candidate(candidate)
            if candidate is None:
                continue
            if len(candidate) < self._min_len:
                continue
            key = candidate.casefold()
            if key in seen:
                continue
            seen.add(key)
            results.append(candidate)
            if len(results) >= self._max_results:
                break
        return results

    def extract_from_chunk(self, chunk: ChunkRecord) -> list[str]:
        """Return entities extracted from *chunk* text."""
        return self.extract_from_text(chunk.text)

    def extract_from_artifact(self, artifact: ArtifactRecord) -> list[str]:
        """Return entities extracted from artifact text and lightweight metadata."""
        combined = "\n".join(
            part for part in [
                artifact.metadata.title,
                artifact.text_content,
                " ".join(str(value) for value in artifact.extra.get("extracted_refs", [])),
            ] if part
        )
        return self.extract_from_text(combined)

    def _clean_candidate(self, candidate: str) -> str | None:
        """Normalize a candidate and discard obvious low-signal XML tokens."""
        normalized = _WHITESPACE_RE.sub(" ", candidate.strip())
        if not normalized:
            return None

        if " " not in normalized and normalized.islower():
            has_structure = (
                "_" in normalized
                or "-" in normalized
                or any(char.isdigit() for char in normalized)
                or any(char.isupper() for char in normalized)
            )
            if not has_structure:
                return None

        return normalized


@lru_cache
def get_entity_extractor() -> EntityExtractor:
    return EntityExtractor()
