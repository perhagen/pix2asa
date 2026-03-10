"""HTTP client for the pix2asa REST API.

Can be used as a library:

    from pix2asa.client import Pix2asaClient
    from pix2asa.converter import ConversionOptions
    from pix2asa.models import SourceVersion, TargetVersion

    with Pix2asaClient("http://localhost:8000") as client:
        result = client.convert(config_text, options)
        print(result.output)

Or as a CLI that mirrors the standalone `pix2asa` command but sends work
to a running API server, with optional local fallback:

    pix2asa-client -f pix.cfg -t asa-5520 --server http://host:8000
    pix2asa-client -f pix.cfg -t asa-5520 --fallback   # local if server down
    pix2asa-client --list-platforms                     # from server

Uses only the Python standard library (urllib + json) — no extra dependencies.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

from . import __version__
from .converter import ConversionOptions, ConversionResult

__all__ = ["Pix2asaClient", "ClientError", "ServerUnavailableError", "main"]

_DEFAULT_SERVER = "http://localhost:8000"


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class ClientError(Exception):
    """Raised when the server returns an HTTP error."""
    def __init__(self, status: int, detail: str) -> None:
        """Initialise with the HTTP status code and error detail message."""
        super().__init__(f"HTTP {status}: {detail}")
        self.status = status
        self.detail = detail


class ServerUnavailableError(ClientError):
    """Raised when the server cannot be reached."""
    def __init__(self, url: str, reason: str) -> None:
        """Initialise with the target URL and the reason the server could not be reached."""
        super().__init__(0, f"Server unreachable at {url}: {reason}")
        self.url = url


# ---------------------------------------------------------------------------
# Device info (returned by list_devices)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RemoteDevice:
    """Immutable description of an ASA target platform returned by the server."""

    slug: str
    display_name: str
    interfaces: tuple[str, ...]
    max_vlans: int


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class Pix2asaClient:
    """Thin HTTP wrapper around the pix2asa REST API.

    All methods raise:
        ServerUnavailableError  — connection refused / timeout / DNS failure
        ClientError             — 4xx / 5xx from the server
    """

    def __init__(self, base_url: str = _DEFAULT_SERVER, timeout: float = 30.0) -> None:
        """Initialise the client with a server base URL and request timeout."""
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    # --- context manager ---

    def __enter__(self) -> "Pix2asaClient":
        """Return self to support use as a context manager."""
        return self

    def __exit__(self, *_: Any) -> None:
        """No-op exit — no resources need to be released."""
        pass

    # --- public API ---

    def ping(self) -> bool:
        """Return True if the server is reachable, False otherwise."""
        try:
            self._get("/api/version")
            return True
        except (ServerUnavailableError, ClientError):
            return False

    def server_version(self) -> str:
        """Return the server's pix2asa version string."""
        return self._get("/api/version")["version"]

    def list_devices(self) -> list[RemoteDevice]:
        """Return all target ASA platforms known to the server."""
        raw = self._get("/api/devices")
        return [
            RemoteDevice(
                slug=d["slug"],
                display_name=d["display_name"],
                interfaces=tuple(d["interfaces"]),
                max_vlans=d["max_vlans"],
            )
            for d in raw
        ]

    def convert(self, config_text: str, options: ConversionOptions) -> ConversionResult:
        """Send a conversion request and return the result.

        Raises ServerUnavailableError or ClientError on failure.
        """
        payload: dict[str, Any] = {
            "config": config_text,
            "target_platform": options.target_platform,
            "source_version": options.source_version.value,
            "target_version": options.target_version.value,
            "interface_map": options.interface_map,
            "custom_5505": options.custom_5505,
            "boot_system": options.boot_system,
        }
        data = self._post("/api/convert", payload)
        return ConversionResult(
            output=data["output"],
            log=data["log"],
            warnings=data.get("warnings", []),
            errors=data.get("errors", []),
        )

    # --- internals ---

    def _get(self, path: str) -> Any:
        """Send a GET request to *path* and return the decoded JSON response."""
        return self._request("GET", path, body=None)

    def _post(self, path: str, payload: dict) -> Any:
        """Send a POST request with *payload* to *path* and return the decoded JSON response."""
        return self._request("POST", path, body=payload)

    def _request(self, method: str, path: str, body: dict | None) -> Any:
        """Execute an HTTP request and return the parsed JSON body.

        Raises ServerUnavailableError on connection failure and ClientError on HTTP error responses.
        """
        url = self.base_url + path
        data: bytes | None = None
        headers: dict[str, str] = {"Accept": "application/json"}

        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"

        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            try:
                detail = json.loads(exc.read().decode()).get("detail", exc.reason)
            except Exception:
                detail = exc.reason
            raise ClientError(exc.code, str(detail)) from exc
        except (urllib.error.URLError, OSError) as exc:
            raise ServerUnavailableError(url, str(exc)) from exc


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    """Entry point for the `pix2asa-client` command."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    client = Pix2asaClient(base_url=args.server, timeout=args.timeout)

    # --list-platforms — fetch from server (or local fallback)
    if args.list_platforms:
        return _cmd_list_platforms(client, args)

    # Remaining commands require an input file
    if not args.input_file:
        parser.error("Input file required (-f / --input-file) unless --list-platforms.")

    return _cmd_convert(client, args, parser)


def _cmd_list_platforms(client: Pix2asaClient, args: argparse.Namespace) -> int:
    """Fetch and print all available target platforms, with optional local fallback."""
    try:
        devices = client.list_devices()
        for dev in sorted(devices, key=lambda d: d.slug):
            print(f"  {dev.slug:<20} {dev.display_name}")
        return 0
    except ServerUnavailableError as exc:
        if args.fallback:
            _warn(f"Server unavailable ({exc.url}) — using local device list.")
            from .models import TARGET_DEVICES
            for slug, dev in sorted(TARGET_DEVICES.items()):
                print(f"  {slug:<20} {dev.display_name}")
            return 0
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


def _cmd_convert(
    client: Pix2asaClient,
    args: argparse.Namespace,
    parser: argparse.ArgumentParser,
) -> int:
    """Read input, build ConversionOptions, convert via server, and write output/log."""
    # --- read input ---
    try:
        with open(args.input_file, "r", encoding="utf-8", errors="replace") as fh:
            config_text = fh.read()
    except OSError as exc:
        parser.error(f"can't open '{args.input_file}': {exc}")

    # --- build options ---
    from .models import SourceVersion, TargetVersion

    src_ver = SourceVersion.PIX7 if args.pix7 else SourceVersion.PIX6
    target_ver = TargetVersion.ASA84

    iface_map: dict[str, str] = {}
    if args.map_interface:
        for mapping in args.map_interface:
            parts = mapping.split("@")
            if len(parts) != 2:
                parser.error(f"Interface map must be SRC@DST, got: {mapping!r}")
            iface_map[parts[0]] = parts[1]

    target_platform: str = ""
    if not iface_map:
        if not args.target_platform:
            parser.error("Target platform required (-t / --target-platform).")
        target_platform = args.target_platform

    boot_system = ""
    if args.boot_system_file:
        try:
            with open(args.boot_system_file, "r") as fh:
                boot_system = fh.read().strip()
        except OSError as exc:
            parser.error(f"can't open '{args.boot_system_file}': {exc}")

    options = ConversionOptions(
        target_platform=target_platform,
        source_version=src_ver,
        target_version=target_ver,
        interface_map=iface_map,
        custom_5505=bool(args.pix5505),
        boot_system=boot_system,
        debug=bool(args.debug),
        source_filename=args.input_file or "",
    )

    # --- send to server (or fall back) ---
    result = _do_convert(client, config_text, options, args)
    if result is None:
        return 1

    # --- write output ---
    if args.output_file:
        try:
            with open(args.output_file, "w") as fh:
                fh.write(result.output)
        except OSError as exc:
            parser.error(f"can't open '{args.output_file}': {exc}")
    else:
        print(result.output, file=sys.stdout, end="")

    # --- write log ---
    if args.log_file or args.append_log_file or args.debug:
        if args.log_file:
            try:
                with open(args.log_file, "w") as fh:
                    fh.write(result.log)
            except OSError as exc:
                parser.error(f"can't open '{args.log_file}': {exc}")
        elif args.append_log_file:
            try:
                with open(args.append_log_file, "a") as fh:
                    fh.write(result.log)
            except OSError as exc:
                parser.error(f"can't open '{args.append_log_file}': {exc}")
        else:
            print(result.log, file=sys.stdout)

    return 1 if result.errors else 0


def _do_convert(
    client: Pix2asaClient,
    config_text: str,
    options: ConversionOptions,
    args: argparse.Namespace,
) -> ConversionResult | None:
    """Try the server; fall back to local library if --fallback is set."""
    try:
        result = client.convert(config_text, options)
        if args.debug:
            _info(f"Converted via server: {client.base_url}")
        return result
    except ServerUnavailableError as exc:
        if args.fallback:
            _warn(f"Server unavailable ({exc.url}) — running locally.")
            from .converter import convert
            return convert(config_text, options)
        print(f"ERROR: {exc}", file=sys.stderr)
        _hint("Tip: use --fallback to run locally when the server is down.")
        return None
    except ClientError as exc:
        print(f"ERROR: Server error — {exc}", file=sys.stderr)
        return None


def _build_parser() -> argparse.ArgumentParser:
    """Build and return the argument parser for the `pix2asa-client` CLI."""
    p = argparse.ArgumentParser(
        prog="pix2asa-client",
        description=(
            "Convert Cisco PIX configuration to ASA format via the pix2asa REST API.\n"
            "Mirrors the standalone `pix2asa` command; add --server to point at a remote instance."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--version", action="version", version=f"pix2asa-client {__version__}")

    # Server options (client-specific)
    srv = p.add_argument_group("server options")
    srv.add_argument(
        "--server", metavar="URL", default=_DEFAULT_SERVER,
        help=f"pix2asa API server base URL (default: {_DEFAULT_SERVER})",
    )
    srv.add_argument(
        "--timeout", metavar="SECONDS", type=float, default=30.0,
        help="HTTP request timeout in seconds (default: 30)",
    )
    srv.add_argument(
        "--fallback", action="store_true",
        help="Fall back to local conversion if the server is unavailable",
    )

    # Conversion options (mirror of pix2asa CLI)
    conv = p.add_argument_group("conversion options")
    conv.add_argument("--list-platforms", action="store_true",
                      help="List supported target platforms and exit.")
    conv.add_argument("-f", "--input-file",
                      metavar="FILE", help="PIX configuration file to convert.")
    conv.add_argument("-o", "--output-file",
                      metavar="FILE",
                      help="Write converted ASA config here (default: stdout).")
    conv.add_argument("-t", "--target-platform", metavar="PLATFORM",
                      help="Target ASA platform slug (see --list-platforms).")
    conv.add_argument("-m", "--map-interface", action="append", metavar="SRC@DST",
                      help="Explicit interface mapping (repeatable). E.g. ethernet0@GigabitEthernet0/0")
    conv.add_argument("-b", "--boot-system-file",
                      metavar="FILE", help="File containing boot system image path.")
    conv.add_argument("-7", "--pix7", action="store_true",
                      help="Source PIX config is version 7.x (default: 6.x).")
    conv.add_argument("-5", "--pix5505", action="store_true",
                      help="Generate ASA 5505 switch default configuration.")
    conv.add_argument("-T", "--target-version", choices=["84"], default="84",
                      help="ASA target OS version (default: 84 for ASA 8.4+).")
    conv.add_argument("-d", "--debug", action="store_true",
                      help="Enable debug logging.")
    conv.add_argument("-l", "--log-file",
                      metavar="FILE", help="Write log to FILE.")
    conv.add_argument("-a", "--append-log-file",
                      metavar="FILE", help="Append log to FILE.")
    return p


def _warn(msg: str) -> None:
    """Print a WARNING-prefixed message to stderr."""
    print(f"WARNING: {msg}", file=sys.stderr)


def _info(msg: str) -> None:
    """Print an INFO-prefixed message to stderr."""
    print(f"INFO: {msg}", file=sys.stderr)


def _hint(msg: str) -> None:
    """Print a plain hint message to stderr."""
    print(msg, file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
