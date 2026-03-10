"""Shared pytest fixtures for the pix2asa test suite."""

from __future__ import annotations

import pathlib
import pytest

from pix2asa.context import ConversionContext
from pix2asa.converter import ConversionOptions, convert
from pix2asa.models import SourceVersion, TargetVersion


CONFIGS_DIR = pathlib.Path(__file__).parent.parent / "configs"


# ---------------------------------------------------------------------------
# pytest CLI option (must be in conftest.py to be registered at collection)
# ---------------------------------------------------------------------------

def pytest_addoption(parser):
    parser.addoption(
        "--live-server", default=None, metavar="URL",
        help="Base URL of a running pix2asa server for live client tests",
    )


@pytest.fixture(scope="session")
def live_server_url(request):
    return request.config.getoption("--live-server")


# ---------------------------------------------------------------------------
# Context helpers
# ---------------------------------------------------------------------------

@pytest.fixture()
def ctx6() -> ConversionContext:
    """A fresh PIX 6 → ASA 8.4+ ConversionContext."""
    return ConversionContext(
        source_version=SourceVersion.PIX6,
        target_version=TargetVersion.ASA84,
        target_platform="asa-5520",
    )


@pytest.fixture()
def ctx7() -> ConversionContext:
    """A fresh PIX 7 → ASA 8.4+ ConversionContext."""
    return ConversionContext(
        source_version=SourceVersion.PIX7,
        target_version=TargetVersion.ASA84,
        target_platform="asa-5520",
    )


@pytest.fixture()
def dispatcher6(ctx6):
    """A Dispatcher built for PIX 6."""
    from pix2asa.actions import build_dispatcher
    return build_dispatcher(ctx6)


@pytest.fixture()
def dispatcher7(ctx7):
    """A Dispatcher built for PIX 7."""
    from pix2asa.actions import build_dispatcher
    return build_dispatcher(ctx7)


# ---------------------------------------------------------------------------
# Conversion option helpers
# ---------------------------------------------------------------------------

def opts(platform="asa-5520", src=6, tgt=84, **kwargs) -> ConversionOptions:
    """Build ConversionOptions with convenient defaults."""
    return ConversionOptions(
        target_platform=platform,
        source_version=SourceVersion.PIX6 if src == 6 else SourceVersion.PIX7,
        target_version=TargetVersion.ASA84,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Config file fixtures
# ---------------------------------------------------------------------------

def _load(filename: str) -> str:
    path = CONFIGS_DIR / filename
    return path.read_text(encoding="utf-8", errors="replace")


@pytest.fixture()
def pix501_config() -> str:
    return _load("PIX501conf2003Aug13.txt")


@pytest.fixture()
def pix515_fo_config() -> str:
    return _load("515-fo.cfg")


@pytest.fixture()
def pix535_config() -> str:
    return _load("pix535.txt")


@pytest.fixture()
def pix38_config() -> str:
    return _load("pix38.txt")


@pytest.fixture()
def pix525_latin1_config() -> str:
    return _load("PIX-525-fake-FO.txt")


@pytest.fixture()
def conduit_config() -> str:
    return _load("conduit.txt")


@pytest.fixture()
def pix535_trunk_config() -> str:
    return _load("pix-535_with_trunk.cfg")
