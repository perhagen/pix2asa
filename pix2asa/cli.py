"""Command-line interface for pix2asa.

Usage examples:
    pix2asa -f pix.cfg -t asa-5520 -o asa.cfg
    pix2asa -f pix.cfg -t asa-5520 --serve 8000
    pix2asa --list-platforms
"""

from __future__ import annotations

import argparse
import sys

from . import __version__
from .converter import convert, ConversionOptions
from .models import SourceVersion, TARGET_DEVICES, TargetVersion

__all__ = ["main"]


def main(argv: list[str] | None = None) -> int:
    """Parse arguments, run the conversion, and return an exit code (0 = success, 1 = errors)."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.list_platforms:
        for slug, dev in sorted(TARGET_DEVICES.items()):
            print(f"  {slug:<20} {dev.display_name}")
        return 0

    if args.serve is not None:
        _serve(args.serve)
        return 0  # never reached (uvicorn blocks)

    # --- read input ---
    if not args.input_file:
        parser.error("Input file required (-f / --input-file) unless --serve or --list-platforms.")

    try:
        with open(args.input_file, "r", encoding="utf-8", errors="replace") as fh:
            config_text = fh.read()
    except OSError as exc:
        parser.error(f"can't open '{args.input_file}': {exc}")

    # --- build options ---
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
        convert_names=not bool(args.no_convert_names),
        debug=bool(args.debug),
        source_filename=args.input_file or "",
    )

    # --- convert ---
    result = convert(config_text, options)

    # --- write output ---
    if args.output_file:
        try:
            with open(args.output_file, "w") as fh:
                fh.write(result.output)
        except OSError as exc:
            parser.error(f"can't open '{args.output_file}': {exc}")
    else:
        print(result.output, file=sys.stdout, end="")

    # --- log ---
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


def _build_parser() -> argparse.ArgumentParser:
    """Construct and return the argument parser for the pix2asa CLI."""
    p = argparse.ArgumentParser(
        prog="pix2asa",
        description="Convert Cisco PIX configuration to ASA format.",
    )
    p.add_argument("--version", action="version", version=f"pix2asa {__version__}")
    p.add_argument("--list-platforms", action="store_true",
                   help="List supported target platforms and exit.")

    p.add_argument("-f", "--input-file", metavar="FILE",
                   help="PIX configuration file to convert.")
    p.add_argument("-o", "--output-file", metavar="FILE",
                   help="Write converted ASA config here (default: stdout).")
    p.add_argument("-t", "--target-platform", metavar="PLATFORM",
                   help="Target ASA platform slug (see --list-platforms).")
    p.add_argument("-m", "--map-interface", action="append", metavar="SRC@DST",
                   help="Explicit interface mapping (can repeat). E.g. ethernet0@GigabitEthernet0/0")
    p.add_argument("-b", "--boot-system-file", metavar="FILE",
                   help="File containing boot system image path.")
    p.add_argument("-7", "--pix7", action="store_true",
                   help="Source PIX config is version 7.x (default: 6.x).")
    p.add_argument("-5", "--pix5505", action="store_true",
                   help="Generate ASA 5505 switch default configuration.")
    p.add_argument("-T", "--target-version", choices=["84"], default="84",
                   help="ASA target OS version (default: 84 for ASA 8.4+).")
    p.add_argument("-d", "--debug", action="store_true", help="Enable debug logging.")
    p.add_argument("--no-convert-names", action="store_true",
                   help="Pass 'name' commands through unchanged instead of converting to host objects.")
    p.add_argument("-l", "--log-file", metavar="FILE", help="Write log to FILE.")
    p.add_argument("-a", "--append-log-file", metavar="FILE", help="Append log to FILE.")
    p.add_argument("--serve", nargs="?", const=8000, type=int, metavar="PORT",
                   help="Start the REST API server on PORT (default 8000).")
    return p


def _serve(port: int) -> None:
    """Start the uvicorn server hosting the FastAPI app on *port*."""
    try:
        import uvicorn
    except ImportError:
        print("ERROR: uvicorn is required for --serve. Install it: pip install uvicorn[standard]",
              file=sys.stderr)
        sys.exit(1)
    from .api import app
    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    sys.exit(main())
