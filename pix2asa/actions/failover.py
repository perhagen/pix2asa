"""Failover-related handlers for PIX-to-ASA conversion.

Covers PIX 6 failover poll, lan interface, link, lan/link rename (PIX 7),
and the failover LAN key blanking.
"""

from __future__ import annotations

import re

from ..context import ConversionContext
from ..models import ConfigLine
from ..rendering import emit_lines
from .misc import _password_blanked


def _handle_failover_poll(m: re.Match, ctx: ConversionContext) -> bool:
    """Fix PIX6 'failover poll <time>' syntax to ASA's 'failover polltime <time>'."""
    line = m.group(0)
    tmp = f"failover polltime {m['time']}"
    emit_lines("failover_poll.j2", {"old": line, "new": tmp}, ctx)
    ctx.log(f"INFO: Failover poll timer corrected: {line!r} -> {tmp!r}")
    return True


def _handle_failover_lan_interface(m: re.Match, ctx: ConversionContext) -> bool:
    """Convert a PIX6 'failover lan interface' command, remapping the physical interface name."""
    nameif = m["nameif"]
    phys = ctx.get_real_phys(nameif)
    if not phys or phys not in ctx.interfaces:
        ctx.log(f"ERROR: Could not find matching interface to {nameif!r}")
        return True
    mapped = ctx.interfaces[phys].mapped_name or phys
    ctx.interfaces[phys].set_failover_lan()
    ctx.failover_lan_if = nameif
    tmp = f"failover lan interface {nameif} {mapped}"
    emit_lines("failover_lan_interface.j2", {"original": m.group(0), "new": tmp}, ctx)
    ctx.log(f"INFO: {m.group(0)!r} Converted to {tmp!r}")
    cfg = ConfigLine("failover lan")
    cfg.set_failover_lan(nameif)
    ctx.config_lines.append(cfg)
    return True


def _handle_failover_link(m: re.Match, ctx: ConversionContext) -> bool:
    """Convert a PIX6 'failover link' command, remapping the physical interface and adding a state-tracking marker."""
    nameif = m["nameif"]
    phys = ctx.get_real_phys(nameif)
    if not phys or phys not in ctx.interfaces:
        ctx.log(f"ERROR: Could not find matching interface to {nameif!r}")
        return True
    mapped = ctx.interfaces[phys].mapped_name or phys
    ctx.interfaces[phys].set_failover_state()
    tmp = f"failover link {nameif} {mapped}"
    emit_lines("failover_link.j2", {"original": m.group(0), "new": tmp}, ctx)
    ctx.log(f"INFO: {m.group(0)!r} Converted to {tmp!r}")
    cfg = ConfigLine("failover link ip")
    cfg.set_failover_link(nameif)
    ctx.config_lines.append(cfg)
    return True


def _handle_failover_lan_rename(m: re.Match, ctx: ConversionContext) -> bool:
    """Re-emit the failover lan interface line with the remapped physical interface name (PIX 7)."""
    from .interfaces import _if_map
    nameif = m["nameif"]
    hw = m["hw"].lower()
    sub = m["sub"] if "sub" in m.groupdict() and m["sub"] else ""
    dest = _if_map(hw, ctx)
    emit_lines("failover_lan_rename.j2", {"nameif": nameif, "dest": dest, "sub": sub}, ctx)
    return True


def _handle_failover_link_rename(m: re.Match, ctx: ConversionContext) -> bool:
    """Re-emit the failover link line with the remapped physical interface name (PIX 7)."""
    from .interfaces import _if_map
    nameif = m["nameif"]
    hw = m["hw"].lower()
    sub = m["sub"] if "sub" in m.groupdict() and m["sub"] else ""
    dest = _if_map(hw, ctx)
    emit_lines("failover_link_rename.j2", {"nameif": nameif, "dest": dest, "sub": sub}, ctx)
    return True


def _handle_failover_lan_key(m: re.Match, ctx: ConversionContext) -> bool:
    """Blank out the failover LAN key by delegating to _password_blanked."""
    return _password_blanked(m, ctx)
