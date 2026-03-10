"""Fixup/inspect handlers and the negation machinery for PIX-to-ASA conversion.

Covers all 'fixup protocol ...' and 'no fixup protocol ...' forms, the
_NegatedMatch wrapper, and the _neg() factory for creating negated variants.
"""

from __future__ import annotations

import re

from ..context import ConversionContext
from ..models import ConfigLine, Inspect


# ---------------------------------------------------------------------------
# Inspect-section marker helper
# ---------------------------------------------------------------------------

def _ensure_inspect_marker(ctx: ConversionContext) -> None:
    """Insert a single inspect-section marker ConfigLine into the output if none exists yet."""
    if not ctx.inspects:
        cfg = ConfigLine("")
        cfg.mark_inspect()
        ctx.config_lines.append(cfg)


# ---------------------------------------------------------------------------
# Fixup / inspect handlers
# ---------------------------------------------------------------------------

def _handle_fixup(m: re.Match, ctx: ConversionContext) -> bool:
    """Generic fixup/inspect handler.  Rule sets negated=True for 'no fixup'."""
    negated: bool = getattr(m, "_rule_negated", False)
    proto = m["proto"]
    port = m["port"] if "port" in m.groupdict() else "0"

    # Rename h323 h225 1720 → h323 h225
    if proto == "h323" and port == "1720":
        proto = "h323 h225"
    elif proto == "smtp":
        proto = "esmtp"

    _ensure_inspect_marker(ctx)
    for ins in ctx.inspects:
        if ins.name == proto:
            return True  # duplicate

    ctx.inspects.append(Inspect(name=proto, port=str(port), negated=negated))
    return True


def _handle_fixup_dns(m: re.Match, ctx: ConversionContext) -> bool:
    """Handle fixup/no-fixup for DNS, defaulting the maximum-length port to 512 if omitted."""
    negated: bool = getattr(m, "_rule_negated", False)
    port = m["port"] if "port" in m.groupdict() and m["port"] else "512"
    _ensure_inspect_marker(ctx)
    for ins in ctx.inspects:
        if ins.name == "dns":
            return True
    ctx.inspects.append(Inspect(name="dns", port=str(port), negated=negated))
    return True


def _handle_fixup_esp_ike(m: re.Match, ctx: ConversionContext) -> bool:
    """Convert 'fixup protocol esp-ike' to an ipsec-pass-thru inspect entry."""
    _ensure_inspect_marker(ctx)
    ctx.inspects.append(Inspect(name="ipsec-pass-thru"))
    return True


def _handle_fixup_h323_bare(m: re.Match, ctx: ConversionContext) -> bool:
    """Handle bare 'fixup protocol h323 <port>' (no h225/ras qualifier).

    PIX 'fixup protocol h323 <port>' enables both H.225 call signalling and
    RAS registration — emit both inspect entries.
    """
    negated: bool = getattr(m, "_rule_negated", False)
    _ensure_inspect_marker(ctx)
    for sub in ("h323 h225", "h323 ras"):
        if not any(ins.name == sub for ins in ctx.inspects):
            ctx.inspects.append(Inspect(name=sub, negated=negated))
    return True


# Known protocol name → ASA inspect name (for generic fallback)
_FIXUP_PROTO_MAP: dict[str, str] = {
    "smtp": "esmtp",
    "h323": "h323 h225",  # bare h323 → primary sub-type; bare handler adds ras too
}

# Protocols handled by specific rules above — generic fallback should not re-handle them
_FIXUP_SPECIFIC_PROTOS = frozenset({
    "dns", "ftp", "ftp strict", "h323 h225", "h323 ras", "http", "ils", "rsh",
    "rtsp", "snmp", "sip", "skinny", "smtp", "sqlnet", "tftp", "ctiqbe", "pptp",
    "esp-ike", "h323",
})


def _handle_fixup_generic(m: re.Match, ctx: ConversionContext) -> bool:
    """Catch-all for fixup commands with non-default ports or less common protocols.

    Emits 'inspect <proto>' (port is ignored — ASA 8.4 inspects on all ports by default)
    and logs a WARNING when a non-default port was specified.
    """
    negated: bool = getattr(m, "_rule_negated", False)
    proto = m["proto"].strip().lower()
    port  = m["port"].strip() if "port" in m.groupdict() and m["port"] else ""

    asa_name = _FIXUP_PROTO_MAP.get(proto, proto)

    _ensure_inspect_marker(ctx)
    if not any(ins.name == asa_name for ins in ctx.inspects):
        ctx.inspects.append(Inspect(name=asa_name, negated=negated))

    if port:
        ctx.log(
            f"WARNING: fixup protocol {proto} {port} — "
            f"non-default port ignored; ASA 8.4+ inspect {asa_name} runs on all ports. "
            f"Add a custom class-map/policy-map if inspection on port {port} only is required."
        )
    return True


# ---------------------------------------------------------------------------
# Negation machinery
# ---------------------------------------------------------------------------

class _NegatedMatch:
    """Thin wrapper around re.Match that exposes _rule_negated = True."""

    __slots__ = ("_m",)

    def __init__(self, m: re.Match) -> None:
        """Store the underlying re.Match object."""
        self._m = m

    def __getattr__(self, name: str):
        """Delegate attribute access to the wrapped re.Match object."""
        return getattr(self._m, name)

    @property
    def _rule_negated(self) -> bool:
        """Always return True, indicating this is a negated rule match."""
        return True

    def __getitem__(self, key):
        """Delegate item access to the wrapped re.Match object."""
        return self._m[key]

    def groupdict(self):
        """Delegate groupdict() to the wrapped re.Match object."""
        return self._m.groupdict()


def _neg(handler):
    """Return a handler variant that wraps the match in _NegatedMatch."""
    def _wrapper(m: re.Match, ctx: ConversionContext) -> bool:
        """Call handler with the match wrapped in _NegatedMatch."""
        return handler(_NegatedMatch(m), ctx)
    _wrapper.__name__ = f"{handler.__name__}_neg"
    return _wrapper


# Negated variants used in rule tables
_handle_fixup_neg           = _neg(_handle_fixup)
_handle_fixup_dns_neg       = _neg(_handle_fixup_dns)
_handle_fixup_h323_bare_neg = _neg(_handle_fixup_h323_bare)
_handle_fixup_generic_neg   = _neg(_handle_fixup_generic)
