"""
PM Agent — translates natural language to JQL and executes the query.
"""
from __future__ import annotations

import logging
from typing import Any

from backend.app.schemas import JiraIssueResult, PMQueryResponse
from backend.app.services.jira_client import JiraClient
from backend.app.services.llm_client import LLMClient
from backend.app.services.prompt_loader import PromptLoader

logger = logging.getLogger(__name__)


class PMAgent:
    def __init__(
        self,
        llm: LLMClient,
        prompt_loader: PromptLoader,
        jira: JiraClient,
    ) -> None:
        self._llm = llm
        self._pl = prompt_loader
        self._jira = jira

    def query(self, session_id: str, natural_language_query: str) -> PMQueryResponse:
        system = self._pl.load_prompt("pm_jira_query.md")
        messages = [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": (
                    f"Project key: {self._jira._settings.jira_project_key or 'not set'}\n\n"
                    f"Query: {natural_language_query}\n\n"
                    "Respond with ONLY the JQL string — no explanation, no markdown."
                ),
            },
        ]
        jql_raw = self._llm.chat(messages, temperature=0.0, max_tokens=256)
        # Strip any accidental markdown fences or quotes
        jql = jql_raw.strip().strip("`").strip('"').strip("'").strip()

        logger.info("PM Agent generated JQL: %s", jql)

        results: list[JiraIssueResult] = []
        total = 0

        if self._jira.is_configured():
            data = self._jira.search_issues(jql)
            total = data.get("total", 0)
            for issue in data.get("issues", []):
                fields = issue.get("fields", {})
                assignee_field = fields.get("assignee")
                priority_field = fields.get("priority")
                results.append(
                    JiraIssueResult(
                        key=issue["key"],
                        summary=fields.get("summary", ""),
                        status=fields.get("status", {}).get("name", ""),
                        issue_type=fields.get("issuetype", {}).get("name", ""),
                        assignee=assignee_field.get("displayName") if assignee_field else None,
                        priority=priority_field.get("name") if priority_field else None,
                    )
                )
        else:
            logger.warning("Jira not configured — returning JQL only.")

        return PMQueryResponse(
            session_id=session_id,
            jql=jql,
            results=results,
            total=total,
        )
