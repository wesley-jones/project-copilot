"""
BA Agent — orchestrates the full BA workflow:
  - Requirements generation & update
  - Story set generation & update (strict JSON)
  - Readiness checks
"""
from __future__ import annotations

import json
import logging
from typing import Any

from backend.app.schemas import (
    ReadinessFinding,
    ReadinessReport,
    RequirementsResponse,
    Severity,
    StoriesResponse,
    StorySet,
)
from backend.app.services.document_store import DocumentStore
from backend.app.services.llm_client import LLMClient
from backend.app.services.prompt_loader import PromptLoader

logger = logging.getLogger(__name__)


class BAAgent:
    def __init__(
        self,
        llm: LLMClient,
        prompt_loader: PromptLoader,
        store: DocumentStore,
    ) -> None:
        self._llm = llm
        self._pl = prompt_loader
        self._store = store

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _hidden_checklist(self) -> str:
        try:
            return self._pl.load_config("ba_hidden_checklist.md")
        except FileNotFoundError:
            logger.warning("Hidden BA checklist not found; proceeding without it.")
            return ""

    def _system_requirements(self) -> str:
        checklist = self._hidden_checklist()
        base = self._pl.load_prompt("ba_requirements.md")
        if checklist:
            base += f"\n\n---\n## Internal BA Checklist (not shown to user)\n{checklist}"
        return base

    def _system_stories(self) -> str:
        checklist = self._hidden_checklist()
        base = self._pl.load_prompt("ba_story_breakdown.md")
        if checklist:
            base += f"\n\n---\n## Internal BA Checklist (not shown to user)\n{checklist}"
        return base

    def _system_readiness(self, session_id: str) -> str:
        checklist = self._hidden_checklist()
        base = self._pl.load_prompt("ba_readiness_checklist.md")
        uploaded = self._store.load_all_docs_text(session_id)
        if checklist:
            base += f"\n\n---\n## Internal BA Checklist\n{checklist}"
        if uploaded:
            base += f"\n\n---\n## Uploaded Project Documentation\n{uploaded}"
        return base

    # ------------------------------------------------------------------
    # Requirements
    # ------------------------------------------------------------------

    def generate_requirements(self, session_id: str, raw_notes: str) -> RequirementsResponse:
        ws = self._store.load_workspace(session_id)
        ws.raw_notes = raw_notes
        self._store.save_workspace(ws)  # persist before LLM call so notes survive errors

        system = self._system_requirements()
        user_content = (
            "Please process the following raw notes into structured requirements.\n\n"
            f"## Raw Notes\n{raw_notes}"
        )
        if ws.context_docs:
            doc_block = "\n\n".join(
                f"--- Uploaded Document: {name} ---\n{text}"
                for name, text in ws.context_docs.items()
                if text.strip()
            )
            if doc_block:
                user_content += f"\n\n## Uploaded Supporting Documents\n{doc_block}"
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user_content},
        ]
        raw = self._llm.chat(messages, temperature=0.3)
        result = self._parse_requirements_output(raw)

        ws.requirements_draft = result.requirements
        self._store.save_workspace(ws)
        return RequirementsResponse(session_id=session_id, **result.model_dump(exclude={"session_id"}))

    def update_requirements(self, session_id: str, edit_instruction: str) -> RequirementsResponse:
        ws = self._store.load_workspace(session_id)
        if not ws.requirements_draft:
            raise ValueError("No requirements draft exists for this session. Generate requirements first.")

        system = self._system_requirements()
        messages = [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": (
                    "Here is the current requirements document:\n\n"
                    f"{ws.requirements_draft}\n\n"
                    f"Please apply the following edit instruction:\n{edit_instruction}"
                ),
            },
        ]
        raw = self._llm.chat(messages, temperature=0.3)
        result = self._parse_requirements_output(raw)

        ws.requirements_draft = result.requirements
        self._store.save_workspace(ws)
        return RequirementsResponse(session_id=session_id, **result.model_dump(exclude={"session_id"}))

    def _parse_requirements_output(self, raw: str) -> RequirementsResponse:
        """
        Parse the LLM output for requirements. Expects structured text with
        sections for Requirements, Clarifying Questions, and Assumptions.
        Falls back gracefully.
        """
        import re

        requirements = raw
        questions: list[str] = []
        assumptions: list[str] = []

        # Try to extract sections by common heading patterns
        cq_match = re.search(
            r"#+\s*clarifying questions?\s*\n(.*?)(?=\n#+|\Z)", raw, re.IGNORECASE | re.DOTALL
        )
        if cq_match:
            block = cq_match.group(1)
            questions = [
                line.lstrip("-*•123456789. ").strip()
                for line in block.strip().splitlines()
                if line.strip() and not line.strip().startswith("#")
            ]

        ass_match = re.search(
            r"#+\s*assumptions?\s*\n(.*?)(?=\n#+|\Z)", raw, re.IGNORECASE | re.DOTALL
        )
        if ass_match:
            block = ass_match.group(1)
            assumptions = [
                line.lstrip("-*•123456789. ").strip()
                for line in block.strip().splitlines()
                if line.strip() and not line.strip().startswith("#")
            ]

        return RequirementsResponse(
            session_id="",
            requirements=requirements,
            clarifying_questions=questions,
            assumptions=assumptions,
        )

    # ------------------------------------------------------------------
    # Stories
    # ------------------------------------------------------------------

    def generate_stories(self, session_id: str) -> StoriesResponse:
        ws = self._store.load_workspace(session_id)
        if not ws.requirements_draft:
            raise ValueError("No requirements draft found. Generate requirements first.")

        system = self._system_stories()
        schema_hint = json.dumps(StorySet.model_json_schema(), indent=2)
        messages = [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": (
                    "Generate a story set (1 Epic + Stories) from the requirements below.\n"
                    "Output ONLY valid JSON matching this schema (no markdown, no prose):\n"
                    f"{schema_hint}\n\n"
                    f"## Requirements\n{ws.requirements_draft}"
                ),
            },
        ]
        data = self._llm.chat_json(messages, temperature=0.1)
        story_set = StorySet(**data)

        ws.story_set = story_set.model_dump()
        self._store.save_workspace(ws)
        return StoriesResponse(session_id=session_id, story_set=story_set)

    def update_stories(self, session_id: str, edit_instruction: str) -> StoriesResponse:
        ws = self._store.load_workspace(session_id)
        if not ws.story_set:
            raise ValueError("No story set found. Generate stories first.")

        system = self._system_stories()
        schema_hint = json.dumps(StorySet.model_json_schema(), indent=2)
        messages = [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": (
                    "Here is the current story set JSON:\n"
                    f"{json.dumps(ws.story_set, indent=2)}\n\n"
                    f"Apply this edit instruction: {edit_instruction}\n\n"
                    "Output ONLY valid JSON matching this schema:\n"
                    f"{schema_hint}"
                ),
            },
        ]
        data = self._llm.chat_json(messages, temperature=0.1)
        story_set = StorySet(**data)

        ws.story_set = story_set.model_dump()
        self._store.save_workspace(ws)
        return StoriesResponse(session_id=session_id, story_set=story_set)

    # ------------------------------------------------------------------
    # Readiness
    # ------------------------------------------------------------------

    def check_readiness(self, session_id: str) -> "ReadinessResponse":
        from backend.app.schemas import ReadinessResponse

        ws = self._store.load_workspace(session_id)
        if not ws.requirements_draft:
            raise ValueError("No requirements draft found.")

        system = self._system_readiness(session_id)
        story_context = (
            json.dumps(ws.story_set, indent=2) if ws.story_set else "Not yet generated."
        )
        schema_hint = json.dumps(ReadinessReport.model_json_schema(), indent=2)
        messages = [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": (
                    "Run a readiness check on the following requirements and story set.\n"
                    "Output ONLY valid JSON matching this schema:\n"
                    f"{schema_hint}\n\n"
                    f"## Requirements\n{ws.requirements_draft}\n\n"
                    f"## Story Set\n{story_context}"
                ),
            },
        ]
        data = self._llm.chat_json(messages, temperature=0.1)
        report = ReadinessReport(**data)

        ws.readiness_report = report.model_dump()
        self._store.save_workspace(ws)
        return ReadinessResponse(session_id=session_id, report=report)
