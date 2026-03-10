"""Pure conversion entry point.

convert(config_text, options) -> ConversionResult

No global state, no file I/O — suitable for direct use by the API and CLI.
stdout is captured internally so the caller always receives a string.

Rust equivalent:
    fn convert(input: &str, options: &ConversionOptions) -> ConversionResult
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field

from .actions import apply_name_substitutions, apply_nat_remap_to_names, build_dispatcher, emit_default_mtus, emit_nat_rules, emit_conduit_access_groups, setup_custom_if
from .context import ConversionContext
from .models import (
    ConfigLine,
    Inspect,
    SourceVersion,
    TARGET_DEVICES,
    TargetVersion,
)

__all__ = ["ConversionOptions", "ConversionResult", "VirtualInterface", "convert"]


# ---------------------------------------------------------------------------
# Options / result types (also used as Pydantic models in api.py)
# ---------------------------------------------------------------------------

@dataclass
class VirtualInterface:
    """One allocate-interface line for ASA multi-context system config.

    Attributes:
        src_pix_if:  PIX source interface name (e.g. "ethernet0")
        physical:    System-level physical/sub-interface (e.g. "Port-channel1.1400")
        nameif:      Logical name used both as the context interface name and nameif
                     (e.g. "outside")
    """
    src_pix_if: str
    physical: str
    nameif: str


@dataclass
class ConversionOptions:
    """Options controlling a single PIX-to-ASA conversion run."""
    target_platform: str = ""
    source_version: SourceVersion = SourceVersion.PIX6
    target_version: TargetVersion = TargetVersion.ASA84
    # Explicit interface overrides: {"ethernet0": "GigabitEthernet0/0", ...}
    interface_map: dict[str, str] = field(default_factory=dict)
    custom_5505: bool = False
    boot_system: str = ""
    convert_names: bool = True   # when False, 'name' commands are passed through unchanged
    debug: bool = False
    source_filename: str = ""    # original input filename, recorded in the log
    # Multi-context (virtual) interface mappings
    context_mode: bool = False
    virtual_interfaces: list[VirtualInterface] = field(default_factory=list)


@dataclass
class ConversionResult:
    """Result returned by :func:`convert`, containing output text and diagnostic messages."""
    output: str                    # converted ASA configuration text
    log: str                       # full log (INFO / WARNING / ERROR lines)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    converted_names: dict[str, str] = field(default_factory=dict)  # name → IP for all converted 'name' commands


# ---------------------------------------------------------------------------
# Version auto-detection
# ---------------------------------------------------------------------------

_PIX_VERSION_RE = re.compile(r"^PIX\s+Version\s+(\d+)\.\d+", re.IGNORECASE | re.MULTILINE)


def _detect_source_version(config_text: str) -> SourceVersion | None:
    """Return the SourceVersion implied by the 'PIX Version X.Y(Z)' header, or None."""
    m = _PIX_VERSION_RE.search(config_text)
    if not m:
        return None
    major = int(m.group(1))
    if major >= 7:
        return SourceVersion.PIX7
    return SourceVersion.PIX6


def _render_system_config(ctx: "ConversionContext", options: "ConversionOptions") -> str:
    """Build the :::: system-config :::: block for multi-context ASA deployments.

    Placed before the device context config in the output so operators can
    copy the system-context commands to the system config separately.
    """
    name = ctx.original_hostname or "unknown"
    lines = [
        ":::: system-config ::::",
        f": context {name}",
    ]
    for vi in options.virtual_interfaces:
        lines.append(f":  allocate-interface {vi.physical} {vi.nameif}")
    lines.append(f":  config-url disk0:/{name}.cfg")
    lines.append("::::")
    lines.append("")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def convert(config_text: str, options: ConversionOptions) -> ConversionResult:
    """Convert a PIX configuration string to ASA format."""

    # Auto-detect source version from the config header, overriding the caller's
    # selection when a 'PIX Version X.Y(Z)' line is present.
    detected = _detect_source_version(config_text)
    source_version = detected if detected is not None else options.source_version

    ctx = ConversionContext(
        source_version=source_version,
        target_version=options.target_version,
        target_platform=options.target_platform,
        custom_5505=options.custom_5505,
        boot_system=options.boot_system,
        convert_names=options.convert_names,
        debug=options.debug,
    )

    # Register explicit interface overrides before the pass begins
    for src, dst in options.interface_map.items():
        if not setup_custom_if(src.lower(), dst, ctx):
            return ConversionResult(
                output="",
                log=ctx.get_log(),
                errors=[f"Invalid interface mapping: {src}@{dst}"],
            )
    if options.interface_map:
        ctx.target_platform = "custom"

    # Register virtual (context-mode) interface mappings.
    # Each maps a PIX source interface to its logical nameif so the interface
    # stanza renders as "interface outside / nameif outside" instead of the
    # hardware name.
    for vi in options.virtual_interfaces:
        if not setup_custom_if(vi.src_pix_if.lower(), vi.nameif, ctx):
            return ConversionResult(
                output="",
                log=ctx.get_log(),
                errors=[f"Invalid virtual interface mapping: {vi.src_pix_if}@{vi.nameif}"],
            )
    if options.virtual_interfaces:
        ctx.target_platform = "custom"

    ctx.log(f"INFO: PIX to ASA conversion tool")
    if options.source_filename:
        ctx.log(f"INFO: Source file: {options.source_filename}")
    if detected is not None:
        ctx.log(f"INFO: Source version: PIX OS {ctx.source_version.value}.x (auto-detected)")
    else:
        ctx.log(f"INFO: Source version: PIX OS {ctx.source_version.value}.x")
    ctx.log(f"INFO: Target platform: {ctx.target_platform or '(auto)'}")

    dispatcher = build_dispatcher(ctx)

    # --- main parse loop ---
    for raw_line in config_text.splitlines():
        line = _normalize_newlines(raw_line)
        if not line:
            continue
        matched = dispatcher.dispatch(line, ctx)
        if not matched:
            ctx.config_lines.append(ConfigLine(line))

    # --- post-processing ---
    emit_default_mtus(ctx)
    emit_nat_rules(ctx)
    apply_nat_remap_to_names(ctx)   # catch-up remap for static-before-name ordering
    emit_conduit_access_groups(ctx)
    apply_name_substitutions(ctx)

    # --- render output ---
    output_buf = io.StringIO()
    _render_config(ctx, output_buf)
    output = output_buf.getvalue()

    # --- prepend system-config block for multi-context mode ---
    if options.context_mode and options.virtual_interfaces:
        output = _render_system_config(ctx, options) + output

    # --- extract warnings / errors from log ---
    log_text = ctx.get_log()
    warnings = [ln for ln in log_text.splitlines() if ln.startswith("WARNING:")]
    errors = [ln for ln in log_text.splitlines() if ln.startswith("ERROR:")]

    return ConversionResult(
        output=output,
        log=log_text,
        warnings=warnings,
        errors=errors,
        converted_names=dict(ctx.converted_names),
    )


# ---------------------------------------------------------------------------
# Output rendering
# ---------------------------------------------------------------------------

def _render_config(ctx: ConversionContext, out: io.StringIO) -> None:
    """Write the full converted ASA config to `out`."""
    from pix2asa.rendering import render_template

    def w(line: str = "") -> None:
        print(line, file=out)

    # ASA version header + optional boot system
    if ctx.boot_system:
        ctx.log(f"INFO: BootSystem Image: {ctx.boot_system}")
    out.write(render_template("version_header.j2", {"boot_system": ctx.boot_system}))

    ctx.log(f"INFO: The destination platform is: {ctx.target_platform}")

    # Interface mapping summary
    if ctx.platform_if_mapping:
        if ctx.platform_if_exceeded:
            w(":::: WARNING: Your source platform has more physical interfaces than your")
            w(":::: destination platform. The interfaces that could")
            w(":::: not be mapped on destination platform have been identity mapped.")
            ctx.log("WARNING: Source platform has more physical interfaces than destination.")
        mapping_str = repr(dict(sorted(ctx.platform_if_mapping.items())))
        w(f":::: Interface mapping - {mapping_str}")
        ctx.log("\nINFO: Interface Mapping:")
        for src in sorted(ctx.platform_if_mapping):
            ctx.log(f"  {src}\t->\t{ctx.platform_if_mapping[src]}")

    # ASA 5505 switch default config
    if ctx.target_platform == "asa-5505" or ctx.custom_5505:
        ctx.log("INFO: A default switch configuration for the embedded switch has been generated.")
        out.write(render_template("asa5505_switch.j2", {}))

    # VPDN groups (must precede interface stanzas)
    for group in ctx.vpdn_groups:
        w(f"vpdn group {group} request dialout pppoe")

    # --- Config body (grouped by section type) ---
    # Build blocks: each block is (section_key, [ConfigLine, ...]).
    # Indented continuation lines are kept with their parent block.
    blocks: list[tuple[int, list]] = []
    for cfg_line in ctx.config_lines:
        if cfg_line.is_inspect_marker():
            continue  # inspect output is deferred to policy-map block
        if cfg_line.is_interface_marker():
            blocks.append((_SEC_INTERFACE, [cfg_line]))
        elif cfg_line.is_failover_lan() or cfg_line.is_failover_link():
            blocks.append((_SEC_FAILOVER, [cfg_line]))
        elif cfg_line.text.startswith((" ", "\t")):
            # Continuation / sub-command — attach to the current block
            if blocks:
                blocks[-1][1].append(cfg_line)
            else:
                blocks.append((_section_key(cfg_line.text.lstrip()), [cfg_line]))
        else:
            blocks.append((_section_key(cfg_line.text), [cfg_line]))

    # Stable sort by section key — preserves original order within each section
    blocks.sort(key=lambda b: b[0])

    # Emit blocks; insert a blank line + section header whenever the section changes
    last_sec = -1
    for sec, lines in blocks:
        if sec != last_sec:
            if last_sec >= 0:
                w()
            label = _SEC_LABELS.get(sec, "")
            if label and sec != _SEC_HEADER:
                w(f":: {label}")
            last_sec = sec
        for cfg_line in lines:
            if cfg_line.is_interface_marker():
                iface_name = cfg_line.get_interface()
                if iface_name in ctx.interfaces:
                    w(ctx.interfaces[iface_name].render())
            elif cfg_line.is_failover_lan() or cfg_line.is_failover_link():
                w(cfg_line.render())
            else:
                line_text = cfg_line.render()
                if line_text:
                    w(line_text)

    # Inspect / policy-map block
    if ctx.inspects:
        w()
        w(":: Service Policy")
    _render_inspects(ctx, out)


def _render_inspects(ctx: ConversionContext, out: io.StringIO) -> None:
    """Emit the policy-map / inspect block rendered from inspect_stanza.j2."""
    if not ctx.inspects:
        return
    from pix2asa.rendering import render_template
    dns_entry = next((i for i in ctx.inspects if i.name == "dns"), None)
    rendered = render_template("inspect_stanza.j2", {
        "dns_entry": dns_entry,
        "inspects": ctx.inspects,
    })
    out.write(rendered)


# ---------------------------------------------------------------------------
# Section classification
# ---------------------------------------------------------------------------

# Section keys for output grouping (lower = earlier in output)
_SEC_HEADER     = 0   # :, :::: comments
_SEC_INTERFACE  = 1   # interface stanzas
_SEC_CREDS      = 2   # enable password, passwd
_SEC_IDENTITY   = 3   # hostname, domain-name, names
_SEC_MTU        = 4   # mtu
_SEC_IP         = 5   # ip ...
_SEC_OBJECTS    = 6   # object network, object-group
_SEC_ACL        = 7   # access-list
_SEC_NAT        = 8   # nat, ! pix2asa:
_SEC_ACLGRP     = 9   # access-group
_SEC_ROUTE      = 10  # route
_SEC_FAILOVER   = 11  # failover
_SEC_TIMEOUT    = 12  # timeout
_SEC_AAA        = 13  # aaa-server, aaa
_SEC_MGMT       = 14  # http, telnet, ssh, console, management-access
_SEC_LOGGING    = 15  # logging
_SEC_SNMP       = 16  # snmp-server
_SEC_SYSOPT     = 17  # sysopt
_SEC_CRYPTO     = 18  # crypto ipsec, crypto map, crypto dynamic-map
_SEC_ISAKMP     = 19  # isakmp
_SEC_VPN        = 20  # vpngroup, tunnel-group
_SEC_DHCP       = 21  # dhcpd, dhcp
_SEC_USERS      = 22  # username
_SEC_NTP        = 23  # ntp
_SEC_CLOCK      = 24  # clock timezone, clock summer-time
_SEC_ICMP       = 25  # icmp permit / deny
_SEC_ASDM       = 26  # asdm location, asdm history
_SEC_ARP        = 27  # arp
_SEC_MISC       = 99  # everything else


def _section_key(text: str) -> int:
    """Return the section number for *text* to group output by command type."""
    if text.startswith((":::", ": ", ":\n")) or text in (":", ":"):
        return _SEC_HEADER
    if text.startswith(("enable ", "passwd ")):
        return _SEC_CREDS
    if text.startswith(("hostname ", "domain-name ", "names", "no names")):
        return _SEC_IDENTITY
    if text.startswith("mtu "):
        return _SEC_MTU
    if text.startswith(("ip ", "no ip ")):
        return _SEC_IP
    if text.startswith(("object ", "object-group ")):
        return _SEC_OBJECTS
    if text.startswith("access-list "):
        return _SEC_ACL
    if text.startswith(("nat ", "nat(")) or "pix2asa:" in text:
        return _SEC_NAT
    if text.startswith("access-group "):
        return _SEC_ACLGRP
    if text.startswith("route "):
        return _SEC_ROUTE
    if text.startswith(("failover", "no failover")):
        return _SEC_FAILOVER
    if text.startswith("timeout "):
        return _SEC_TIMEOUT
    if text.startswith(("aaa-", "aaa ")):
        return _SEC_AAA
    if text.startswith(("http ", "http\n", "telnet ", "ssh ", "console ",
                         "no floodguard", "management-access ")):
        return _SEC_MGMT
    if text.startswith(("logging ", "no logging")):
        return _SEC_LOGGING
    if text.startswith(("snmp-", "no snmp-")):
        return _SEC_SNMP
    if text.startswith(("sysopt ", "no sysopt ")):
        return _SEC_SYSOPT
    if text.startswith("crypto "):
        return _SEC_CRYPTO
    if text.startswith("isakmp "):
        return _SEC_ISAKMP
    if text.startswith(("vpngroup ", "tunnel-group ")):
        return _SEC_VPN
    if text.startswith(("dhcpd ", "dhcp ")):
        return _SEC_DHCP
    if text.startswith("username "):
        return _SEC_USERS
    if text.startswith("ntp "):
        return _SEC_NTP
    if text.startswith("clock "):
        return _SEC_CLOCK
    if text.startswith(("icmp ", "no icmp ")):
        return _SEC_ICMP
    if text.startswith("asdm "):
        return _SEC_ASDM
    if text.startswith("arp "):
        return _SEC_ARP
    return _SEC_MISC


# Human-readable label for each section key (used as output section headers)
_SEC_LABELS: dict[int, str] = {
    _SEC_HEADER:    "Header",
    _SEC_INTERFACE: "Interfaces",
    _SEC_CREDS:     "Credentials",
    _SEC_IDENTITY:  "Identity",
    _SEC_MTU:       "MTU",
    _SEC_IP:        "IP Settings",
    _SEC_OBJECTS:   "Objects",
    _SEC_ACL:       "Access Lists",
    _SEC_NAT:       "NAT",
    _SEC_ACLGRP:    "Access Groups",
    _SEC_ROUTE:     "Routing",
    _SEC_FAILOVER:  "Failover",
    _SEC_TIMEOUT:   "Timeouts",
    _SEC_AAA:       "AAA",
    _SEC_MGMT:      "Management",
    _SEC_LOGGING:   "Logging",
    _SEC_SNMP:      "SNMP",
    _SEC_SYSOPT:    "System Options",
    _SEC_CRYPTO:    "Crypto / IPsec",
    _SEC_ISAKMP:    "ISAKMP",
    _SEC_VPN:       "VPN",
    _SEC_DHCP:      "DHCP",
    _SEC_USERS:     "Users",
    _SEC_NTP:       "NTP",
    _SEC_CLOCK:     "Clock",
    _SEC_ICMP:      "ICMP",
    _SEC_ASDM:      "ASDM",
    _SEC_ARP:       "ARP",
    _SEC_MISC:      "Miscellaneous",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalize_newlines(s: str) -> str:
    """Normalise CR-LF and bare CR line endings to LF and strip trailing newlines."""
    return s.replace("\r\n", "\n").replace("\r", "\n").rstrip("\n")
