from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from zoneinfo import ZoneInfo

LEGAL_FORMATTER_VERSION = "vi-legal-v1"
LEGAL_TIME_ZONE = ZoneInfo("Asia/Ho_Chi_Minh")

MAX_NAME_LENGTH = 500
MAX_ADDRESS_COMPONENT_LENGTH = 500
MAX_ADDRESS_COMPONENTS = 32
MAX_ADDRESS_LENGTH = 2_000
MAX_IDENTIFIER_LENGTH = 128
MAX_CURRENCY_WORDS_LENGTH = 500
MAX_MULTILINE_TEXT_LENGTH = 16_384

_HORIZONTAL_WHITESPACE = re.compile(r"[\t ]+")
_PARAGRAPH_BREAK = re.compile(r"\n(?:[\t ]*\n)+")
_UNAPPROVED_LINE_SEPARATOR = re.compile(r"[\x85\u2028\u2029]")


class LegalFormatError(ValueError):
    """Raised when a raw value is outside the legal formatter contract."""


@dataclass(frozen=True, slots=True, repr=False)
class LegalFormattedValue[T]:
    raw: T
    formatted: str
    version: str = field(default=LEGAL_FORMATTER_VERSION, init=False)

    def __repr__(self) -> str:
        return f"{type(self).__name__}(version={self.version!r}, redacted=True)"


@dataclass(frozen=True, slots=True, repr=False)
class ReviewedCurrencyWords:
    """A typed marker for an administrator-reviewed currency-words value."""

    raw: str

    def __repr__(self) -> str:
        return f"{type(self).__name__}(redacted=True)"


@dataclass(frozen=True, slots=True, repr=False)
class LegalCurrencyValue:
    raw: Decimal
    numeric: str
    generated_words: str
    raw_reviewed_words_override: str | None
    reviewed_words_override: str | None
    version: str = field(default=LEGAL_FORMATTER_VERSION, init=False)

    @property
    def words(self) -> str:
        return self.reviewed_words_override or self.generated_words

    def __repr__(self) -> str:
        return f"{type(self).__name__}(version={self.version!r}, redacted=True)"


class LegalBreakKind(StrEnum):
    LINE = "line"
    PARAGRAPH = "paragraph"


class XMLSafeLegalText:
    """Unforgeable adapter produced only after bounded validation and escaping."""

    __slots__ = ("__raw", "__escaped_segments", "__break_kind")
    __raw: str
    __escaped_segments: tuple[str, ...]
    __break_kind: LegalBreakKind

    def __new__(cls, *, _validated: object | None = None) -> XMLSafeLegalText:
        if _validated is not _XML_SAFE_TOKEN:
            raise TypeError("XMLSafeLegalText must be created by format_legal_multiline().")
        return super().__new__(cls)

    @classmethod
    def _create(
        cls,
        *,
        raw: str,
        escaped_segments: tuple[str, ...],
        break_kind: LegalBreakKind,
    ) -> XMLSafeLegalText:
        instance = cls(_validated=_XML_SAFE_TOKEN)
        object.__setattr__(instance, "_XMLSafeLegalText__raw", raw)
        object.__setattr__(instance, "_XMLSafeLegalText__escaped_segments", escaped_segments)
        object.__setattr__(instance, "_XMLSafeLegalText__break_kind", break_kind)
        return instance

    @property
    def raw(self) -> str:
        return self.__raw

    @property
    def escaped_segments(self) -> tuple[str, ...]:
        return self.__escaped_segments

    @property
    def break_kind(self) -> LegalBreakKind:
        return self.__break_kind

    @property
    def version(self) -> str:
        return LEGAL_FORMATTER_VERSION

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("XMLSafeLegalText is immutable.")

    def __repr__(self) -> str:
        return f"{type(self).__name__}(version={self.version!r}, redacted=True)"


_XML_SAFE_TOKEN = object()


def _is_xml_10_character(character: str) -> bool:
    codepoint = ord(character)
    return (
        codepoint in (0x09, 0x0A, 0x0D)
        or 0x20 <= codepoint <= 0xD7FF
        or 0xE000 <= codepoint <= 0xFFFD
        or 0x10000 <= codepoint <= 0x10FFFF
    )


def _require_text(value: object, *, maximum: int, allow_newlines: bool = False) -> str:
    if (
        not isinstance(value, str)
        or len(value) > maximum
        or any(not _is_xml_10_character(character) for character in value)
        or _UNAPPROVED_LINE_SEPARATOR.search(value)
    ):
        raise LegalFormatError("The legal text value is invalid or exceeds its bound.")
    if not allow_newlines and ("\r" in value or "\n" in value):
        raise LegalFormatError("Line breaks are not allowed in this legal text value.")
    return value


def _normalize_horizontal_whitespace(value: str) -> str:
    return _HORIZONTAL_WHITESPACE.sub(" ", value).strip()


def format_legal_date(value: date) -> LegalFormattedValue[date]:
    if not isinstance(value, date) or isinstance(value, datetime):
        raise LegalFormatError("A date-only value is required.")
    return LegalFormattedValue(
        raw=value,
        formatted=f"ngày {value.day:02d} tháng {value.month:02d} năm {value.year:04d}",
    )


def format_legal_datetime(value: datetime) -> LegalFormattedValue[datetime]:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise LegalFormatError("A timezone-aware datetime is required.")
    if value.second or value.microsecond:
        raise LegalFormatError("Legal datetimes require exact minute precision.")
    try:
        if value.utcoffset() is None:
            raise LegalFormatError("A timezone-aware datetime is required.")
        local = value.astimezone(LEGAL_TIME_ZONE)
    except LegalFormatError:
        raise
    except Exception as error:
        raise LegalFormatError("The legal datetime cannot be represented.") from error
    return LegalFormattedValue(
        raw=value,
        formatted=(
            f"{local.hour:02d} giờ {local.minute:02d} phút, "
            f"ngày {local.day:02d} tháng {local.month:02d} năm {local.year:04d}"
        ),
    )


def format_legal_name(value: str) -> LegalFormattedValue[str]:
    raw = _require_text(value, maximum=MAX_NAME_LENGTH)
    formatted = _normalize_horizontal_whitespace(raw)
    if not formatted:
        raise LegalFormatError("A non-empty authoritative name is required.")
    return LegalFormattedValue(raw=raw, formatted=formatted)


def format_legal_person_name(value: str) -> LegalFormattedValue[str]:
    return format_legal_name(value)


def format_legal_organization_name(value: str) -> LegalFormattedValue[str]:
    return format_legal_name(value)


def format_legal_address(
    components: tuple[str | None, ...],
) -> LegalFormattedValue[tuple[str | None, ...]]:
    if not isinstance(components, tuple) or len(components) > MAX_ADDRESS_COMPONENTS:
        raise LegalFormatError("Address components must be supplied as a typed tuple.")
    normalized: list[str] = []
    for component in components:
        if component is None:
            continue
        raw_component = _require_text(component, maximum=MAX_ADDRESS_COMPONENT_LENGTH)
        if cleaned := _normalize_horizontal_whitespace(raw_component):
            normalized.append(cleaned)
    formatted = ", ".join(normalized)
    if len(formatted) > MAX_ADDRESS_LENGTH:
        raise LegalFormatError("The joined legal address exceeds its bound.")
    return LegalFormattedValue(raw=components, formatted=formatted)


def format_legal_identifier(value: str) -> LegalFormattedValue[str]:
    raw = _require_text(value, maximum=MAX_IDENTIFIER_LENGTH)
    formatted = _normalize_horizontal_whitespace(raw)
    if not formatted:
        raise LegalFormatError("A non-empty legal identifier is required.")
    return LegalFormattedValue(raw=raw, formatted=formatted)


_DIGITS = (
    "không",
    "một",
    "hai",
    "ba",
    "bốn",
    "năm",
    "sáu",
    "bảy",
    "tám",
    "chín",
)
_GROUP_SCALES = ("", "nghìn", "triệu", "tỷ", "nghìn tỷ")
_MAX_CURRENCY_AMOUNT = 999_999_999_999_999


def _read_under_thousand(value: int, *, include_zero_hundreds: bool) -> str:
    hundreds, remainder = divmod(value, 100)
    tens, units = divmod(remainder, 10)
    words: list[str] = []
    if hundreds or include_zero_hundreds:
        words.extend((_DIGITS[hundreds], "trăm"))
    if tens > 1:
        words.extend((_DIGITS[tens], "mươi"))
        if units == 1:
            words.append("mốt")
        elif units == 4:
            words.append("tư")
        elif units == 5:
            words.append("lăm")
        elif units:
            words.append(_DIGITS[units])
    elif tens == 1:
        words.append("mười")
        if units:
            words.append("lăm" if units == 5 else _DIGITS[units])
    elif units:
        if hundreds or include_zero_hundreds:
            words.append("lẻ")
        words.append(_DIGITS[units])
    return " ".join(words)


def _currency_words(value: int) -> str:
    if value == 0:
        return _DIGITS[0]
    groups: list[int] = []
    remaining = value
    while remaining:
        remaining, group = divmod(remaining, 1_000)
        groups.append(group)
    words: list[str] = []
    highest = len(groups) - 1
    for index in range(highest, -1, -1):
        group = groups[index]
        if group == 0:
            continue
        words.append(
            _read_under_thousand(
                group,
                include_zero_hundreds=index < highest and group < 100,
            )
        )
        if _GROUP_SCALES[index]:
            words.append(_GROUP_SCALES[index])
    return " ".join(words)


def format_legal_currency(
    value: Decimal,
    *,
    reviewed_words_override: ReviewedCurrencyWords | None = None,
) -> LegalCurrencyValue:
    if (
        not isinstance(value, Decimal)
        or not value.is_finite()
        or value != value.to_integral_value()
        or value < 0
        or value > _MAX_CURRENCY_AMOUNT
    ):
        raise LegalFormatError("The currency amount must be a supported non-negative integer.")
    integer = int(value)
    generated = _currency_words(integer)
    raw_reviewed: str | None = None
    reviewed: str | None = None
    if reviewed_words_override is not None:
        if not isinstance(reviewed_words_override, ReviewedCurrencyWords):
            raise LegalFormatError("A typed reviewed currency-word override is required.")
        raw_reviewed = reviewed_words_override.raw
        raw_override = _require_text(
            raw_reviewed,
            maximum=MAX_CURRENCY_WORDS_LENGTH,
        )
        reviewed = _normalize_horizontal_whitespace(raw_override)
        if not reviewed:
            raise LegalFormatError("A reviewed currency-word override cannot be empty.")
    return LegalCurrencyValue(
        raw=value,
        numeric=str(integer),
        generated_words=generated,
        raw_reviewed_words_override=raw_reviewed,
        reviewed_words_override=reviewed,
    )


def format_legal_multiline(
    value: str,
    *,
    break_kind: LegalBreakKind,
) -> XMLSafeLegalText:
    raw = _require_text(value, maximum=MAX_MULTILINE_TEXT_LENGTH, allow_newlines=True)
    try:
        selected_break = LegalBreakKind(break_kind)
    except (TypeError, ValueError) as error:
        raise LegalFormatError("The legal-text break kind is unsupported.") from error
    canonical = raw.replace("\r\n", "\n").replace("\r", "\n")
    if selected_break is LegalBreakKind.LINE:
        segments = tuple(_normalize_horizontal_whitespace(line) for line in canonical.split("\n"))
    else:
        paragraphs = _PARAGRAPH_BREAK.split(canonical)
        segments = tuple(
            _normalize_horizontal_whitespace(paragraph.replace("\n", " "))
            for paragraph in paragraphs
        )
    return XMLSafeLegalText._create(
        raw=raw,
        escaped_segments=tuple(_escape_word_xml_text(segment) for segment in segments),
        break_kind=selected_break,
    )


def _escape_word_xml_text(value: str) -> str:
    return html.escape(value, quote=True).replace("{", "&#123;").replace("}", "&#125;")


@dataclass(frozen=True, slots=True)
class VietnameseLegalFormattersV1:
    """Stable, explicitly selectable platform formatter contract, version 1."""

    version: str = field(default=LEGAL_FORMATTER_VERSION, init=False)

    date = staticmethod(format_legal_date)
    datetime = staticmethod(format_legal_datetime)
    person_name = staticmethod(format_legal_person_name)
    organization_name = staticmethod(format_legal_organization_name)
    address = staticmethod(format_legal_address)
    identifier = staticmethod(format_legal_identifier)
    currency = staticmethod(format_legal_currency)
    multiline = staticmethod(format_legal_multiline)


VIETNAMESE_LEGAL_FORMATTERS_V1 = VietnameseLegalFormattersV1()


def get_legal_formatters(version: str) -> VietnameseLegalFormattersV1:
    """Resolve a supported formatter contract without locale or mutable registry state."""

    if version != LEGAL_FORMATTER_VERSION:
        raise LegalFormatError("The legal formatter version is unsupported.")
    return VIETNAMESE_LEGAL_FORMATTERS_V1
