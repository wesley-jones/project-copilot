"""
Appian ingestion source for baseline XML and ZIP export normalization.

Phase 3 keeps this intentionally lightweight: XML is parsed generically and
converted into searchable ArtifactRecords with conservative metadata guesses.
"""
from __future__ import annotations

import logging
from pathlib import Path
import re
from typing import Any
import zipfile

from backend.app.config import get_settings
from backend.app.services.graph.models import (
    ArtifactKind,
    ArtifactMetadata,
    ArtifactRecord,
    SourceSystem,
    SourceType,
)
from backend.app.services.ingestion.base import BaseIngestionSource
from backend.app.services.ingestion.raw_store import get_raw_store
from backend.app.services.parsers.xml_parser import parse_xml_source

logger = logging.getLogger(__name__)


def _sanitize_part(value: str) -> str:
    sanitized = re.sub(r"[^\w-]+", "-", value.replace("\\", "/").strip().lower())
    sanitized = re.sub(r"-{2,}", "-", sanitized).strip("-")
    return sanitized or "unknown"


def _artifact_kind_from_guess(guess: str, source_name: str) -> ArtifactKind:
    basis = f"{guess} {source_name}".lower()
    if "application" in basis or "package" in basis:
        return ArtifactKind.APPLICATION
    if "interface" in basis:
        return ArtifactKind.INTERFACE
    if "process" in basis or "workflow" in basis:
        return ArtifactKind.PROCESS_MODEL
    if "integration" in basis or "connected-system" in basis:
        return ArtifactKind.INTEGRATION
    if "datatype" in basis or "type" in basis:
        return ArtifactKind.DATA_TYPE
    if "config" in basis or "constant" in basis:
        return ArtifactKind.CONFIG
    if "rule" in basis or "expression" in basis:
        return ArtifactKind.RULE
    return ArtifactKind.UNKNOWN


class AppianIngestionSource(BaseIngestionSource):
    """Scan Appian XML files and ZIP exports into normalized ArtifactRecords."""

    @property
    def source_name(self) -> str:
        return "appian"

    @property
    def source_type(self) -> SourceType:
        return SourceType.XML

    def health_check(self) -> bool:
        return get_settings().knowledge_appian_exports_dir.exists()

    def fetch_artifacts(self, run_id: str, **kwargs: Any) -> list[ArtifactRecord]:
        settings = get_settings()
        root = Path(kwargs["root_dir"]) if kwargs.get("root_dir") else settings.knowledge_appian_exports_dir
        recursive = (
            kwargs["recursive"] if "recursive" in kwargs and kwargs["recursive"] is not None
            else settings.knowledge_appian_extract_recursive
        )
        project_key = kwargs.get("project_key") or settings.knowledge_default_project_key
        raw_store = get_raw_store() if settings.knowledge_raw_capture_enabled else None

        if not root.exists():
            logger.warning("AppianIngestionSource: root dir does not exist: %s", root)
            return []

        pattern = "**/*" if recursive else "*"
        candidates = sorted(
            path for path in root.glob(pattern)
            if path.is_file() and path.suffix.lower() in {".xml", ".zip"}
        )
        artifacts: list[ArtifactRecord] = []
        raw_refs_by_source: dict[Path, str] = {}

        for file_path in candidates:
            try:
                file_size = file_path.stat().st_size
                if file_size > settings.knowledge_appian_max_file_bytes:
                    logger.warning(
                        "AppianIngestionSource: skipping %s - size %d exceeds limit of %d bytes",
                        file_path,
                        file_size,
                        settings.knowledge_appian_max_file_bytes,
                    )
                    continue

                raw_ref = self._get_raw_ref(run_id, file_path, raw_store, raw_refs_by_source)
                if file_path.suffix.lower() == ".xml":
                    artifact = self._artifact_from_xml_path(
                        run_id=run_id,
                        root=root,
                        file_path=file_path,
                        project_key=project_key,
                        raw_ref=raw_ref,
                    )
                    if artifact is not None:
                        artifacts.append(artifact)
                else:
                    artifacts.extend(
                        self._artifacts_from_zip(
                            run_id=run_id,
                            root=root,
                            zip_path=file_path,
                            project_key=project_key,
                            raw_ref=raw_ref,
                            max_bytes=settings.knowledge_appian_max_file_bytes,
                        )
                    )
            except Exception as exc:
                logger.warning("AppianIngestionSource: skipping %s (%s)", file_path, exc)
        return artifacts

    def _get_raw_ref(
        self,
        run_id: str,
        file_path: Path,
        raw_store,
        raw_refs_by_source: dict[Path, str],
    ) -> str | None:
        if raw_store is None:
            return None
        if file_path in raw_refs_by_source:
            return raw_refs_by_source[file_path]
        raw_ref = raw_store.save_appian_raw(run_id, file_path, file_path.name)
        raw_refs_by_source[file_path] = raw_ref
        return raw_ref

    def _artifact_from_xml_path(
        self,
        *,
        run_id: str,
        root: Path,
        file_path: Path,
        project_key: str | None,
        raw_ref: str | None,
    ) -> ArtifactRecord | None:
        text_content, metadata = parse_xml_source(path=file_path, source_name=file_path.name)
        artifact_id = f"appian-{_sanitize_part(file_path.relative_to(root).with_suffix('').as_posix())}"
        return self._build_artifact(
            run_id=run_id,
            artifact_id=artifact_id,
            title=metadata.get("object_name") or file_path.stem,
            text_content=text_content,
            metadata=metadata,
            project_key=project_key,
            external_id=str(file_path),
            raw_ref=raw_ref,
            original_path=str(file_path),
            zip_member=None,
            source_name=file_path.name,
        )

    def _artifacts_from_zip(
        self,
        *,
        run_id: str,
        root: Path,
        zip_path: Path,
        project_key: str | None,
        raw_ref: str | None,
        max_bytes: int,
    ) -> list[ArtifactRecord]:
        artifacts: list[ArtifactRecord] = []
        try:
            with zipfile.ZipFile(zip_path) as archive:
                for member in sorted(archive.namelist()):
                    if member.endswith("/") or not member.lower().endswith(".xml"):
                        continue
                    info = archive.getinfo(member)
                    if info.file_size > max_bytes:
                        logger.warning(
                            "AppianIngestionSource: skipping %s in %s - size %d exceeds limit",
                            member,
                            zip_path.name,
                            info.file_size,
                        )
                        continue
                    try:
                        xml_bytes = archive.read(member)
                        text_content, metadata = parse_xml_source(
                            xml_bytes=xml_bytes,
                            source_name=f"{zip_path.name}:{member}",
                        )
                        artifact = self._build_artifact(
                            run_id=run_id,
                            artifact_id=(
                                f"appian-{_sanitize_part(zip_path.stem)}-"
                                f"{_sanitize_part(Path(member).with_suffix('').as_posix())}"
                            ),
                            title=metadata.get("object_name") or Path(member).stem,
                            text_content=text_content,
                            metadata=metadata,
                            project_key=project_key,
                            external_id=f"{zip_path}#{member}",
                            raw_ref=f"{raw_ref}#member={member}" if raw_ref else None,
                            original_path=str(zip_path),
                            zip_member=member,
                            source_name=member,
                        )
                        artifacts.append(artifact)
                    except Exception as exc:
                        logger.warning(
                            "AppianIngestionSource: skipping %s in %s (%s)",
                            member,
                            zip_path,
                            exc,
                        )
        except zipfile.BadZipFile as exc:
            logger.warning("AppianIngestionSource: invalid zip %s (%s)", zip_path, exc)
        return artifacts

    def _build_artifact(
        self,
        *,
        run_id: str,
        artifact_id: str,
        title: str,
        text_content: str,
        metadata: dict[str, Any],
        project_key: str | None,
        external_id: str,
        raw_ref: str | None,
        original_path: str,
        zip_member: str | None,
        source_name: str,
    ) -> ArtifactRecord:
        object_name = metadata.get("object_name") or title
        object_type_guess = metadata.get("object_type_guess", "unknown")
        artifact_kind = _artifact_kind_from_guess(object_type_guess, source_name)
        return ArtifactRecord(
            metadata=ArtifactMetadata(
                artifact_id=artifact_id,
                source_type=SourceType.XML,
                source_system=SourceSystem.APPIAN,
                external_id=external_id,
                project_key=project_key,
                title=object_name,
                artifact_kind=artifact_kind,
                ingestion_run_id=run_id,
            ),
            text_content=text_content,
            summary=object_name,
            raw_ref=raw_ref,
            extra={
                "original_path": original_path,
                "zip_member": zip_member,
                "root_tag": metadata.get("root_tag"),
                "object_name": object_name,
                "object_type_guess": object_type_guess,
                "extracted_refs": metadata.get("extracted_refs", []),
                "identifiers": metadata.get("identifiers", []),
                "child_tags": metadata.get("child_tags", []),
                "attributes": metadata.get("attributes", {}),
                "parser_used": "xml_parser",
            },
        )


def get_appian_ingestion_source() -> AppianIngestionSource:
    return AppianIngestionSource()
