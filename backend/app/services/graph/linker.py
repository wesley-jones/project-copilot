"""Rule-based graph linking for Phase 3."""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from backend.app.config import get_settings
from backend.app.services.graph.entity_extractor import get_entity_extractor
from backend.app.services.graph.models import ArtifactRecord, ChunkRecord, EdgeType, GraphEdge, SourceSystem
from backend.app.services.indexing.tokenizer import get_tokenizer

if TYPE_CHECKING:
    from backend.app.services.knowledge_service import KnowledgeService

logger = logging.getLogger(__name__)


def _edge_id(edge_type: EdgeType, from_id: str, to_id: str) -> str:
    digest = hashlib.sha1(f"{edge_type.value}|{from_id}|{to_id}".encode("utf-8")).hexdigest()[:16]
    return f"edge-{digest}"


class Linker:
    """Create conservative, deterministic GraphEdge relationships."""

    _SYMMETRIC_EDGE_TYPES = frozenset(
        {
            EdgeType.SAME_PROJECT,
            EdgeType.RELATED_TO,
            EdgeType.SAME_APPIAN_PACKAGE,
            EdgeType.SAME_SOURCE,
        }
    )

    def __init__(self) -> None:
        self._settings = get_settings()
        self._tokenizer = get_tokenizer()
        self._extractor = get_entity_extractor()

    def link_all(self, service: "KnowledgeService", run_id: str | None = None) -> dict[str, int]:
        artifacts = sorted(service.list_artifacts(), key=lambda item: item.metadata.artifact_id)
        summary = {
            "artifacts_seen": len(artifacts),
            "artifacts_linked": 0,
            "edges_created": 0,
            "artifacts_failed": 0,
        }
        for artifact in artifacts:
            service.delete_edges_by_artifact(artifact.metadata.artifact_id)
        for artifact in artifacts:
            try:
                edges = self._build_edges_for_artifact(service, artifact, run_id)
                for edge in edges:
                    service.save_edge(edge)
                summary["artifacts_linked"] += 1
                summary["edges_created"] += len(edges)
            except Exception as exc:
                logger.warning("Linker.link_all: failed for %s (%s)", artifact.metadata.artifact_id, exc)
                summary["artifacts_failed"] += 1
        return summary

    def link_artifact(
        self,
        service: "KnowledgeService",
        artifact_id: str,
        run_id: str | None = None,
    ) -> list[GraphEdge]:
        artifact = service.get_artifact(artifact_id)
        if artifact is None:
            raise ValueError(f"Artifact '{artifact_id}' not found.")
        service.delete_edges_by_artifact(artifact_id)
        edges = self._build_edges_for_artifact(service, artifact, run_id)
        for edge in edges:
            service.save_edge(edge)
        return edges

    def related_artifacts(
        self,
        service: "KnowledgeService",
        artifact_id: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        from backend.app.services.graph.related import build_related_artifacts

        return build_related_artifacts(service, artifact_id, limit=limit)

    def _build_edges_for_artifact(
        self,
        service: "KnowledgeService",
        artifact: ArtifactRecord,
        run_id: str | None,
    ) -> list[GraphEdge]:
        chunks = sorted(
            service.list_chunks(artifact.metadata.artifact_id),
            key=lambda item: (item.chunk_index, item.chunk_id),
        )
        other_artifacts = {
            item.metadata.artifact_id: item
            for item in service.list_artifacts()
            if item.metadata.artifact_id != artifact.metadata.artifact_id
        }
        edges: dict[str, GraphEdge] = {}

        for chunk in chunks:
            self._add_edge(
                edges,
                from_id=artifact.metadata.artifact_id,
                to_id=chunk.chunk_id,
                edge_type=EdgeType.CONTAINS,
                evidence=f"Artifact contains chunk {chunk.chunk_index}.",
                run_id=run_id,
            )

        if self._settings.knowledge_linking_enable_jira_refs:
            self._link_jira_refs(edges, artifact, other_artifacts, run_id)

        self._link_same_project(edges, artifact, other_artifacts, run_id)
        if self._settings.knowledge_linking_enable_keyword_overlap:
            self._link_keyword_overlap(edges, artifact, other_artifacts, run_id)
        self._link_entity_matches(edges, artifact, other_artifacts, run_id)
        self._link_appian_refs(edges, artifact, chunks, other_artifacts, run_id)

        ordered = sorted(edges.values(), key=lambda item: (item.edge_type.value, item.from_id, item.to_id))
        max_related = max(1, self._settings.knowledge_linking_max_related_per_artifact)
        limited: list[GraphEdge] = []
        related_count = 0
        for edge in ordered:
            if edge.edge_type != EdgeType.CONTAINS:
                related_count += 1
            if edge.edge_type != EdgeType.CONTAINS and related_count > max_related:
                continue
            limited.append(edge)
        return limited

    def _link_jira_refs(
        self,
        edges: dict[str, GraphEdge],
        artifact: ArtifactRecord,
        other_artifacts: dict[str, ArtifactRecord],
        run_id: str | None,
    ) -> None:
        known_jira = {
            item.metadata.artifact_id.removeprefix("jira-").upper(): item
            for item in other_artifacts.values()
            if item.metadata.source_system == SourceSystem.JIRA
        }
        for entity in self._extractor.extract_from_artifact(artifact):
            target = known_jira.get(entity.upper())
            if target is None:
                continue
            self._add_edge(
                edges,
                from_id=artifact.metadata.artifact_id,
                to_id=target.metadata.artifact_id,
                edge_type=EdgeType.REFERENCES_ARTIFACT,
                evidence=f"Text mentions Jira key {entity}.",
                run_id=run_id,
            )

    def _link_same_project(
        self,
        edges: dict[str, GraphEdge],
        artifact: ArtifactRecord,
        other_artifacts: dict[str, ArtifactRecord],
        run_id: str | None,
    ) -> None:
        project_key = artifact.metadata.project_key
        if not project_key:
            return
        for other in other_artifacts.values():
            if other.metadata.project_key != project_key:
                continue
            self._add_edge(
                edges,
                from_id=artifact.metadata.artifact_id,
                to_id=other.metadata.artifact_id,
                edge_type=EdgeType.SAME_PROJECT,
                evidence=f"Artifacts share project key {project_key}.",
                run_id=run_id,
            )

    def _link_keyword_overlap(
        self,
        edges: dict[str, GraphEdge],
        artifact: ArtifactRecord,
        other_artifacts: dict[str, ArtifactRecord],
        run_id: str | None,
    ) -> None:
        base_keywords = set(self._tokenizer.extract_keywords(artifact.text_content, limit=12))
        if not base_keywords:
            return
        threshold = max(1, self._settings.knowledge_linking_overlap_threshold)
        for other in other_artifacts.values():
            if not (
                other.metadata.source_system == artifact.metadata.source_system
                or (
                    artifact.metadata.project_key
                    and other.metadata.project_key == artifact.metadata.project_key
                )
            ):
                continue
            overlap = sorted(base_keywords & set(self._tokenizer.extract_keywords(other.text_content, limit=12)))
            if len(overlap) < threshold:
                continue
            self._add_edge(
                edges,
                from_id=artifact.metadata.artifact_id,
                to_id=other.metadata.artifact_id,
                edge_type=EdgeType.RELATED_TO,
                evidence=f"Keyword overlap: {', '.join(overlap[:5])}.",
                run_id=run_id,
            )

    def _link_entity_matches(
        self,
        edges: dict[str, GraphEdge],
        artifact: ArtifactRecord,
        other_artifacts: dict[str, ArtifactRecord],
        run_id: str | None,
    ) -> None:
        entities = {entity.casefold(): entity for entity in self._extractor.extract_from_artifact(artifact)}
        if not entities:
            return
        for other in other_artifacts.values():
            candidates = {
                other.metadata.artifact_id.casefold(),
                other.metadata.title.casefold(),
            }
            match = next((entities[key] for key in candidates if key in entities), None)
            if match is None:
                continue
            self._add_edge(
                edges,
                from_id=artifact.metadata.artifact_id,
                to_id=other.metadata.artifact_id,
                edge_type=EdgeType.MENTIONS,
                evidence=f"Entity match on '{match}'.",
                run_id=run_id,
            )

    def _link_appian_refs(
        self,
        edges: dict[str, GraphEdge],
        artifact: ArtifactRecord,
        chunks: list[ChunkRecord],
        other_artifacts: dict[str, ArtifactRecord],
        run_id: str | None,
    ) -> None:
        if artifact.metadata.source_system != SourceSystem.APPIAN:
            return

        package_name = Path(artifact.extra.get("original_path", "")).stem.casefold()
        refs = list(artifact.extra.get("extracted_refs", []))
        for chunk in chunks:
            refs.extend(self._extractor.extract_from_chunk(chunk))
        normalized_refs = {ref.casefold(): ref for ref in refs}

        for other in other_artifacts.values():
            if other.metadata.source_system != SourceSystem.APPIAN:
                continue
            other_package = Path(other.extra.get("original_path", "")).stem.casefold()
            if package_name and other_package and package_name == other_package:
                self._add_edge(
                    edges,
                    from_id=artifact.metadata.artifact_id,
                    to_id=other.metadata.artifact_id,
                    edge_type=EdgeType.SAME_APPIAN_PACKAGE,
                    evidence=f"Artifacts originated from package {Path(artifact.extra.get('original_path', '')).stem}.",
                    run_id=run_id,
                )

            candidates = {
                other.metadata.artifact_id.casefold(),
                other.metadata.title.casefold(),
            }
            match = next((normalized_refs[key] for key in candidates if key in normalized_refs), None)
            if match is None:
                continue
            edge_type = (
                EdgeType.CALLS
                if other.metadata.artifact_kind.value == "integration"
                else EdgeType.USES_OBJECT
            )
            self._add_edge(
                edges,
                from_id=artifact.metadata.artifact_id,
                to_id=other.metadata.artifact_id,
                edge_type=edge_type,
                evidence=f"Appian reference match on '{match}'.",
                run_id=run_id,
            )

    def _add_edge(
        self,
        edges: dict[str, GraphEdge],
        *,
        from_id: str,
        to_id: str,
        edge_type: EdgeType,
        evidence: str,
        run_id: str | None,
    ) -> None:
        if edge_type in self._SYMMETRIC_EDGE_TYPES and to_id < from_id:
            from_id, to_id = to_id, from_id
        if from_id == to_id and edge_type != EdgeType.CONTAINS:
            return
        edge_id = _edge_id(edge_type, from_id, to_id)
        edges[edge_id] = GraphEdge(
            edge_id=edge_id,
            from_id=from_id,
            to_id=to_id,
            edge_type=edge_type,
            source="rule_based_linker",
            evidence=evidence,
            ingestion_run_id=run_id,
        )
