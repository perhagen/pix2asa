"""Tests for pix2asa.client — Pix2asaClient and CLI.

The client tests run in two modes:
  - Unit tests (default): use a mock HTTP server (no real server needed)
  - Live tests (opt-in):  use a real running server via --live-server pytest option

Live tests are skipped unless --live-server is passed:
    pytest tests/test_client.py --live-server http://localhost:8000
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

import pytest

from pix2asa import __version__
from pix2asa.client import (
    ClientError,
    Pix2asaClient,
    RemoteDevice,
    ServerUnavailableError,
    main,
)
from pix2asa.converter import ConversionResult
from pix2asa.models import SourceVersion, TargetVersion

from .conftest import opts


# ---------------------------------------------------------------------------
# Minimal mock HTTP server (stdlib only)
# ---------------------------------------------------------------------------

_DEVICES_PAYLOAD = [
    {"slug": "asa-5520", "display_name": "ASA 5520",
     "interfaces": ["GigabitEthernet0/0", "GigabitEthernet0/1"], "max_vlans": 150},
    {"slug": "asa-5505", "display_name": "ASA 5505",
     "interfaces": ["vlan1", "vlan2"], "max_vlans": 3},
]

_CONVERT_PAYLOAD = {
    "output": "ASA Version 7.2(2)\nhostname fw-migrated\n",
    "log": "INFO: PIX to ASA conversion tool\n",
    "warnings": [],
    "errors": [],
}


class _MockHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # silence request logging
        pass

    def do_GET(self):
        if self.path == "/api/version":
            self._json({"version": __version__})
        elif self.path == "/api/devices":
            self._json(_DEVICES_PAYLOAD)
        else:
            self._error(404, "Not found")

    def do_POST(self):
        if self.path == "/api/convert":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))
            # Return error for invalid source_version
            if body.get("source_version") not in (6, 7):
                self._error(422, "source_version must be 6 or 7")
            elif body.get("target_platform") == "bad-platform":
                self._error(422, "Unknown target_platform: 'bad-platform'")
            else:
                self._json(_CONVERT_PAYLOAD)
        else:
            self._error(404, "Not found")

    def _json(self, data: Any, status: int = 200):
        payload = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _error(self, status: int, detail: str):
        self._json({"detail": detail}, status=status)


@pytest.fixture(scope="module")
def mock_server() -> str:
    """Spin up a real (but lightweight) HTTP server in a background thread."""
    server = HTTPServer(("127.0.0.1", 0), _MockHandler)
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()


@pytest.fixture()
def mock_client(mock_server) -> Pix2asaClient:
    return Pix2asaClient(base_url=mock_server, timeout=5.0)


# ---------------------------------------------------------------------------
# Pix2asaClient unit tests (mock server)
# ---------------------------------------------------------------------------

class TestClientPing:
    def test_ping_up(self, mock_client):
        assert mock_client.ping() is True

    def test_ping_down(self):
        c = Pix2asaClient(base_url="http://127.0.0.1:1", timeout=0.5)
        assert c.ping() is False


class TestClientVersion:
    def test_returns_version_string(self, mock_client):
        assert mock_client.server_version() == __version__

    def test_unreachable_raises(self):
        c = Pix2asaClient(base_url="http://127.0.0.1:1", timeout=0.5)
        with pytest.raises(ServerUnavailableError):
            c.server_version()


class TestClientListDevices:
    def test_returns_list_of_remote_devices(self, mock_client):
        devices = mock_client.list_devices()
        assert isinstance(devices, list)
        assert all(isinstance(d, RemoteDevice) for d in devices)

    def test_count(self, mock_client):
        assert len(mock_client.list_devices()) == len(_DEVICES_PAYLOAD)

    def test_slug_present(self, mock_client):
        slugs = {d.slug for d in mock_client.list_devices()}
        assert "asa-5520" in slugs

    def test_interfaces_is_tuple(self, mock_client):
        for dev in mock_client.list_devices():
            assert isinstance(dev.interfaces, tuple)

    def test_max_vlans(self, mock_client):
        dev = next(d for d in mock_client.list_devices() if d.slug == "asa-5520")
        assert dev.max_vlans == 150


class TestClientConvert:
    def test_returns_conversion_result(self, mock_client):
        from pix2asa.converter import ConversionOptions
        result = mock_client.convert("PIX Version 6.3(1)\n", opts())
        assert isinstance(result, ConversionResult)

    def test_output_field(self, mock_client):
        result = mock_client.convert("", opts())
        assert result.output == _CONVERT_PAYLOAD["output"]

    def test_log_field(self, mock_client):
        result = mock_client.convert("", opts())
        assert result.log == _CONVERT_PAYLOAD["log"]

    def test_warnings_list(self, mock_client):
        result = mock_client.convert("", opts())
        assert result.warnings == []

    def test_errors_list(self, mock_client):
        result = mock_client.convert("", opts())
        assert result.errors == []

    def test_server_error_raises_client_error(self, mock_client):
        bad_opts = opts()
        bad_opts.target_platform = "bad-platform"
        with pytest.raises(ClientError) as exc_info:
            mock_client.convert("", bad_opts)
        assert exc_info.value.status == 422

    def test_unreachable_raises_server_unavailable(self):
        c = Pix2asaClient(base_url="http://127.0.0.1:1", timeout=0.5)
        with pytest.raises(ServerUnavailableError):
            c.convert("", opts())


class TestClientContextManager:
    def test_context_manager(self, mock_server):
        with Pix2asaClient(mock_server) as c:
            assert c.ping() is True


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class TestExceptions:
    def test_client_error_str(self):
        e = ClientError(404, "not found")
        assert "404" in str(e)
        assert "not found" in str(e)

    def test_server_unavailable_inherits_client_error(self):
        e = ServerUnavailableError("http://x", "refused")
        assert isinstance(e, ClientError)
        assert e.status == 0

    def test_server_unavailable_stores_url(self):
        e = ServerUnavailableError("http://myserver:8000", "refused")
        assert e.url == "http://myserver:8000"


# ---------------------------------------------------------------------------
# CLI — pix2asa-client (mock server)
# ---------------------------------------------------------------------------

class TestClientCLI:
    """Run the CLI's main() against the mock server."""

    def test_list_platforms(self, mock_server, capsys):
        rc = main(["--server", mock_server, "--list-platforms"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "asa-5520" in out

    def test_list_platforms_server_down_no_fallback(self, capsys):
        rc = main(["--server", "http://127.0.0.1:1", "--timeout", "0.5",
                   "--list-platforms"])
        assert rc == 1

    def test_list_platforms_server_down_with_fallback(self, capsys):
        rc = main(["--server", "http://127.0.0.1:1", "--timeout", "0.5",
                   "--fallback", "--list-platforms"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "asa-5520" in out

    def test_convert_to_stdout(self, mock_server, tmp_path, capsys):
        cfg = tmp_path / "pix.cfg"
        cfg.write_text("PIX Version 6.3(1)\n")
        rc = main(["--server", mock_server,
                   "-f", str(cfg), "-t", "asa-5520"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "ASA Version" in out

    def test_convert_to_file(self, mock_server, tmp_path):
        cfg = tmp_path / "pix.cfg"
        out = tmp_path / "asa.cfg"
        cfg.write_text("PIX Version 6.3(1)\n")
        rc = main(["--server", mock_server,
                   "-f", str(cfg), "-t", "asa-5520", "-o", str(out)])
        assert rc == 0
        assert "ASA Version" in out.read_text()

    def test_convert_server_down_no_fallback(self, tmp_path):
        cfg = tmp_path / "pix.cfg"
        cfg.write_text("PIX Version 6.3(1)\n")
        rc = main(["--server", "http://127.0.0.1:1", "--timeout", "0.5",
                   "-f", str(cfg), "-t", "asa-5520"])
        assert rc == 1

    def test_convert_server_down_with_fallback(self, tmp_path, capsys):
        cfg = tmp_path / "pix.cfg"
        cfg.write_text(
            "PIX Version 6.3(1)\n"
            "nameif ethernet0 outside security0\n"
            "nameif ethernet1 inside security100\n"
            "ip address outside 10.0.0.1 255.255.255.0\n"
        )
        rc = main(["--server", "http://127.0.0.1:1", "--timeout", "0.5",
                   "--fallback", "-f", str(cfg), "-t", "asa-5520"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "ASA Version" in out

    def test_no_input_file_error(self, mock_server):
        with pytest.raises(SystemExit):
            main(["--server", mock_server, "-t", "asa-5520"])

    def test_debug_log_to_stdout(self, mock_server, tmp_path, capsys):
        cfg = tmp_path / "pix.cfg"
        cfg.write_text("PIX Version 6.3(1)\n")
        rc = main(["--server", mock_server,
                   "-f", str(cfg), "-t", "asa-5520", "-d"])
        assert rc == 0
        # debug flag causes log to be printed; stderr has INFO from client
        combined = capsys.readouterr()
        assert "ASA Version" in combined.out

    def test_map_interface_flag(self, mock_server, tmp_path, capsys):
        cfg = tmp_path / "pix.cfg"
        cfg.write_text("PIX Version 6.3(1)\n")
        rc = main(["--server", mock_server,
                   "-f", str(cfg),
                   "-m", "ethernet0@GigabitEthernet0/0",
                   "-m", "ethernet1@GigabitEthernet0/1"])
        assert rc == 0

    def test_invalid_map_interface_format(self, mock_server, tmp_path):
        cfg = tmp_path / "pix.cfg"
        cfg.write_text("PIX Version 6.3(1)\n")
        with pytest.raises(SystemExit):
            main(["--server", mock_server,
                  "-f", str(cfg), "-m", "bad_format_no_at"])

    def test_version_flag(self, capsys):
        with pytest.raises(SystemExit) as exc:
            main(["--version"])
        assert exc.value.code == 0
        out = capsys.readouterr()
        assert __version__ in out.out or __version__ in out.err


# ---------------------------------------------------------------------------
# Live tests (opt-in, skip unless --live-server passed)
# ---------------------------------------------------------------------------

class TestLiveServer:
    @pytest.fixture(autouse=True)
    def skip_without_live_server(self, live_server_url):
        if not live_server_url:
            pytest.skip("Pass --live-server URL to run live server tests")

    def test_ping(self, live_server_url):
        c = Pix2asaClient(live_server_url)
        assert c.ping() is True

    def test_version(self, live_server_url):
        c = Pix2asaClient(live_server_url)
        assert c.server_version() == __version__

    def test_devices(self, live_server_url):
        c = Pix2asaClient(live_server_url)
        devices = c.list_devices()
        assert len(devices) >= 16

    def test_convert(self, live_server_url):
        c = Pix2asaClient(live_server_url)
        config = (
            "PIX Version 6.3(1)\n"
            "nameif ethernet0 outside security0\n"
            "nameif ethernet1 inside security100\n"
            "ip address outside 10.0.0.1 255.255.255.0\n"
        )
        result = c.convert(config, opts())
        assert result.output.startswith("ASA Version")
