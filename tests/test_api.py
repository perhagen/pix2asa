"""Tests for pix2asa.api — FastAPI endpoints."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pix2asa import __version__
from pix2asa.api import app
from pix2asa.models import TARGET_DEVICES

from .conftest import opts

# Inline config shared across API tests
_SIMPLE_PIX6 = """\
PIX Version 6.3(1)
interface ethernet0 auto
interface ethernet1 100full
nameif ethernet0 outside security0
nameif ethernet1 inside security100
ip address outside 10.0.0.1 255.255.255.0
ip address inside 192.168.1.1 255.255.255.0
fixup protocol ftp 21
fixup protocol http 80
: end
"""


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


# ---------------------------------------------------------------------------
# GET /api/version
# ---------------------------------------------------------------------------

class TestVersionEndpoint:
    def test_status_200(self, client):
        r = client.get("/api/version")
        assert r.status_code == 200

    def test_version_matches_package(self, client):
        assert client.get("/api/version").json()["version"] == __version__

    def test_response_schema(self, client):
        body = client.get("/api/version").json()
        assert set(body.keys()) == {"version"}


# ---------------------------------------------------------------------------
# GET /api/devices
# ---------------------------------------------------------------------------

class TestDevicesEndpoint:
    def test_status_200(self, client):
        assert client.get("/api/devices").status_code == 200

    def test_returns_list(self, client):
        body = client.get("/api/devices").json()
        assert isinstance(body, list)

    def test_count_matches_registry(self, client):
        body = client.get("/api/devices").json()
        assert len(body) == len(TARGET_DEVICES)

    def test_device_schema(self, client):
        device = client.get("/api/devices").json()[0]
        assert "slug" in device
        assert "display_name" in device
        assert "interfaces" in device
        assert "max_vlans" in device

    def test_known_platform_present(self, client):
        slugs = {d["slug"] for d in client.get("/api/devices").json()}
        assert "asa-5520" in slugs
        assert "asa-5505" in slugs
        assert "custom" in slugs

    def test_interfaces_is_list(self, client):
        for dev in client.get("/api/devices").json():
            assert isinstance(dev["interfaces"], list)

    def test_max_vlans_positive(self, client):
        for dev in client.get("/api/devices").json():
            if dev["slug"] != "custom":
                assert dev["max_vlans"] > 0


# ---------------------------------------------------------------------------
# POST /api/convert — success paths
# ---------------------------------------------------------------------------

class TestConvertEndpoint:
    def _convert(self, client, config=_SIMPLE_PIX6, platform="asa-5520",
                 src=6, tgt=84, **kwargs):
        return client.post("/api/convert", json={
            "config": config,
            "target_platform": platform,
            "source_version": src,
            "target_version": tgt,
            **kwargs,
        })

    def test_status_200(self, client):
        assert self._convert(client).status_code == 200

    def test_output_starts_with_asa_version(self, client):
        body = self._convert(client).json()
        assert body["output"].startswith("ASA Version 8.4")

    def test_output_field_present(self, client):
        body = self._convert(client).json()
        assert "output" in body
        assert isinstance(body["output"], str)
        assert len(body["output"]) > 0

    def test_log_field_present(self, client):
        body = self._convert(client).json()
        assert "log" in body
        assert isinstance(body["log"], str)

    def test_warnings_field_is_list(self, client):
        body = self._convert(client).json()
        assert isinstance(body["warnings"], list)

    def test_errors_field_is_list(self, client):
        body = self._convert(client).json()
        assert isinstance(body["errors"], list)

    def test_nameif_in_output(self, client):
        body = self._convert(client).json()
        assert "nameif outside" in body["output"]
        assert "nameif inside" in body["output"]

    def test_policy_map_in_output(self, client):
        body = self._convert(client).json()
        assert "policy-map global_policy" in body["output"]

    def test_asa84_version_header(self, client):
        body = self._convert(client, tgt=84).json()
        assert body["output"].startswith("ASA Version 8.4")

    def test_interface_map_applied(self, client):
        _imap_config = (
            "PIX Version 6.3(1)\n"
            "interface ethernet0 auto\n"
            "interface ethernet1 100full\n"
            "nameif ethernet0 outside security0\n"
            "nameif ethernet1 inside security100\n"
            "ip address outside 10.0.0.1 255.255.255.0\n"
            "ip address inside 192.168.1.1 255.255.255.0\n"
        )
        body = client.post("/api/convert", json={
            "config": _imap_config,
            "target_platform": "",
            "source_version": 6,
            "target_version": 84,
            "interface_map": {
                "ethernet0": "GigabitEthernet0/0",
                "ethernet1": "GigabitEthernet0/1",
            },
        }).json()
        assert "interface GigabitEthernet0/0" in body["output"]

    def test_pix7_source(self, client):
        pix7_config = """\
ASA Version 7.0(1)
interface GigabitEthernet0/0
 nameif outside
 security-level 0
 ip address 10.0.0.1 255.255.255.0
 no shutdown
!
: end
"""
        r = client.post("/api/convert", json={
            "config": pix7_config,
            "target_platform": "asa-5520",
            "source_version": 7,
            "target_version": 84,
        })
        assert r.status_code == 200

    @pytest.mark.integration
    def test_real_pix501(self, client, pix501_config):
        body = self._convert(client, config=pix501_config, platform="asa-5505").json()
        assert body["output"].startswith("ASA Version")
        assert "nameif outside" in body["output"]


# ---------------------------------------------------------------------------
# POST /api/convert — validation errors
# ---------------------------------------------------------------------------

class TestConvertValidation:
    def test_invalid_source_version(self, client):
        r = client.post("/api/convert", json={
            "config": _SIMPLE_PIX6,
            "target_platform": "asa-5520",
            "source_version": 5,
            "target_version": 84,
        })
        assert r.status_code == 422

    def test_invalid_target_version(self, client):
        r = client.post("/api/convert", json={
            "config": _SIMPLE_PIX6,
            "target_platform": "asa-5520",
            "source_version": 6,
            "target_version": 99,
        })
        assert r.status_code == 422

    def test_invalid_platform(self, client):
        r = client.post("/api/convert", json={
            "config": _SIMPLE_PIX6,
            "target_platform": "asa-9999-nonexistent",
            "source_version": 6,
            "target_version": 84,
        })
        assert r.status_code == 422
        assert "asa-9999-nonexistent" in r.json()["detail"]

    def test_missing_config_field(self, client):
        r = client.post("/api/convert", json={
            "target_platform": "asa-5520",
            "source_version": 6,
            "target_version": 84,
        })
        assert r.status_code == 422

    def test_empty_config_still_200(self, client):
        r = client.post("/api/convert", json={
            "config": "",
            "target_platform": "asa-5520",
            "source_version": 6,
            "target_version": 84,
        })
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# OpenAPI / docs
# ---------------------------------------------------------------------------

class TestOpenAPI:
    def test_openapi_json_accessible(self, client):
        r = client.get("/openapi.json")
        assert r.status_code == 200
        schema = r.json()
        assert "paths" in schema
        assert "/api/convert" in schema["paths"]
        assert "/api/version" in schema["paths"]
        assert "/api/devices" in schema["paths"]
