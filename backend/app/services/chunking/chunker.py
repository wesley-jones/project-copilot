"""
Deterministic artifact chunking for lexical retrieval.

Phase 2 intentionally keeps chunking lightweight:
  - Split on markdown headings first.
  - Fall back to paragraph blocks.
  - Split oversized sections into overlapping character windows.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import re

from backend.app.config import get_settings
from backend.app.services.graph.models import ArtifactRecord, ChunkRecord, ChunkType
from backend.app.services.indexing.tokenizer import Tokenizer, get_tokenizer

_HEADING_RE = re.compile(r"(?m)^(#{1,6})\s+(.+?)\s*$")
_PARAGRAPH_RE = re.compile(r"(?ms)\S.*?(?=\n\s*\n|\Z)")


@dataclass(frozen=True)
class _SectionCandidate:
    text: str
    char_start: int
    char_end: int
    title: str | None = None
    source_heading: str | None = None


@dataclass(frozen=True)
class _ChunkCandidate:
    text: str
    char_start: int
    char_end: int
    chunk_type: ChunkType
    section_title: str | None
    source_heading: str | None
    truncated: bool = False


class Chunker:
    """Split ArtifactRecord text into deterministic ChunkRecord objects."""

    def __init__(self, tokenizer: Tokenizer | None = None) -> None:
        settings = get_settings()
        self._target_chars = max(1, settings.knowledge_chunk_target_chars)
        self._overlap_chars = max(0, min(settings.knowledge_chunk_overlap_chars, self._target_chars - 1))
        self._max_chunks = max(1, settings.knowledge_max_chunks_per_artifact)
        self._tokenizer = tokenizer if tokenizer is not None else get_tokenizer()

    def chunk_artifact(self, artifact: ArtifactRecord) -> list[ChunkRecord]:
        """Return deterministic chunks for *artifact* based on its text_content."""
        text = self._normalize_text(artifact.text_content)
        if not text:
            return []

        sections = self._split_sections(text)
        candidates = self._build_chunk_candidates(sections, text)
        if len(candidates) > self._max_chunks:
            candidates = candidates[: self._max_chunks]
            last = candidates[-1]
            candidates[-1] = _ChunkCandidate(
                text=last.text,
                char_start=last.char_start,
                char_end=last.char_end,
                chunk_type=last.chunk_type,
                section_title=last.section_title,
                source_heading=last.source_heading,
                truncated=True,
            )

        return [self._to_chunk_record(artifact, index, candidate) for index, candidate in enumerate(candidates)]

    def _normalize_text(self, text: str) -> str:
        return text.replace("\r\n", "\n").replace("\r", "\n").strip()

    def _split_sections(self, text: str) -> list[_SectionCandidate]:
        heading_sections = self._split_by_headings(text)
        if heading_sections:
            return heading_sections
        paragraph_sections = self._split_by_paragraphs(text)
        if paragraph_sections:
            return paragraph_sections
        return [_SectionCandidate(text=text, char_start=0, char_end=len(text))]

    def _split_by_headings(self, text: str) -> list[_SectionCandidate]:
        matches = list(_HEADING_RE.finditer(text))
        if not matches:
            return []

        sections: list[_SectionCandidate] = []
        first_heading_start = matches[0].start()
        if first_heading_start > 0:
            preface = text[:first_heading_start].strip()
            if preface:
                sections.append(
                    _SectionCandidate(
                        text=preface,
                        char_start=0,
                        char_end=first_heading_start,
                    )
                )

        for index, match in enumerate(matches):
            start = match.start()
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            section_text = text[start:end].strip()
            if not section_text:
                continue
            heading_text = match.group(0).strip()
            sections.append(
                _SectionCandidate(
                    text=section_text,
                    char_start=start,
                    char_end=end,
                    title=match.group(2).strip(),
                    source_heading=heading_text,
                )
            )
        return sections

    def _split_by_paragraphs(self, text: str) -> list[_SectionCandidate]:
        sections: list[_SectionCandidate] = []
        for match in _PARAGRAPH_RE.finditer(text):
            section_text = match.group(0).strip()
            if not section_text:
                continue
            sections.append(
                _SectionCandidate(
                    text=section_text,
                    char_start=match.start(),
                    char_end=match.end(),
                )
            )
        return sections

    def _build_chunk_candidates(
        self,
        sections: list[_SectionCandidate],
        text: str,
    ) -> list[_ChunkCandidate]:
        if len(sections) == 1 and len(sections[0].text) <= self._target_chars:
            only = sections[0]
            return [
                _ChunkCandidate(
                    text=only.text,
                    char_start=0,
                    char_end=len(text),
                    chunk_type=ChunkType.FULL_TEXT,
                    section_title=only.title,
                    source_heading=only.source_heading,
                )
            ]

        chunks: list[_ChunkCandidate] = []
        current_sections: list[_SectionCandidate] = []

        def flush_current() -> None:
            if not current_sections:
                return
            merged_text = "\n\n".join(section.text for section in current_sections).strip()
            if not merged_text:
                current_sections.clear()
                return
            chunks.append(
                _ChunkCandidate(
                    text=merged_text,
                    char_start=current_sections[0].char_start,
                    char_end=current_sections[-1].char_end,
                    chunk_type=ChunkType.SECTION,
                    section_title=current_sections[0].title,
                    source_heading=current_sections[0].source_heading,
                )
            )
            current_sections.clear()

        for section in sections:
            if len(section.text) > self._target_chars:
                flush_current()
                chunks.extend(self._window_split(section))
                continue

            if not current_sections:
                current_sections.append(section)
                continue

            merged_length = len("\n\n".join([*(part.text for part in current_sections), section.text]))
            if merged_length <= self._target_chars:
                current_sections.append(section)
            else:
                flush_current()
                current_sections.append(section)

        flush_current()
        return chunks

    def _window_split(self, section: _SectionCandidate) -> list[_ChunkCandidate]:
        chunks: list[_ChunkCandidate] = []
        step = max(1, self._target_chars - self._overlap_chars)
        start = 0
        text_length = len(section.text)

        while start < text_length:
            end = min(start + self._target_chars, text_length)
            window_text = section.text[start:end].strip()
            if window_text:
                chunks.append(
                    _ChunkCandidate(
                        text=window_text,
                        char_start=section.char_start + start,
                        char_end=section.char_start + end,
                        chunk_type=ChunkType.PARAGRAPH,
                        section_title=section.title,
                        source_heading=section.source_heading,
                    )
                )
            if end >= text_length:
                break
            start += step

        return chunks

    def _to_chunk_record(
        self,
        artifact: ArtifactRecord,
        index: int,
        candidate: _ChunkCandidate,
    ) -> ChunkRecord:
        return ChunkRecord(
            chunk_id=f"{artifact.metadata.artifact_id}-chunk-{index:04d}",
            artifact_id=artifact.metadata.artifact_id,
            chunk_index=index,
            chunk_type=candidate.chunk_type,
            text=candidate.text,
            token_estimate=max(1, len(candidate.text) // 4),
            section_title=candidate.section_title,
            page_or_location=None,
            keywords=self._tokenizer.extract_keywords(candidate.text),
            entities=[],
            extra={
                "char_start": candidate.char_start,
                "char_end": candidate.char_end,
                "truncated": candidate.truncated,
                "source_heading": candidate.source_heading,
            },
        )


@lru_cache
def get_chunker() -> Chunker:
    return Chunker()
