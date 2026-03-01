import json
import logging
import re
import uuid
from typing import Any

logger = logging.getLogger(__name__)


def new_session_id() -> str:
    return uuid.uuid4().hex


def extract_json(text: str) -> Any:
    """
    Try to extract a JSON object or array from a string that may contain
    surrounding markdown fences or prose.
    """
    # Strip markdown fences
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fenced:
        text = fenced.group(1).strip()

    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try to find first { or [ and last } or ]
    start = min(
        (text.find("{") if text.find("{") != -1 else len(text)),
        (text.find("[") if text.find("[") != -1 else len(text)),
    )
    end_brace = text.rfind("}")
    end_bracket = text.rfind("]")
    end = max(end_brace, end_bracket)
    if start < end:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError as exc:
            raise ValueError(f"Could not parse JSON from LLM output: {exc}") from exc

    raise ValueError("No JSON structure found in LLM output")


def redact_auth(headers: dict[str, str]) -> dict[str, str]:
    """Return a copy of headers with Authorization values redacted."""
    return {
        k: ("***REDACTED***" if k.lower() == "authorization" else v)
        for k, v in headers.items()
    }


def safe_log_request(method: str, url: str, headers: dict[str, str]) -> None:
    logger.debug("HTTP %s %s headers=%s", method, url, redact_auth(headers))
