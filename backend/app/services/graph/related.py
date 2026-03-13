"""Helpers for related-artifact inspection over stored graph edges."""
from __future__ import annotations

from typing import Any


def build_related_artifacts(service, artifact_id: str, limit: int = 10) -> list[dict[str, Any]]:
    """Return conservative, inspectable related-artifact summaries for *artifact_id*."""
    artifact = service.get_artifact(artifact_id)
    if artifact is None:
        raise ValueError(f"Artifact '{artifact_id}' not found.")

    chunk_prefix = f"{artifact_id}-chunk-"
    related: dict[str, dict[str, Any]] = {}
    artifacts = {item.metadata.artifact_id: item for item in service.list_artifacts()}

    for edge in service.list_edges():
        other_id: str | None = None
        if edge.from_id == artifact_id and not edge.to_id.startswith(chunk_prefix):
            other_id = edge.to_id
        elif edge.to_id == artifact_id and not edge.from_id.startswith(chunk_prefix):
            other_id = edge.from_id
        elif edge.from_id.startswith(chunk_prefix):
            other_id = edge.to_id
        elif edge.to_id.startswith(chunk_prefix):
            other_id = edge.from_id

        if other_id is None or other_id == artifact_id or other_id not in artifacts:
            continue

        other = artifacts[other_id]
        entry = related.setdefault(
            other_id,
            {
                "artifact_id": other_id,
                "title": other.metadata.title,
                "artifact_kind": other.metadata.artifact_kind.value,
                "source_system": other.metadata.source_system.value,
                "edge_types": [],
                "score": 0,
                "rationale": [],
            },
        )
        if edge.edge_type.value not in entry["edge_types"]:
            entry["edge_types"].append(edge.edge_type.value)
        entry["score"] += 1
        if edge.evidence and edge.evidence not in entry["rationale"]:
            entry["rationale"].append(edge.evidence)

    results = sorted(related.values(), key=lambda item: (-item["score"], item["artifact_id"]))
    for item in results:
        item["rationale"] = "; ".join(item["rationale"][:3]) if item["rationale"] else None
    return results[: max(1, limit)]
