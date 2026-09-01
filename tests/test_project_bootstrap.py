from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class ProjectBootstrapTests(unittest.TestCase):
    def test_required_scaffold_files_exist(self) -> None:
        required_paths = (
            "manage.py",
            "config/__init__.py",
            "config/asgi.py",
            "config/urls.py",
            "config/wsgi.py",
            "apps/__init__.py",
            "apps/core/__init__.py",
            "apps/accounts/__init__.py",
            "apps/audit/__init__.py",
            "apps/cases/__init__.py",
            "apps/documents/__init__.py",
            "requirements/base.in",
            "requirements/base.txt",
            "requirements/development.in",
            "requirements/development.txt",
            "requirements/production.in",
            "requirements/production.txt",
            "pyproject.toml",
            "package.json",
            "package-lock.json",
            ".python-version",
            ".env.example",
            "README.md",
        )

        missing = [path for path in required_paths if not (PROJECT_ROOT / path).is_file()]

        self.assertEqual(missing, [])

    def test_python_version_targets_current_3_13_patch(self) -> None:
        version = (PROJECT_ROOT / ".python-version").read_text(encoding="utf-8").strip()

        self.assertEqual(version, "3.13.15")

    def test_direct_python_dependencies_are_exactly_pinned(self) -> None:
        requirement_inputs = (
            PROJECT_ROOT / "requirements/base.in",
            PROJECT_ROOT / "requirements/development.in",
        )

        for requirement_file in requirement_inputs:
            with self.subTest(requirement_file=requirement_file.name):
                for line in requirement_file.read_text(encoding="utf-8").splitlines():
                    stripped = line.strip()
                    if not stripped or stripped.startswith(("#", "-r")):
                        continue
                    self.assertRegex(
                        stripped,
                        re.compile(r"^[A-Za-z0-9_.-]+(?:\[[A-Za-z0-9_,.-]+\])?==[^=]+$"),
                    )

    def test_frontend_dependencies_and_commands_are_pinned(self) -> None:
        package = json.loads((PROJECT_ROOT / "package.json").read_text(encoding="utf-8"))

        self.assertEqual(package["engines"]["node"], ">=22.0.0")
        self.assertEqual(
            package["scripts"]["css:build"],
            "tailwindcss -i static_src/css/app.css -o static/css/app.css --minify",
        )
        self.assertEqual(
            package["scripts"]["css:watch"],
            "tailwindcss -i static_src/css/app.css -o static/css/app.css --watch",
        )
        for version in package["devDependencies"].values():
            self.assertRegex(version, re.compile(r"^\d+\.\d+\.\d+$"))


if __name__ == "__main__":
    unittest.main()
