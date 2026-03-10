"""Playwright end-to-end tests for the pix2asa React UI.

Prerequisites:
    pip install pytest-playwright
    playwright install chromium

Run with:
    pytest tests/test_frontend.py -v

The Vite dev server must be running on port 5173 (proxies /api/* to :8000),
and the FastAPI server must be running on port 8000.

    pix2asa --serve 8000 &
    cd ui && npm run dev &

To target production (FastAPI serving the built SPA):
    BASE_URL=http://localhost:8000 pytest tests/test_frontend.py -v

# pyproject.toml / pytest.ini marker registration:
# [tool.pytest.ini_options]
# markers = ["frontend: marks tests as frontend/E2E tests (skipped when server not running)"]
"""

from __future__ import annotations

import os
import socket

import pytest
from playwright.sync_api import Page, expect

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_URL = os.environ.get("BASE_URL", "http://localhost:5173")

# Minimal PIX 6 config that produces a valid ASA conversion
_PIX_CONFIG = """\
PIX Version 6.3(5)
hostname pix-test
interface ethernet0
nameif ethernet0 outside security0
ip address ethernet0 203.0.113.1 255.255.255.0
interface ethernet1
nameif ethernet1 inside security100
ip address ethernet1 10.0.0.1 255.255.255.0
"""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _server_is_up(host: str, port: int, timeout: float = 1.0) -> bool:
    """Return True if a TCP connection to host:port succeeds."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _require_servers(page: Page) -> None:
    """Skip the test if either required server is not reachable."""
    # Check the UI server
    from urllib.parse import urlparse
    parsed = urlparse(BASE_URL)
    ui_host = parsed.hostname or "localhost"
    ui_port = parsed.port or 5173
    if not _server_is_up(ui_host, ui_port):
        pytest.skip(f"UI server not reachable at {BASE_URL} — start with: cd ui && npm run dev")
    # Check the API server (always :8000)
    if not _server_is_up("localhost", 8000):
        pytest.skip("API server not reachable at http://localhost:8000 — start with: pix2asa --serve 8000")


def _navigate_to_step4(page: Page, config: str = _PIX_CONFIG) -> None:
    """Walk the wizard from Step 1 through Step 4, entering *config* along the way."""
    page.goto(BASE_URL)
    page.wait_for_load_state("networkidle")

    # Step 1 — paste config
    textarea = page.locator("textarea").first
    textarea.fill(config)
    page.get_by_role("button", name="Next").click()

    # Step 2 — device selector; accept default and proceed
    page.wait_for_selector("text=Step 2")
    page.get_by_role("button", name="Next").click()

    # Step 3 — interface mapper; accept auto-mapping and proceed
    page.wait_for_selector("text=Step 3")
    page.get_by_role("button", name="Next").click()

    # Step 4 — conversion panel
    page.wait_for_selector("text=Step 4")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_page_loads(page: Page) -> None:
    """The app loads and shows the Step 1 panel."""
    _require_servers(page)

    page.goto(BASE_URL)
    page.wait_for_load_state("networkidle")

    # Title or header should contain the app name
    title = page.title()
    assert "pix2asa" in title.lower(), f"Unexpected page title: {title!r}"

    # Step 1 panel must be visible
    expect(page.get_by_text("Step 1", exact=False)).to_be_visible()

    # The config textarea must be present
    expect(page.locator("textarea").first).to_be_visible()


def test_full_wizard_flow(page: Page) -> None:
    """Walk all 4 wizard steps and verify a successful conversion."""
    _require_servers(page)

    _navigate_to_step4(page)

    # Verify the Debug checkbox is present and check it
    debug_checkbox = page.locator("input[type='checkbox']").filter(
        has=page.locator("xpath=following-sibling::*[contains(text(),'NAT')]")
    ).first
    # Fallback: find by label text
    debug_label = page.locator("label", has_text="NAT translation")
    debug_input = debug_label.locator("input[type='checkbox']")
    if debug_input.count() == 0:
        # Try sibling approach: find the checkbox next to "Debug:" label
        debug_input = page.locator("label:has-text('Debug') ~ label input[type='checkbox']")
    if debug_input.count() > 0:
        if not debug_input.is_checked():
            debug_input.check()

    # Click the convert button (labelled "Make target configuration")
    convert_btn = page.get_by_role("button", name="Make target configuration")
    expect(convert_btn).to_be_visible()
    convert_btn.click()

    # Wait for conversion to complete — the result buttons should appear
    page.wait_for_selector("text=View target config", timeout=15_000)

    # "View target config" button must be visible
    expect(page.get_by_role("button", name="View target config")).to_be_visible()

    # Open the target config modal and verify ASA content
    page.get_by_role("button", name="View target config").click()

    # The modal/viewer should show "ASA Version"
    page.wait_for_selector("text=ASA Version", timeout=5_000)
    expect(page.get_by_text("ASA Version", exact=False)).to_be_visible()

    # Close the modal (press Escape or click a close button)
    page.keyboard.press("Escape")


def test_view_log(page: Page) -> None:
    """After conversion, the log viewer shows INFO: messages."""
    _require_servers(page)

    _navigate_to_step4(page)

    # Convert
    page.get_by_role("button", name="Make target configuration").click()
    page.wait_for_selector("text=View log", timeout=15_000)

    # Open log viewer
    page.get_by_role("button", name="View log").click()
    page.wait_for_selector("text=INFO:", timeout=5_000)
    expect(page.get_by_text("INFO:", exact=False)).to_be_visible()

    page.keyboard.press("Escape")


def test_debug_log_shows_nat_table(page: Page) -> None:
    """When debug is enabled the log contains the NAT Translation Table header."""
    _require_servers(page)

    # Use a config that includes a static NAT + conduit so the table is populated
    pix_with_nat = _PIX_CONFIG + (
        "static (inside,outside) 203.0.113.10 10.0.0.10 netmask 255.255.255.255\n"
        "conduit permit tcp host 203.0.113.10 eq 80 any\n"
    )
    _navigate_to_step4(page, config=pix_with_nat)

    # Ensure Debug checkbox is checked (it defaults to true in the app, but be explicit)
    debug_label = page.locator("label", has_text="NAT translation")
    debug_input = debug_label.locator("input[type='checkbox']")
    if debug_input.count() > 0 and not debug_input.is_checked():
        debug_input.check()

    page.get_by_role("button", name="Make target configuration").click()
    page.wait_for_selector("text=View log", timeout=15_000)

    page.get_by_role("button", name="View log").click()
    page.wait_for_selector("text=NAT Translation Table", timeout=5_000)
    expect(page.get_by_text("NAT Translation Table", exact=False)).to_be_visible()

    page.keyboard.press("Escape")


def test_convert_button_disabled_on_empty_config(page: Page) -> None:
    """The convert button is disabled (or shows an error) when no config is entered."""
    _require_servers(page)

    # Navigate to step 4 with an empty config
    _navigate_to_step4(page, config="")

    convert_btn = page.get_by_role("button", name="Make target configuration")
    expect(convert_btn).to_be_visible()

    # The button should be disabled when config is empty
    assert convert_btn.is_disabled(), (
        "Expected convert button to be disabled with empty config"
    )


def test_view_source_config(page: Page) -> None:
    """View source config button shows the original PIX config in the modal."""
    _require_servers(page)

    _navigate_to_step4(page)

    page.get_by_role("button", name="Make target configuration").click()
    page.wait_for_selector("text=View source config", timeout=15_000)

    page.get_by_role("button", name="View source config").click()
    # The original PIX hostname should appear in the modal
    page.wait_for_selector("text=pix-test", timeout=5_000)
    expect(page.get_by_text("pix-test", exact=False)).to_be_visible()

    page.keyboard.press("Escape")


def test_step_navigation(page: Page) -> None:
    """Back/Next buttons navigate correctly between steps."""
    _require_servers(page)

    page.goto(BASE_URL)
    page.wait_for_load_state("networkidle")

    # Should start at Step 1
    expect(page.get_by_text("Step 1", exact=False)).to_be_visible()

    # Enter config and go to Step 2
    page.locator("textarea").first.fill(_PIX_CONFIG)
    page.get_by_role("button", name="Next").click()
    page.wait_for_selector("text=Step 2")
    expect(page.get_by_text("Step 2", exact=False)).to_be_visible()

    # Go back to Step 1
    page.get_by_role("button", name="Back").click()
    page.wait_for_selector("text=Step 1")
    expect(page.get_by_text("Step 1", exact=False)).to_be_visible()

    # Config text should still be there
    textarea_value = page.locator("textarea").first.input_value()
    assert "PIX Version" in textarea_value, "Config was cleared when navigating back"
