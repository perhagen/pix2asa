"""Interface pool mapping and all interface-related handlers.

Covers:
  - _map_interface_pool: assigns the next available destination interface
  - _if_map: thin wrapper for pool lookup
  - setup_custom_if: registers explicit -m flag interface mappings
  - All 14 interface handlers (physical, logical, nameif, IP, MTU, etc.)
"""

from __future__ import annotations

import re

from ..context import ConversionContext
from ..models import ConfigLine, InterfaceConfig, TARGET_DEVICES
from ..rendering import emit_lines
from .misc import _repeat


# ---------------------------------------------------------------------------
# Interface pool mapping
# ---------------------------------------------------------------------------

def _map_interface_pool(source_if: str, ctx: ConversionContext) -> str:
    """Assign the next available destination interface for source_if.

    Uses ctx.target_platform to look up the ordered interface list.
    Falls back to identity mapping when the pool is exhausted.
    """
    platform = ctx.target_platform
    if source_if in ctx.platform_if_mapping:
        return ctx.platform_if_mapping[source_if]

    device = TARGET_DEVICES.get(platform)
    dest_interfaces = list(device.interfaces) if device else []

    if platform == "custom":
        # Identity mapping: source name is used as-is unless explicitly overridden
        dest_if = ctx.platform_if_mapping.get(source_if, source_if)
        ctx.map_interface(source_if, dest_if)
        return dest_if

    if ctx.platform_if_index < len(dest_interfaces):
        dest_if = dest_interfaces[ctx.platform_if_index]
        ctx.platform_if_index += 1
        ctx.map_interface(source_if, dest_if)
    else:
        # Exhausted — identity map
        dest_if = source_if
        ctx.map_interface(source_if, dest_if)
        ctx.platform_if_exceeded = True

    return dest_if


def _if_map(inter: str, ctx: ConversionContext) -> str:
    """Return the mapped destination interface name for inter."""
    if inter in ctx.platform_if_mapping:
        return ctx.platform_if_mapping[inter]
    return _map_interface_pool(inter, ctx)


def setup_custom_if(source_if: str, dest_if: str, ctx: ConversionContext) -> bool:
    """Register an explicit src→dst interface mapping (from -m flag)."""
    if dest_if in ctx.platform_if_mapping_r:
        ctx.log(f"ERROR: You can only map to an interface once. "
                f"{source_if}@{dest_if} was specified")
        ctx.log(f"ERROR: {ctx.platform_if_mapping_r[dest_if]}@{dest_if} already exists")
        return False
    if source_if in ctx.platform_if_mapping:
        ctx.log(f"ERROR: You can only map an interface once. "
                f"{source_if}@{dest_if} was specified")
        ctx.log(f"ERROR: {source_if}@{ctx.platform_if_mapping[source_if]} already exists")
        return False
    ctx.map_interface(source_if, dest_if)
    return True


# ---------------------------------------------------------------------------
# Interface handlers
# ---------------------------------------------------------------------------

def _handle_interface(m: re.Match, ctx: ConversionContext) -> bool:
    """Register or update a physical interface entry and append an interface marker ConfigLine."""
    hw = m["hw"].lower()
    speed = m["speed"] if "speed" in m.groupdict() and m["speed"] else "auto"
    state = m["state"] if "state" in m.groupdict() and m["state"] else "no shutdown"

    cfg = ConfigLine("")
    cfg.mark_interface(hw)
    ctx.config_lines.append(cfg)

    if hw not in ctx.interfaces:
        iface = InterfaceConfig(phys_name=hw, speed=speed, state=state)
        iface.mapped_name = _map_interface_pool(hw, ctx)
        ctx.interfaces[hw] = iface
    else:
        ctx.interfaces[hw].speed = speed
        if state != "no shutdown":
            ctx.interfaces[hw].state = state
        # Always refresh mapped_name — the nameif command may have created this
        # InterfaceConfig before the platform mapping was registered (e.g. PIX 4/6
        # configs where 'nameif' precedes 'interface').
        ctx.interfaces[hw].mapped_name = _map_interface_pool(hw, ctx)
    return True


def _handle_logical_interface(m: re.Match, ctx: ConversionContext) -> bool:
    """Register a logical (VLAN-based) sub-interface and populate vlan↔physical name maps."""
    hw = m["hw"].lower()
    vlan = m["vlan"]
    state = m["state"] if "state" in m.groupdict() and m["state"] else "no shutdown"

    logical_name = f"{hw}_{vlan}"
    cfg = ConfigLine("")
    cfg.mark_interface(logical_name)
    ctx.config_lines.append(cfg)

    ctx.logical_to_phys[f"vlan{vlan}"] = logical_name
    ctx.logical_to_phys_r[logical_name] = f"vlan{vlan}"

    iface = InterfaceConfig(phys_name=logical_name, state=state, logical=True)
    iface.set_logical()
    iface.set_vlan(vlan)
    iface.mapped_name = logical_name
    ctx.interfaces[logical_name] = iface
    return True


def _handle_interface_rename_only(m: re.Match, ctx: ConversionContext) -> bool:
    """Emit an interface command with the mapped destination interface name (PIX 7 pass)."""
    hw = m["hw"].lower()
    sub = m["sub"] if "sub" in m.groupdict() and m["sub"] else ""
    dest = _if_map(hw, ctx)
    emit_lines("interface_rename.j2", {"dest": dest, "sub": sub}, ctx)
    return True


def _handle_vlan_interface_rename(m: re.Match, ctx: ConversionContext) -> bool:
    """Emit a VLAN interface line unchanged (already in ASA syntax)."""
    vlan = m["vlan"].lower()
    emit_lines("vlan_interface.j2", {"vlan": vlan}, ctx)
    return True


def _handle_nameif(m: re.Match, ctx: ConversionContext) -> bool:
    """Record name↔interface mappings and set the nameif and security level on the interface."""
    hw = m["hw"].lower()
    name = m["name"]
    level = int(m["level"])
    ctx.name_ifs[name] = hw
    ctx.name_ifs_r[hw] = name
    if hw in ctx.interfaces:
        ctx.interfaces[hw].set_nameif(name, level)
    else:
        iface = InterfaceConfig(phys_name=hw)
        iface.set_nameif(name, level)
        ctx.interfaces[hw] = iface
    return True


def _handle_nameif_logical(m: re.Match, ctx: ConversionContext) -> bool:
    """Like _handle_nameif but resolves a logical (VLAN) interface to its physical entry first."""
    hw = m["hw"].lower()
    name = m["name"]
    level = int(m["level"])
    ctx.name_ifs[name] = hw
    ctx.name_ifs_r[hw] = name
    phys = ctx.logical_to_phys.get(hw, hw)
    if phys in ctx.interfaces:
        ctx.interfaces[phys].set_nameif(name, level)
    else:
        iface = InterfaceConfig(phys_name=hw)
        iface.set_nameif(name, level)
        ctx.interfaces[hw] = iface
    return True


def _handle_mtu(m: re.Match, ctx: ConversionContext) -> bool:
    """Store the MTU value on the matching interface and pass the original line through."""
    nameif = m["nameif"]
    mtu = int(m["mtu"])
    phys = ctx.get_real_phys(nameif)
    if phys and phys in ctx.interfaces:
        ctx.interfaces[phys].mtu = mtu
    emit_lines("passthrough.j2", {"line": m.group(0)}, ctx)
    return True


def _handle_ip_static(m: re.Match, ctx: ConversionContext) -> bool:
    """Store a static IP address and netmask on the matching interface; no output line emitted."""
    nameif = m["nameif"]
    ip = m["ip"]
    mask = m["mask"]
    phys = ctx.get_real_phys(nameif)
    if phys and phys in ctx.interfaces:
        ctx.interfaces[phys].ip_address = ip
        ctx.interfaces[phys].netmask = mask
    else:
        ctx.log(f"ERROR: Could not find matching interface for ip address: {nameif}")
    return True


def _handle_ip_dhcp(m: re.Match, ctx: ConversionContext) -> bool:
    """Mark the matching interface as DHCP-configured, optionally setting the default-route flag."""
    nameif = m["nameif"]
    set_route = bool(m["setroute"]) if "setroute" in m.groupdict() else False
    phys = ctx.get_real_phys(nameif)
    if phys and phys in ctx.interfaces:
        ctx.interfaces[phys].set_dhcp(set_route=bool(set_route))
    else:
        ctx.log(f"ERROR: Could not find matching interface for dhcp: {nameif}")
    return True


def _handle_ip_pppoe(m: re.Match, ctx: ConversionContext) -> bool:
    """Mark the matching interface as PPPoE-configured, optionally setting the default-route flag."""
    nameif = m["nameif"]
    set_route = bool(m["setroute"]) if "setroute" in m.groupdict() else False
    phys = ctx.get_real_phys(nameif)
    if phys and phys in ctx.interfaces:
        ctx.interfaces[phys].set_pppoe(set_route=bool(set_route))
    else:
        ctx.log(f"ERROR: Could not find matching interface for pppoe: {nameif}")
    return True


def _handle_standby_ip(m: re.Match, ctx: ConversionContext) -> bool:
    """Store the failover standby IP address on the matching interface."""
    nameif = m["nameif"]
    ip = m["ip"]
    phys = ctx.get_real_phys(nameif)
    if phys and phys in ctx.interfaces:
        ctx.interfaces[phys].standby_ip = ip
    else:
        ctx.log(f"ERROR: Could not find matching interface for standby: {nameif}")
    return True


def _handle_no_ip_address(m: re.Match, ctx: ConversionContext) -> bool:
    """Silently drop 'no ip address' lines; handled by interface defaults."""
    return True  # silently drop — handled by default


def _handle_allocate_interface(m: re.Match, ctx: ConversionContext) -> bool:
    """Map a physical interface name and emit an allocate-interface line with the remapped name."""
    hw = m["hw"].lower()
    dest = _map_interface_pool(hw, ctx)
    ctx.log(f"allocate-interface {hw} -> {dest}")
    emit_lines("allocate_interface.j2", {"dest": dest}, ctx)
    return True
