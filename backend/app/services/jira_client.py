"""
Jira REST API v2 client.

Rules:
- Never log API tokens or Authorization header values.
- Apply request timeouts.
- Redact auth in any logged headers.
"""
from __future__ import annotations

import logging
from base64 import b64encode
from typing import Any, Optional

import httpx

from backend.app.config import get_settings
from backend.app.utils import redact_auth, safe_log_request

logger = logging.getLogger(__name__)


class JiraError(Exception):
    def __init__(self, message: str, status_code: Optional[int] = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class JiraClient:
    def __init__(self) -> None:
        self._settings = get_settings()

    @property
    def _base(self) -> str:
        return self._settings.jira_base_url.rstrip("/")

    @property
    def _headers(self) -> dict[str, str]:
        mode = (self._settings.jira_auth_mode or "basic").strip().lower()
        auth_value: str

        if mode == "bearer" or (mode == "auto" and self._settings.jira_bearer_token):
            token = self._settings.jira_bearer_token or self._settings.jira_api_token
            auth_value = f"Bearer {token}"
        else:
            token = b64encode(
                f"{self._settings.jira_user}:{self._settings.jira_api_token}".encode()
            ).decode()
            auth_value = f"Basic {token}"

        return {
            "Authorization": auth_value,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _get(self, path: str, params: Optional[dict[str, Any]] = None) -> Any:
        url = f"{self._base}{path}"
        safe_log_request("GET", url, self._headers)
        try:
            with httpx.Client(
                timeout=self._settings.jira_timeout,
                verify=self._settings.jira_verify_ssl,
            ) as client:
                resp = client.get(url, headers=self._headers, params=params)
            resp.raise_for_status()
            return resp.json()
        except httpx.TimeoutException as exc:
            raise JiraError(f"Jira request timed out: {exc}") from exc
        except httpx.HTTPStatusError as exc:
            raise JiraError(
                f"Jira HTTP {exc.response.status_code}: {exc.response.text[:300]}",
                status_code=exc.response.status_code,
            ) from exc

    def _post(self, path: str, body: dict[str, Any]) -> Any:
        url = f"{self._base}{path}"
        safe_log_request("POST", url, self._headers)
        try:
            with httpx.Client(
                timeout=self._settings.jira_timeout,
                verify=self._settings.jira_verify_ssl,
            ) as client:
                resp = client.post(url, headers=self._headers, json=body)
            resp.raise_for_status()
            return resp.json()
        except httpx.TimeoutException as exc:
            raise JiraError(f"Jira request timed out: {exc}") from exc
        except httpx.HTTPStatusError as exc:
            raise JiraError(
                f"Jira HTTP {exc.response.status_code}: {exc.response.text[:300]}",
                status_code=exc.response.status_code,
            ) from exc

    # ------------------------------------------------------------------
    # Issue creation helpers
    # ------------------------------------------------------------------

    def _issue_body(
        self,
        summary: str,
        description: str,
        issue_type: str,
        labels: list[str],
        priority: Optional[str] = None,
        parent_key: Optional[str] = None,
    ) -> dict[str, Any]:
        fields: dict[str, Any] = {
            "project": {"key": self._settings.jira_project_key},
            "summary": summary,
            "description": description,
            "issuetype": {"name": issue_type},
        }
        if labels:
            fields["labels"] = labels
        if priority:
            fields["priority"] = {"name": priority.capitalize()}
        if parent_key:
            fields["parent"] = {"key": parent_key}
        return {"fields": fields}

    def create_epic(
        self,
        summary: str,
        description: str,
        labels: list[str],
        priority: Optional[str] = None,
    ) -> str:
        """Create an Epic and return its key."""
        body = self._issue_body(summary, description, "Epic", labels, priority)
        # Some Jira setups require Epic Name field
        body["fields"]["customfield_10011"] = summary
        data = self._post("/rest/api/2/issue", body)
        return data["key"]

    def create_story(
        self,
        summary: str,
        description: str,
        labels: list[str],
        priority: Optional[str] = None,
        parent_key: Optional[str] = None,
    ) -> str:
        """Create a Story and return its key."""
        body = self._issue_body(summary, description, "Story", labels, priority, parent_key)
        data = self._post("/rest/api/2/issue", body)
        return data["key"]

    def create_subtask(
        self,
        summary: str,
        description: str,
        parent_key: str,
    ) -> str:
        body = self._issue_body(summary, description, "Subtask", [], parent_key=parent_key)
        data = self._post("/rest/api/2/issue", body)
        return data["key"]

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search_issues(self, jql: str, max_results: int = 50) -> dict[str, Any]:
        """Execute a JQL search and return the raw Jira response dict."""
        params = {
            "jql": jql,
            "maxResults": max_results,
            "fields": "summary,status,issuetype,assignee,priority",
        }
        return self._get("/rest/api/2/search", params=params)

    def get_issue(self, issue_key: str) -> dict[str, Any]:
        return self._get(f"/rest/api/2/issue/{issue_key}")

    def is_configured(self) -> bool:
        s = self._settings
        mode = (s.jira_auth_mode or "basic").strip().lower()
        if mode == "bearer":
            has_auth = bool(s.jira_bearer_token or s.jira_api_token)
        elif mode == "auto":
            has_auth = bool(s.jira_bearer_token or (s.jira_user and s.jira_api_token))
        else:
            has_auth = bool(s.jira_user and s.jira_api_token)
        return bool(s.jira_base_url and has_auth and s.jira_project_key)


def get_jira_client() -> JiraClient:
    return JiraClient()
