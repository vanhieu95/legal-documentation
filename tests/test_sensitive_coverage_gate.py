from __future__ import annotations

import pytest

from scripts.check_sensitive_coverage import branch_percentage, is_sensitive_module


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("apps/documents/context_builder.py", True),
        ("apps/core/permissions.py", True),
        ("apps/documents/renderer.py", True),
        ("apps/cases/models.py", False),
        ("tests/test_permissions.py", False),
    ],
)
def test_sensitive_module_selection(filename: str, expected: bool) -> None:
    assert is_sensitive_module(filename) is expected


def test_branch_percentage_measures_branches_instead_of_combined_coverage() -> None:
    summary = {
        "num_statements": 100,
        "covered_statements": 100,
        "num_branches": 20,
        "covered_branches": 19,
    }

    assert branch_percentage(summary) == 95.0
