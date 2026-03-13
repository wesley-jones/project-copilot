"""Deterministic lexical tokenization for indexing and keyword extraction."""
from __future__ import annotations

from collections import Counter
from functools import lru_cache
import re

from backend.app.config import get_settings

_STOPWORDS: frozenset[str] = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "how",
        "in",
        "is",
        "it",
        "of",
        "on",
        "or",
        "that",
        "the",
        "this",
        "to",
        "was",
        "were",
        "with",
    }
)

_NON_WORD_RE = re.compile(r"\W+")


class Tokenizer:
    """Simple, stable tokenizer shared by chunking, indexing, and retrieval."""

    def __init__(self, case_sensitive: bool | None = None, min_token_length: int = 3) -> None:
        settings = get_settings()
        self._case_sensitive = (
            settings.knowledge_index_case_sensitive if case_sensitive is None else case_sensitive
        )
        self._min_token_length = max(1, min_token_length)

    def tokenize(self, text: str) -> list[str]:
        """Return stable searchable tokens extracted from *text*."""
        if not text:
            return []

        tokens: list[str] = []
        for raw_token in _NON_WORD_RE.split(text):
            if not raw_token:
                continue
            token = raw_token if self._case_sensitive else raw_token.lower()
            if len(token) < self._min_token_length:
                continue
            if token.lower() in _STOPWORDS:
                continue
            tokens.append(token)
        return tokens

    def extract_keywords(self, text: str, limit: int = 8) -> list[str]:
        """Return the top deterministic keywords from *text*."""
        counts = Counter(self.tokenize(text))
        ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        return [token for token, _ in ranked[:limit]]


@lru_cache
def get_tokenizer() -> Tokenizer:
    return Tokenizer()
