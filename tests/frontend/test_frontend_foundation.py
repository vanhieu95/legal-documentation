from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterator
from pathlib import Path

from django.test import Client

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _relative_luminance(color: str) -> float:
    channels: Iterator[float] = (int(color[index : index + 2], 16) / 255 for index in (1, 3, 5))
    linear_channels = [
        channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4
        for channel in channels
    ]
    return 0.2126 * linear_channels[0] + 0.7152 * linear_channels[1] + 0.0722 * linear_channels[2]


def _contrast_ratio(first: str, second: str) -> float:
    lighter, darker = sorted(
        (_relative_luminance(first), _relative_luminance(second)), reverse=True
    )
    return (lighter + 0.05) / (darker + 0.05)


def test_frontend_dependencies_use_pinned_csp_safe_local_builds() -> None:
    package = json.loads((PROJECT_ROOT / "package.json").read_text(encoding="utf-8"))
    dependencies = package["devDependencies"]

    assert dependencies["htmx.org"] == "2.0.10"
    assert dependencies["@alpinejs/csp"].startswith("3.")
    assert "alpinejs" not in dependencies
    assert package["scripts"]["assets:vendor"]
    assert package["scripts"]["assets:verify"]
    assert "vite" not in json.dumps(package).lower()


def test_vendored_assets_match_recorded_provenance_and_checksums() -> None:
    manifest_path = PROJECT_ROOT / "static" / "vendor" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert manifest["schema"] == 1
    assert {asset["package"] for asset in manifest["assets"]} == {
        "@alpinejs/csp",
        "htmx.org",
    }
    for asset in manifest["assets"]:
        asset_path = PROJECT_ROOT / asset["destination"]
        assert asset_path.is_file()
        assert asset["source"].startswith("node_modules/")
        assert re.fullmatch(r"sha256:[0-9a-f]{64}", asset["checksum"])
        actual_checksum = hashlib.sha256(asset_path.read_bytes()).hexdigest()
        assert asset["checksum"] == f"sha256:{actual_checksum}"


def test_css_exposes_design_tokens_and_accessibility_foundations() -> None:
    css = (PROJECT_ROOT / "static_src" / "css" / "app.css").read_text(encoding="utf-8")
    required_fragments = (
        "--color-primary: #2563eb",
        "--color-success: #16a34a",
        "--color-danger: #dc2626",
        "--color-warning: #d97706",
        "--color-info: #0284c7",
        "--color-text-strong: #18181b",
        "--color-screen: #f8fafc",
        "--color-surface: #ffffff",
        "--space-1: 4px",
        "--space-2: 8px",
        "--space-3: 12px",
        "--space-4: 16px",
        "--space-6: 24px",
        "--space-8: 32px",
        "Inter, ui-sans-serif, system-ui",
        "prefers-color-scheme: dark",
        'data-theme="light"',
        'data-theme="dark"',
        "prefers-reduced-motion: reduce",
        "forced-colors: active",
        ":focus-visible",
        ".no-js",
    )

    for fragment in required_fragments:
        assert fragment in css, f"Missing design-system CSS contract: {fragment}"


def test_essential_token_pairs_meet_wcag_contrast() -> None:
    normal_text_pairs = (
        ("#18181b", "#ffffff"),
        ("#27272a", "#ffffff"),
        ("#71717a", "#ffffff"),
        ("#ffffff", "#2563eb"),
        ("#ffffff", "#dc2626"),
        ("#fafafa", "#18181b"),
        ("#f4f4f5", "#18181b"),
        ("#09090b", "#60a5fa"),
    )
    focus_pairs = (("#2563eb", "#ffffff"), ("#60a5fa", "#18181b"))

    assert all(_contrast_ratio(*pair) >= 4.5 for pair in normal_text_pairs)
    assert all(_contrast_ratio(*pair) >= 3 for pair in focus_pairs)


def test_application_javascript_disables_sensitive_browser_state() -> None:
    javascript = (PROJECT_ROOT / "static_src" / "js" / "app.js").read_text(encoding="utf-8")

    assert "historyEnabled: false" in javascript
    assert "historyCacheSize: 0" in javascript
    assert "allowEval: false" in javascript
    assert "allowScriptTags: false" in javascript
    assert "includeIndicatorStyles: false" in javascript
    assert "selfRequestsOnly: true" in javascript
    assert 'const themeStorageKey = "vds-theme"' in javascript
    assert "localStorage.setItem(themeStorageKey, themeChoice)" in javascript
    assert "localStorage.removeItem(themeStorageKey)" in javascript
    assert "sessionStorage.setItem" not in javascript
    assert 'sessionStorage.removeItem("htmx-current-path-for-history")' in javascript
    assert "eval(" not in javascript
    assert "new Function" not in javascript


def test_component_gallery_is_semantic_local_and_usable_without_javascript() -> None:
    response = Client().get("/foundation/components/")
    html = response.content.decode()

    assert response.status_code == 200
    assert '<html lang="vi" class="no-js"' in html
    assert '<main id="main-content"' in html
    assert 'class="skip-link"' in html
    assert 'role="alert"' in html
    assert 'role="status"' in html
    assert 'aria-live="polite"' in html
    assert "aria-describedby=" in html
    assert "aria-invalid=" in html
    assert "<table" in html
    assert "<caption" in html
    assert "<dialog" in html
    assert "Trạng thái tải" in html
    assert "Chưa có dữ liệu" in html
    assert "Thành công" in html
    assert "Cảnh báo" in html
    assert "Có lỗi xảy ra" in html
    assert 'hx-history="false"' in html
    assert "https://" not in html
    assert "http://" not in html
    assert "localStorage" not in html
    assert "sessionStorage" not in html


def test_login_frontend_has_responsive_focus_and_busy_state_contracts() -> None:
    css = (PROJECT_ROOT / "static_src" / "css" / "app.css").read_text(encoding="utf-8")
    javascript = (PROJECT_ROOT / "static_src" / "js" / "app.js").read_text(encoding="utf-8")

    for selector in (
        ".auth-page",
        ".auth-card",
        ".auth-error-summary",
        ".auth-submit",
        ".submit-loading",
    ):
        assert selector in css
    assert "[data-error-summary]" in javascript
    assert "errorSummary.focus()" in javascript
    assert "[data-submit-form]" in javascript
    assert "submitButton.disabled = true" in javascript
