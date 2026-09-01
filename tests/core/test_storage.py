from __future__ import annotations

import importlib
import stat
from pathlib import Path

import pytest
from django.conf import settings
from django.core.checks import Tags, run_checks
from django.core.files.base import ContentFile
from django.core.files.storage import storages
from django.test import override_settings
from django.urls import Resolver404, resolve


def test_private_storage_alias_has_no_public_url() -> None:
    storage = storages["private"]

    assert Path(storage.location).resolve() == Path(settings.PRIVATE_STORAGE_ROOT).resolve()
    with pytest.raises(ValueError, match="not accessible via a URL"):
        storage.url("synthetic/document.docx")


def test_private_storage_creates_restrictive_files_and_directories(tmp_path: Path) -> None:
    storage_module = importlib.import_module("apps.core.storage")
    storage = storage_module.PrivateFileSystemStorage(location=tmp_path)

    saved_name = storage.save("nested/synthetic.bin", ContentFile(b"synthetic"))

    assert saved_name == "nested/synthetic.bin"
    assert stat.S_IMODE(Path(storage.path(saved_name)).stat().st_mode) == 0o600
    assert stat.S_IMODE((tmp_path / "nested").stat().st_mode) == 0o700


def test_private_storage_is_not_exposed_by_root_urls() -> None:
    with pytest.raises(Resolver404):
        resolve("/private/synthetic.docx")
    with pytest.raises(Resolver404):
        resolve("/media/synthetic.docx")


def test_deploy_check_rejects_private_static_path_overlap() -> None:
    assert not [
        message
        for message in run_checks(tags=[Tags.security], include_deployment_checks=True)
        if message.id.startswith("core.")
    ]

    with override_settings(PRIVATE_STORAGE_ROOT=settings.STATIC_ROOT):
        errors = run_checks(tags=[Tags.security], include_deployment_checks=True)

    assert "core.E001" in {message.id for message in errors}
