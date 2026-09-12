from __future__ import annotations

import math
from dataclasses import dataclass

MEBIBYTE = 1024 * 1024
MAX_TEMPLATE_BYTES = 10 * MEBIBYTE
MAX_PACKAGE_FINDINGS = 50


@dataclass(frozen=True, slots=True)
class PackageValidationLimits:
    """Fail-closed resource limits for untrusted OPC packages."""

    max_compressed_bytes: int = MAX_TEMPLATE_BYTES
    max_entries: int = 512
    max_total_uncompressed_bytes: int = 50 * MEBIBYTE
    max_entry_uncompressed_bytes: int = 10 * MEBIBYTE
    max_compression_ratio: float = 100.0
    max_xml_bytes: int = 2 * MEBIBYTE
    max_xml_depth: int = 64

    def __post_init__(self) -> None:
        integer_limits = (
            self.max_compressed_bytes,
            self.max_entries,
            self.max_total_uncompressed_bytes,
            self.max_entry_uncompressed_bytes,
            self.max_xml_bytes,
            self.max_xml_depth,
        )
        invalid_integer = any(
            isinstance(value, bool) or not isinstance(value, int) or value <= 0
            for value in integer_limits
        )
        invalid_ratio = (
            isinstance(self.max_compression_ratio, bool)
            or not isinstance(self.max_compression_ratio, (int, float))
            or not math.isfinite(self.max_compression_ratio)
            or self.max_compression_ratio <= 0
        )
        if invalid_integer or invalid_ratio:
            raise ValueError("Package validation limits must be positive finite values.")


DEFAULT_PACKAGE_LIMITS = PackageValidationLimits()


@dataclass(frozen=True, slots=True)
class TemplateValidationLimits:
    """Fail-closed parser limits for supported Word text parts."""

    max_source_characters: int = 256 * 1024
    max_tokens: int = 4096
    max_token_characters: int = 4096
    max_control_nesting: int = 32
    max_ast_nodes: int = 8192
    max_ast_depth: int = 64

    def __post_init__(self) -> None:
        if any(
            isinstance(value, bool) or not isinstance(value, int) or value <= 0
            for value in (
                self.max_source_characters,
                self.max_tokens,
                self.max_token_characters,
                self.max_control_nesting,
                self.max_ast_nodes,
                self.max_ast_depth,
            )
        ):
            raise ValueError("Template validation limits must be positive integers.")


DEFAULT_TEMPLATE_LIMITS = TemplateValidationLimits()
