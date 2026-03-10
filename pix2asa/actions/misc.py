"""Miscellaneous utility handlers: pass-through, ignore, unsupported, hostname,
ASDM, sysopt, VPDN, and password/key warning handlers.
"""

from __future__ import annotations

import re

from ..context import ConversionContext
from ..rendering import emit_lines


# ---------------------------------------------------------------------------
# Shared / utility handlers
# ---------------------------------------------------------------------------

def _ignore(m: re.Match, ctx: ConversionContext) -> bool:
    """Silently discard the matched line and log that it was removed."""
    line = m.group(0)
    ctx.log(f"INFO: {line} Removed from config")
    return True


def _repeat(m: re.Match, ctx: ConversionContext) -> bool:
    """Pass the matched line through to the output config unchanged."""
    emit_lines("passthrough.j2", {"line": m.group(0)}, ctx)
    return True


def _not_supported(m: re.Match, ctx: ConversionContext) -> bool:
    """Emit a 'not supported' comment for the matched line and issue a WARNING log entry."""
    line = m.group(0)
    emit_lines("unsupported.j2", {"line": line}, ctx)
    ctx.log(f"WARNING: The configuration is NOT supported - {line}")
    return True


def _conduit_not_supported(m: re.Match, ctx: ConversionContext) -> bool:
    """Emit a manual-conversion comment and ERROR log for conduit/apply/outbound commands."""
    line = m.group(0)
    emit_lines("conduit_unsupported.j2", {"line": line}, ctx)
    ctx.log(f"ERROR: The configuration is NOT supported, "
            f"Please convert manually or via the OCC tool - {line}")
    return True


# ---------------------------------------------------------------------------
# Hostname / ASDM / sysopt handlers
# ---------------------------------------------------------------------------

def _handle_hostname(m: re.Match, ctx: ConversionContext) -> bool:
    """Append '-migrated' to the hostname and emit a comment noting the rename."""
    old = m["name"]
    ctx.original_hostname = old
    new = f"{old}-migrated"
    emit_lines("hostname.j2", {"old": old, "new": new}, ctx)
    ctx.log(f"INFO: Hostname renamed from {old!r} to {new!r}")
    return True


def _handle_asdm_history(m: re.Match, ctx: ConversionContext) -> bool:
    """Convert 'pdm history enable' to the ASA equivalent 'asdm history enable'."""
    cmd = "asdm history enable"
    ctx.log(f"INFO: {m.group(0)} -> {cmd}")
    emit_lines("asdm_history.j2", {}, ctx)
    return True


def _handle_asdm_location(m: re.Match, ctx: ConversionContext) -> bool:
    """Convert a 'pdm location' line to its 'asdm location' equivalent."""
    cmd = f"asdm location {m['ip']} {m['mask']} {m['nameif']}"
    ctx.log(f"INFO: {m.group(0)} -> {cmd}")
    emit_lines("asdm_location.j2", {"ip": m["ip"], "mask": m["mask"], "nameif": m["nameif"]}, ctx)
    return True


def _handle_asdm_logging(m: re.Match, ctx: ConversionContext) -> bool:
    """Convert a 'pdm logging' line to 'logging asdm' and 'logging asdm-buffer-size' commands."""
    level = m["level"] if "level" in m.groupdict() and m["level"] else "0"
    messages = m["msgs"] if "msgs" in m.groupdict() and m["msgs"] else "100"
    cmd = f"logging asdm {level}"
    cmd1 = f"logging asdm-buffer-size {messages}"
    ctx.log(f"INFO: {m.group(0)} -> {cmd}\n\t{cmd1}")
    emit_lines("asdm_logging.j2", {"level": level, "messages": messages}, ctx)
    return True


def _handle_sysopt_permit_ipsec(m: re.Match, ctx: ConversionContext) -> bool:
    """Rename 'sysopt connection permit-ipsec' to 'sysopt connection permit-vpn'."""
    line = m.group(0)
    tmp = "sysopt connection permit-vpn"
    emit_lines("sysopt_ipsec.j2", {"original": line, "new": tmp}, ctx)
    ctx.log(f"INFO: VPN sysopt renamed: {line!r} -> {tmp!r}")
    return True


# ---------------------------------------------------------------------------
# VPDN handlers
# ---------------------------------------------------------------------------

def _handle_vpdn_group(m: re.Match, ctx: ConversionContext) -> bool:
    """Record the VPDN group name for later PPPoE interface association."""
    ctx.vpdn_groups.append(m["group"])
    return True


# ---------------------------------------------------------------------------
# Password / key warning handlers
# ---------------------------------------------------------------------------

def _password_blanked(m: re.Match, ctx: ConversionContext) -> bool:
    """Emit a warning comment and pass the line through when a password appears as all asterisks."""
    line = m.group(0)
    emit_lines("security_warning.j2", {"message": "Your password is set to all STARS(*) Please fix!", "line": line}, ctx)
    ctx.log(f"WARNING: Password is all STARS(*) - please correct before deploying! {line!r}")
    return True


def _isakmp_blanked(m: re.Match, ctx: ConversionContext) -> bool:
    """Emit a warning comment and pass the line through when an ISAKMP key appears as all asterisks."""
    line = m.group(0)
    emit_lines("security_warning.j2", {"message": "Your ISAKMP key is set to all STARS(*) Please fix!", "line": line}, ctx)
    ctx.log(f"WARNING: ISAKMP key is all STARS(*) - please correct before deploying! {line!r}")
    return True
