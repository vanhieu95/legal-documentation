from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, tzinfo
from decimal import Decimal

import pytest
from django.utils import timezone, translation

from apps.core.legal_formatters import (
    LEGAL_FORMATTER_VERSION,
    LegalBreakKind,
    LegalFormatError,
    ReviewedCurrencyWords,
    XMLSafeLegalText,
    format_legal_address,
    format_legal_currency,
    format_legal_date,
    format_legal_datetime,
    format_legal_identifier,
    format_legal_multiline,
    format_legal_name,
    format_legal_organization_name,
    format_legal_person_name,
    get_legal_formatters,
)


def test_vietnamese_legal_date_retains_the_raw_value() -> None:
    raw = date(2026, 12, 8)

    result = format_legal_date(raw)

    assert result.raw is raw
    assert result.formatted == "ngày 08 tháng 12 năm 2026"
    assert result.version == LEGAL_FORMATTER_VERSION


@pytest.mark.parametrize("invalid", [datetime(2026, 1, 1), "2026-01-01", None])
def test_legal_date_rejects_non_date_only_values(invalid: object) -> None:
    with pytest.raises(LegalFormatError):
        format_legal_date(invalid)  # type: ignore[arg-type]


def test_legal_datetime_converts_utc_to_ho_chi_minh_time() -> None:
    raw = datetime(2026, 12, 8, 17, 45, tzinfo=UTC)

    result = format_legal_datetime(raw)

    assert result.raw is raw
    assert result.formatted == "00 giờ 45 phút, ngày 09 tháng 12 năm 2026"


def test_legal_datetime_rejects_naive_values() -> None:
    with pytest.raises(LegalFormatError):
        format_legal_datetime(datetime(2026, 12, 8, 17, 45))


@pytest.mark.parametrize(
    "invalid",
    [
        datetime.max.replace(tzinfo=UTC),
        datetime(2026, 1, 1, 0, 0, 1, tzinfo=UTC),
        datetime(2026, 1, 1, 0, 0, 0, 1, tzinfo=UTC),
    ],
)
def test_legal_datetime_rejects_unrepresentable_or_subminute_values(
    invalid: datetime,
) -> None:
    with pytest.raises(LegalFormatError):
        format_legal_datetime(invalid)


class _MissingOffset(tzinfo):
    def utcoffset(self, value: datetime | None) -> None:
        return None

    def dst(self, value: datetime | None) -> None:
        return None


class _BrokenOffset(tzinfo):
    def utcoffset(self, value: datetime | None) -> timedelta:
        raise RuntimeError("synthetic timezone failure")

    def dst(self, value: datetime | None) -> None:
        return None


@pytest.mark.parametrize("zone", [_MissingOffset(), _BrokenOffset()])
def test_legal_datetime_wraps_invalid_timezone_behavior(zone: tzinfo) -> None:
    with pytest.raises(LegalFormatError):
        format_legal_datetime(datetime(2026, 1, 1, tzinfo=zone))


def test_date_only_value_is_timezone_invariant() -> None:
    raw = date(2026, 1, 1)
    with timezone.override("Pacific/Kiritimati"):
        assert format_legal_date(raw).formatted == "ngày 01 tháng 01 năm 2026"


def test_formatter_version_must_be_selected_explicitly() -> None:
    formatter = get_legal_formatters(LEGAL_FORMATTER_VERSION)

    assert formatter.version == LEGAL_FORMATTER_VERSION
    assert formatter.date(date(2026, 1, 2)).formatted == "ngày 02 tháng 01 năm 2026"

    with pytest.raises(LegalFormatError):
        get_legal_formatters("vi-legal-v999")


@pytest.mark.parametrize(
    "raw",
    ["Nguyễn Thị Minh Châu", "NGUYỄN VĂN AN", "NgUyễn Văn A"],
)
def test_authoritative_names_preserve_diacritics_and_case(raw: str) -> None:
    assert format_legal_name(raw).formatted == raw


def test_person_and_organization_name_interfaces_preserve_authoritative_values() -> None:
    person = "NGUYỄN Thị Ánh"
    organization = "CÔNG TY Luật TNHH Ánh Dương"

    assert format_legal_person_name(person).formatted == person
    assert format_legal_organization_name(organization).formatted == organization


def test_name_preserves_the_administrator_approved_unicode_normalization() -> None:
    decomposed = "Nguye\u0302\u0303n"

    result = format_legal_name(decomposed)

    assert result.raw == decomposed
    assert result.formatted == decomposed


def test_name_normalizes_only_horizontal_whitespace() -> None:
    result = format_legal_name("  NGUYỄN\t  VĂN AN  ")

    assert result.raw == "  NGUYỄN\t  VĂN AN  "
    assert result.formatted == "NGUYỄN VĂN AN"


@pytest.mark.parametrize("raw", ["", "   ", "Name\nSecond", "Name\x00"])
def test_name_rejects_empty_multiline_or_control_text(raw: str) -> None:
    with pytest.raises(LegalFormatError):
        format_legal_name(raw)


def test_address_trims_and_joins_only_supplied_components() -> None:
    raw = (" 12 Đường A ", None, " Phường B  ", "Quận C")

    result = format_legal_address(raw)

    assert result.raw is raw
    assert result.formatted == "12 Đường A, Phường B, Quận C"
    assert "tỉnh" not in result.formatted.casefold()


def test_missing_address_components_remain_missing() -> None:
    assert format_legal_address(("Thôn 1", None, "")).formatted == "Thôn 1"


def test_address_requires_typed_bounded_components_and_joined_output() -> None:
    with pytest.raises(LegalFormatError):
        format_legal_address(["Thôn 1"])  # type: ignore[arg-type]
    with pytest.raises(LegalFormatError):
        format_legal_address(tuple("x" * 500 for _ in range(5)))
    with pytest.raises(LegalFormatError):
        format_legal_address((None,) * 33)


@pytest.mark.parametrize(
    "raw",
    ["01/2026/QĐST-VDS", "SYN-CASE-000001", "ĐS-01.2026", "CASE:01 (#1)"],
)
def test_identifier_validation_and_formatting_are_deterministic(raw: str) -> None:
    result = format_legal_identifier(raw)

    assert result.raw == raw
    assert result.formatted == raw


def test_identifier_preserves_authoritative_unicode_normalization() -> None:
    decomposed = "ĐS-Nguye\u0302\u0303n"
    assert format_legal_identifier(decomposed).formatted == decomposed


@pytest.mark.parametrize("raw", ["", "   ", "CASE\n01", "x" * 129])
def test_invalid_identifiers_fail_predictably(raw: str) -> None:
    with pytest.raises(LegalFormatError):
        format_legal_identifier(raw)


@pytest.mark.parametrize(
    ("amount", "numeric", "words"),
    [
        (Decimal("0"), "0", "không"),
        (Decimal("15"), "15", "mười lăm"),
        (Decimal("24"), "24", "hai mươi tư"),
        (Decimal("25"), "25", "hai mươi lăm"),
        (Decimal("20"), "20", "hai mươi"),
        (Decimal("21"), "21", "hai mươi mốt"),
        (Decimal("26"), "26", "hai mươi sáu"),
        (Decimal("10"), "10", "mười"),
        (Decimal("11"), "11", "mười một"),
        (Decimal("101000"), "101000", "một trăm lẻ một nghìn"),
        (Decimal("1000001"), "1000001", "một triệu không trăm lẻ một"),
        (Decimal("1001"), "1001", "một nghìn không trăm lẻ một"),
        (
            Decimal("999999999999999"),
            "999999999999999",
            "chín trăm chín mươi chín nghìn tỷ chín trăm chín mươi chín tỷ "
            "chín trăm chín mươi chín triệu chín trăm chín mươi chín nghìn "
            "chín trăm chín mươi chín",
        ),
    ],
)
def test_numeric_currency_and_vietnamese_words_are_distinct(
    amount: Decimal, numeric: str, words: str
) -> None:
    result = format_legal_currency(amount)

    assert result.raw is amount
    assert result.numeric == numeric
    assert result.words == words
    assert result.reviewed_words_override is None


@pytest.mark.parametrize(
    "amount",
    [
        Decimal("1.25"),
        Decimal("-1"),
        Decimal("NaN"),
        Decimal("1000000000000000"),
        1,
    ],
)
def test_currency_rejects_invalid_precision_and_negative_values(amount: object) -> None:
    with pytest.raises(LegalFormatError):
        format_legal_currency(amount)  # type: ignore[arg-type]


def test_reviewed_currency_words_override_does_not_change_numeric_value() -> None:
    amount = Decimal("105")
    override = ReviewedCurrencyWords("  một trăm   lẻ năm  ")

    result = format_legal_currency(
        amount,
        reviewed_words_override=override,
    )

    assert result.raw is amount
    assert result.numeric == "105"
    assert result.generated_words == "một trăm lẻ năm"
    assert result.words == "một trăm lẻ năm"
    assert result.reviewed_words_override == "một trăm lẻ năm"
    assert result.raw_reviewed_words_override == "  một trăm   lẻ năm  "


def test_equivalent_integral_decimal_precision_is_accepted() -> None:
    result = format_legal_currency(Decimal("1.0"))

    assert result.raw == Decimal("1.0")
    assert result.numeric == "1"


def test_currency_words_override_must_be_nonempty_single_line_text() -> None:
    with pytest.raises(LegalFormatError):
        format_legal_currency(Decimal("1"), reviewed_words_override=ReviewedCurrencyWords("   "))
    with pytest.raises(LegalFormatError):
        format_legal_currency(
            Decimal("1"),
            reviewed_words_override="không typed",  # type: ignore[arg-type]
        )


def test_multiline_text_preserves_only_the_approved_line_breaks_and_escapes_xml() -> None:
    raw = '  Dòng <một> & "hai"  \r\n{{ user.password }}'

    result = format_legal_multiline(raw, break_kind=LegalBreakKind.LINE)

    assert result.raw == raw
    assert result.break_kind is LegalBreakKind.LINE
    assert result.escaped_segments == (
        "Dòng &lt;một&gt; &amp; &quot;hai&quot;",
        "&#123;&#123; user.password &#125;&#125;",
    )
    assert not hasattr(result, "__html__")


def test_xml_safe_adapter_cannot_be_constructed_directly() -> None:
    with pytest.raises(TypeError):
        XMLSafeLegalText(  # type: ignore[call-arg]
            raw="hostile", escaped_segments=("<w:r/>",), break_kind=LegalBreakKind.LINE
        )


@pytest.mark.parametrize("invalid", ["text\ud800", "text\ufffe", "text\u2028next"])
def test_multiline_adapter_rejects_xml_invalid_or_unapproved_separators(
    invalid: str,
) -> None:
    with pytest.raises(LegalFormatError):
        format_legal_multiline(invalid, break_kind=LegalBreakKind.LINE)


def test_line_adapter_preserves_leading_and_trailing_approved_breaks() -> None:
    result = format_legal_multiline("\nNội dung\n", break_kind=LegalBreakKind.LINE)

    assert result.escaped_segments == ("", "Nội dung", "")


def test_multiline_adapter_accepts_xml_valid_private_and_astral_characters() -> None:
    result = format_legal_multiline("\ue000 😀", break_kind=LegalBreakKind.LINE)

    assert result.escaped_segments == ("\ue000 😀",)


def test_multiline_adapter_is_immutable() -> None:
    result = format_legal_multiline("Nội dung", break_kind=LegalBreakKind.LINE)

    with pytest.raises(AttributeError):
        result.raw = "changed"  # type: ignore[misc]


def test_paragraph_adapter_collapses_wrapped_lines_but_preserves_paragraph_breaks() -> None:
    result = format_legal_multiline(
        "Đoạn một\ndòng tiếp\n\n\nĐoạn hai",
        break_kind=LegalBreakKind.PARAGRAPH,
    )

    assert result.escaped_segments == ("Đoạn một dòng tiếp", "Đoạn hai")


def test_paragraph_adapter_collapses_consecutive_whitespace_only_blank_lines() -> None:
    result = format_legal_multiline(
        "Đoạn một\n\n \n\nĐoạn hai", break_kind=LegalBreakKind.PARAGRAPH
    )

    assert result.escaped_segments == ("Đoạn một", "Đoạn hai")


def test_multiline_adapter_rejects_an_unapproved_break_kind() -> None:
    with pytest.raises(LegalFormatError):
        format_legal_multiline("Text", break_kind="html")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "formatter, value",
    [
        (format_legal_name, "x" * 501),
        (format_legal_address, ("x" * 501,)),
        (format_legal_multiline, "x" * 16_385),
    ],
)
def test_legal_text_outputs_are_bounded(formatter: object, value: object) -> None:
    with pytest.raises(LegalFormatError):
        if formatter is format_legal_multiline:
            format_legal_multiline(value, break_kind=LegalBreakKind.LINE)  # type: ignore[arg-type]
        else:
            formatter(value)  # type: ignore[operator]


def test_ui_locale_cannot_change_legal_output() -> None:
    raw_date = date(2026, 9, 13)
    raw_amount = Decimal("1021")
    with translation.override("vi"):
        vietnamese = (format_legal_date(raw_date), format_legal_currency(raw_amount))
    with translation.override("en"):
        alternate = (format_legal_date(raw_date), format_legal_currency(raw_amount))

    assert alternate == vietnamese


def test_formatter_values_do_not_repr_sensitive_legal_text() -> None:
    name = format_legal_name("Nguyễn Văn Bí Mật")
    multiline = format_legal_multiline("Nội dung bí mật", break_kind=LegalBreakKind.LINE)
    override = ReviewedCurrencyWords("một nội dung bí mật")
    currency = format_legal_currency(Decimal("1"), reviewed_words_override=override)

    assert "Nguyễn Văn Bí Mật" not in repr(name)
    assert "Nội dung bí mật" not in repr(multiline)
    assert "một nội dung bí mật" not in repr(override)
    assert "một nội dung bí mật" not in repr(currency)
