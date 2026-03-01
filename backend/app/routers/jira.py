from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, status

from backend.app.schemas import (
    JiraCreateRequest,
    JiraCreateResponse,
    JiraIssuePayload,
)
from backend.app.services.document_store import DocumentStore, get_document_store
from backend.app.services.jira_client import JiraClient, JiraError, get_jira_client

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/jira", tags=["Jira"])


@router.post("/create_story_set", response_model=JiraCreateResponse)
async def create_story_set(
    req: JiraCreateRequest,
    store: DocumentStore = Depends(get_document_store),
    jira: JiraClient = Depends(get_jira_client),
) -> JiraCreateResponse:
    ws = store.load_workspace(req.session_id)
    if not ws.story_set:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No story set found. Generate stories first.",
        )

    from backend.app.schemas import StorySet
    story_set = StorySet(**ws.story_set)

    # Build payloads list
    epic = story_set.epic
    payloads: list[JiraIssuePayload] = [
        JiraIssuePayload(
            issue_type="Epic",
            summary=epic.title,
            description=epic.description,
            labels=epic.labels,
            priority=epic.priority,
        )
    ]
    for story in story_set.stories:
        payloads.append(
            JiraIssuePayload(
                issue_type="Story",
                summary=story.title,
                description=_format_story_description(story),
                labels=story.labels,
                priority=story.priority,
            )
        )

    if req.dry_run:
        return JiraCreateResponse(dry_run=True, payloads=payloads)

    # Actually create issues
    if not jira.is_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Jira is not configured. Set JIRA_BASE_URL, JIRA_USER, JIRA_API_TOKEN, JIRA_PROJECT_KEY.",
        )

    created_keys: list[str] = []
    errors: list[str] = []
    epic_key: str | None = None

    try:
        epic_key = jira.create_epic(
            summary=epic.title,
            description=epic.description,
            labels=epic.labels,
            priority=epic.priority,
        )
        created_keys.append(epic_key)
        logger.info("Created Epic: %s", epic_key)
    except JiraError as exc:
        errors.append(f"Epic creation failed: {exc}")
        logger.error("Epic creation failed: %s", exc)

    for story in story_set.stories:
        try:
            story_key = jira.create_story(
                summary=story.title,
                description=_format_story_description(story),
                labels=story.labels,
                priority=story.priority,
                parent_key=epic_key,
            )
            created_keys.append(story_key)
            logger.info("Created Story: %s", story_key)

            for subtask in story.subtasks:
                try:
                    sub_key = jira.create_subtask(
                        summary=subtask.title,
                        description=subtask.description,
                        parent_key=story_key,
                    )
                    created_keys.append(sub_key)
                except JiraError as exc:
                    errors.append(f"Subtask '{subtask.title}' failed: {exc}")

        except JiraError as exc:
            errors.append(f"Story '{story.title}' creation failed: {exc}")
            logger.error("Story creation failed: %s", exc)

    return JiraCreateResponse(dry_run=False, payloads=payloads, created_keys=created_keys, errors=errors)


def _format_story_description(story) -> str:
    parts = [story.description]
    if story.acceptance_criteria:
        parts.append("\n\n*Acceptance Criteria:*")
        for ac in story.acceptance_criteria:
            parts.append(f"* {ac}")
    if story.notes:
        parts.append(f"\n\n*Notes:* {story.notes}")
    if story.dependencies:
        parts.append("\n\n*Dependencies:* " + ", ".join(story.dependencies))
    return "\n".join(parts)
