from __future__ import annotations

from importlib.metadata import version


def test_runtime_dependency_versions_are_locked() -> None:
    assert version("Django") == "5.2.17"
    assert version("psycopg") == "3.3.4"
    assert version("docxtpl") == "0.20.2"
    assert version("python-docx") == "1.2.0"
