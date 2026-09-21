from __future__ import annotations

import re
import unicodedata
import uuid
from pathlib import PurePosixPath
from uuid import UUID

_CONTROL_CHARACTERS = re.compile(r"[\x00-\x1f\x7f]")
_WINDOWS_UNSAFE_CHARACTERS = re.compile(r'[<>:"/\\|?*]')
_WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{number}" for number in range(1, 10)),
    *(f"LPT{number}" for number in range(1, 10)),
}
MAX_DISPLAY_FILENAME_LENGTH = 150
_TYPE_KEY = re.compile(r"^(?:vds-[0-9]{2}|synthetic-[a-z0-9]+(?:-[a-z0-9]+)*)$")
_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def build_template_storage_key(type_key: str, version: str) -> str:
    """Return an opaque application-owned key under the template namespace."""
    if not _TYPE_KEY.fullmatch(type_key) or not _VERSION.fullmatch(version):
        raise ValueError("Template storage key components must be stable safe identifiers.")
    return f"templates/{type_key}/{version}/{uuid.uuid4().hex}.docx"


def build_generated_storage_key(case_id: UUID, attempt_id: UUID) -> str:
    """Return an opaque unique key scoped to one case and immutable attempt."""
    return f"generated/{case_id}/{attempt_id}/{uuid.uuid4().hex}.docx"


def build_generated_display_filename(proposed: str, attempt_id: UUID) -> str:
    """Build a unique NFC display filename safe across supported desktop platforms."""
    if not isinstance(proposed, str):
        raise ValueError("The generated display filename must be text.")
    leaf_name = PurePosixPath(proposed.replace("\\", "/")).name
    normalized = unicodedata.normalize("NFC", leaf_name)
    cleaned = _WINDOWS_UNSAFE_CHARACTERS.sub("", _CONTROL_CHARACTERS.sub("", normalized))
    cleaned = " ".join(cleaned.split()).strip(" .")
    stem = cleaned[:-5] if cleaned.casefold().endswith(".docx") else cleaned
    stem = stem.strip(" .") or "document"
    if stem.split(".", 1)[0].upper() in _WINDOWS_RESERVED_NAMES:
        stem = f"template-{stem}"
    suffix = f"-{attempt_id.hex[:8]}.docx"
    return f"{stem[: MAX_DISPLAY_FILENAME_LENGTH - len(suffix)]}{suffix}"


def sanitize_template_display_filename(filename: str) -> str:
    """Return a bounded display name; this value is never used as a storage path."""
    leaf_name = PurePosixPath(filename.replace("\\", "/")).name
    cleaned = " ".join(_CONTROL_CHARACTERS.sub("", leaf_name).split()).strip(" .")
    if not cleaned:
        cleaned = "template.docx"

    stem, separator, suffix = cleaned.rpartition(".")
    if not separator:
        stem, suffix = cleaned, ""
    if stem.upper() in _WINDOWS_RESERVED_NAMES:
        stem = f"template-{stem}"
    cleaned = f"{stem}.{suffix}" if suffix else stem

    if len(cleaned) > MAX_DISPLAY_FILENAME_LENGTH:
        extension = ".docx" if cleaned.lower().endswith(".docx") else ""
        cleaned = f"{cleaned[: MAX_DISPLAY_FILENAME_LENGTH - len(extension)]}{extension}"
    return cleaned
