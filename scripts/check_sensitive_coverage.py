from __future__ import annotations

import json
import sys
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from coverage import Coverage

SENSITIVE_BRANCH_THRESHOLD = 95.0
SENSITIVE_MODULE_TERMS = (
    "context",
    "integrity",
    "permission",
    "policy",
    "registry",
    "render",
    "snapshot",
)


def is_sensitive_module(filename: str) -> bool:
    path = Path(filename)
    return path.parts[0] == "apps" and any(
        term in path.stem.lower() for term in SENSITIVE_MODULE_TERMS
    )


def branch_percentage(summary: Mapping[str, Any]) -> float:
    branch_count = int(summary.get("num_branches", 0))
    if branch_count == 0:
        return 100.0
    return 100.0 * int(summary.get("covered_branches", 0)) / branch_count


def main() -> int:
    coverage = Coverage()
    coverage.load()
    with tempfile.TemporaryDirectory(prefix="vds-sensitive-coverage-") as temporary_directory:
        report_path = Path(temporary_directory) / "coverage.json"
        coverage.json_report(outfile=str(report_path))
        report = json.loads(report_path.read_text(encoding="utf-8"))

    sensitive_files = {
        filename: branch_percentage(details["summary"])
        for filename, details in report["files"].items()
        if is_sensitive_module(filename)
    }
    if not sensitive_files:
        print("Sensitive-module coverage gate: no matching modules exist yet; threshold is armed.")
        return 0

    failures = {
        filename: percentage
        for filename, percentage in sensitive_files.items()
        if percentage < SENSITIVE_BRANCH_THRESHOLD
    }
    for filename, percentage in sorted(sensitive_files.items()):
        print(f"Sensitive-module branch coverage: {filename} {percentage:.2f}%")
    if failures:
        print(
            f"Sensitive modules must reach {SENSITIVE_BRANCH_THRESHOLD:.0f}% branch coverage.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
