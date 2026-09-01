from __future__ import annotations

import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_ci_quality_gate_is_complete_and_blocking() -> None:
    workflow_path = PROJECT_ROOT / ".github" / "workflows" / "ci.yml"

    assert workflow_path.is_file(), "The required GitHub Actions workflow is missing."

    workflow = workflow_path.read_text(encoding="utf-8")
    required_fragments = (
        "permissions:\n  contents: read",
        "persist-credentials: false",
        "postgres:",
        "image: postgres:",
        'python-version: "3.13"',
        'node-version: "22"',
        "python -m pip install --require-hashes -r requirements/development.txt",
        "npm ci",
        "python manage.py migrate --noinput",
        "pytest --cov=apps --cov-branch --cov-report=term-missing",
        "python scripts/check_sensitive_coverage.py",
        "ruff check .",
        "ruff format --check .",
        "mypy apps config",
        "python manage.py check",
        "python manage.py makemigrations --check --dry-run",
        "npm run css:build",
        "python manage.py makemessages --all --no-obsolete",
        "python manage.py compilemessages",
        "python manage.py check --deploy --settings=config.settings.production",
        "python manage.py collectstatic --noinput",
        "npm run browser:test",
    )

    for fragment in required_fragments:
        assert fragment in workflow, f"CI is missing required blocking gate: {fragment}"

    action_references = re.findall(r"^\s*uses:\s*([^\s#]+)", workflow, flags=re.MULTILINE)
    assert action_references
    assert all(re.search(r"@[0-9a-f]{40}$", reference) for reference in action_references)
    assert "continue-on-error" not in workflow
    assert "pull_request_target" not in workflow
    assert "upload-artifact" not in workflow


def test_test_harness_exposes_required_foundation_helpers() -> None:
    conftest = (PROJECT_ROOT / "tests" / "conftest.py").read_text(encoding="utf-8")
    pytest_config = (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert "enforce_csrf_checks=True" in conftest
    assert "user_factory" in conftest
    assert '"postgresql:' in pytest_config
    assert "fail_under = 85" in pytest_config
    assert (PROJECT_ROOT / "scripts" / "check_sensitive_coverage.py").is_file()
    assert (PROJECT_ROOT / "tests" / "browser" / "smoke.spec.js").is_file()
