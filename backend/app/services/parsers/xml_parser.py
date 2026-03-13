"""
Baseline XML parsing helpers for Appian export ingestion.

This parser is intentionally conservative and schema-agnostic. It extracts a
readable text representation plus deterministic metadata fields that are useful
for search, inspection, and rule-based linking.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

logger = logging.getLogger(__name__)

_REF_ATTR_NAMES = ("ref", "reference", "id", "key", "uuid", "name", "identifier", "target")
_NAME_ATTR_NAMES = ("name", "displayName", "display-name", "label", "title", "key", "id")


def _local_name(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[-1]
    return tag


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _guess_object_type(root_tag: str, object_name: str | None, source_name: str) -> str:
    basis = " ".join(part for part in [root_tag, object_name or "", source_name] if part).lower()
    if "interface" in basis or "ui" in basis:
        return "interface"
    if "process" in basis or "workflow" in basis:
        return "process_model"
    if "integration" in basis or "connected-system" in basis:
        return "integration"
    if "application" in basis or "package" in basis:
        return "application"
    if "datatype" in basis or "recordtype" in basis or "xsd" in basis:
        return "data_type"
    if "constant" in basis or "config" in basis or "setting" in basis:
        return "config"
    if "rule" in basis or "expression" in basis:
        return "rule"
    return "unknown"


def parse_xml_source(
    *,
    path: Path | None = None,
    xml_bytes: bytes | None = None,
    source_name: str = "",
) -> tuple[str, dict[str, Any]]:
    """Parse XML from *path* or *xml_bytes* and return `(text_content, metadata)`."""
    if path is None and xml_bytes is None:
        raise ValueError("parse_xml_source requires either path or xml_bytes.")

    try:
        if xml_bytes is not None:
            root = ET.fromstring(xml_bytes)
        else:
            assert path is not None
            root = ET.parse(path).getroot()
    except Exception as exc:
        logger.warning("xml_parser: failed to parse %s (%s)", source_name or path, exc)
        raise

    root_tag = _local_name(root.tag)
    attributes: dict[str, str] = {}
    child_tags: list[str] = []
    identifiers: list[str] = []
    extracted_refs: list[str] = []
    flattened_lines: list[str] = [f"Root: {root_tag}"]
    object_name: str | None = None

    for attr_name, attr_value in sorted(root.attrib.items()):
        clean = _clean(attr_value)
        if not clean:
            continue
        attributes[attr_name] = clean
        if object_name is None and attr_name in _NAME_ATTR_NAMES:
            object_name = clean
        if attr_name.lower() in _REF_ATTR_NAMES:
            extracted_refs.append(clean)
        if attr_name.lower() in {"id", "key", "uuid", "name"}:
            identifiers.append(clean)

    for element in root.iter():
        tag_name = _local_name(element.tag)
        if element is not root:
            child_tags.append(tag_name)

        for attr_name, attr_value in sorted(element.attrib.items()):
            clean = _clean(attr_value)
            if not clean:
                continue
            if object_name is None and attr_name in _NAME_ATTR_NAMES:
                object_name = clean
            if attr_name.lower() in _REF_ATTR_NAMES:
                extracted_refs.append(clean)
            if attr_name.lower() in {"id", "key", "uuid", "name"}:
                identifiers.append(clean)

        text_value = _clean(element.text or "")
        if text_value:
            flattened_lines.append(f"{tag_name}: {text_value}")
            if object_name is None and tag_name.lower() in {"name", "label", "title"}:
                object_name = text_value
            if tag_name.lower() in {"ref", "reference", "identifier", "key", "uuid"}:
                extracted_refs.append(text_value)
                identifiers.append(text_value)

    object_name = object_name or (path.stem if path is not None else None) or root_tag
    metadata = {
        "root_tag": root_tag,
        "object_name": object_name,
        "object_type_guess": _guess_object_type(root_tag, object_name, source_name),
        "attributes": attributes,
        "child_tags": sorted(dict.fromkeys(child_tags)),
        "extracted_refs": list(dict.fromkeys(value for value in extracted_refs if value)),
        "identifiers": list(dict.fromkeys(value for value in identifiers if value)),
    }
    return "\n".join(dict.fromkeys(flattened_lines)), metadata
