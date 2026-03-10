"""Post-processing: emit dynamic NAT rules and default MTU commands.

Covers:
  - Pool object helpers (_range_obj_name, _ensure_range_object,
    _resolve_pool_entry, _resolve_pool_member)
  - emit_nat_rules: pairs collected PIX nat/global rules → ASA object NAT
  - emit_default_mtus: adds 'mtu <nameif> 1500' for interfaces without explicit MTU
"""

from __future__ import annotations

from ..context import ConversionContext
from ..models import ConfigLine, TargetVersion
from ..rendering import emit_lines
from .nat import _ensure_static_object, _ip_to_underscores


# ---------------------------------------------------------------------------
# Pool object helpers
# ---------------------------------------------------------------------------

def _range_obj_name(ip1: str, ip2: str) -> str:
    """Generate an auto object name for an IP range pool (includes both endpoints)."""
    return f"range_{_ip_to_underscores(ip1)}_{_ip_to_underscores(ip2)}"


def _ensure_range_object(ip1: str, ip2: str, ctx: ConversionContext) -> str:
    """Return the object name for an IP range, creating the object network entry if needed."""
    name = _range_obj_name(ip1, ip2)
    if name not in ctx.static_objects:
        emit_lines("auto_object.j2", {"name": name, "type": "range", "ip": ip1, "mask_part": f" {ip2}"}, ctx)
        ctx.static_objects[name] = ("range", ip1, ip2)
    return name


def _resolve_pool_entry(pool_spec: str, pool_type: str, ctx: ConversionContext) -> str:
    """Return the ASA object name for a single global pool entry (single-entry nat path).

    Creates the ``object network`` block if the IP/range/subnet is not yet tracked.
    """
    if pool_type == "host":
        return _ensure_static_object(pool_spec, "255.255.255.255", ctx)
    elif pool_type == "subnet":
        ip, mask = pool_spec.split("/", 1)
        return _ensure_static_object(ip, mask, ctx)
    elif pool_type == "range":
        ip1, ip2 = pool_spec.split("-", 1)
        return _ensure_range_object(ip1, ip2, ctx)
    # "interface" is never passed to this helper
    raise ValueError(f"Unexpected pool_type: {pool_type!r}")


def _resolve_pool_member(pool_spec: str, pool_type: str, ctx: ConversionContext) -> dict:
    """Return a member dict for the nat_pool_group.j2 template (multi-entry pool path).

    Uses inline ``network-object`` forms where possible:

    - Named host (IP in ``converted_names_r``) → ``network-object object <name>``
    - Bare host IP → ``network-object host <ip>`` (no intermediate object network)
    - Subnet → ``network-object <ip> <mask>`` inline
    - Range → creates ``object network range_*`` then ``network-object object <name>``
    """
    if pool_type == "host":
        name = ctx.converted_names_r.get(pool_spec)
        if name:
            return {"type": "object", "name": name}
        return {"type": "host", "ip": pool_spec}
    elif pool_type == "subnet":
        ip, mask = pool_spec.split("/", 1)
        return {"type": "subnet", "ip": ip, "mask": mask}
    elif pool_type == "range":
        ip1, ip2 = pool_spec.split("-", 1)
        range_name = _ensure_range_object(ip1, ip2, ctx)
        return {"type": "object", "name": range_name}
    raise ValueError(f"Unexpected pool_type: {pool_type!r}")


# ---------------------------------------------------------------------------
# Post-processing functions
# ---------------------------------------------------------------------------

def emit_default_mtus(ctx: ConversionContext) -> None:
    """Emit 'mtu <nameif> 1500' for every interface that has no explicit MTU.

    Called once after the engine pass.  Mirrors what would happen if the
    source config contained 'mtu <nameif> 1500' for every interface.
    Skips any nameif that already has a 'mtu ...' ConfigLine (e.g. from a
    passthrough where the interface lookup failed at parse time).
    """
    # Collect nameifs already covered by an explicit mtu line in the output
    seen_mtu: set[str] = {
        line.text.split()[1]
        for line in ctx.config_lines
        if line.text.startswith("mtu ") and len(line.text.split()) >= 2
    }

    for iface in ctx.interfaces.values():
        if iface.mtu == 0 and iface.nameif and iface.nameif not in seen_mtu:
            iface.mtu = 1500
            ctx.config_lines.append(ConfigLine(f"mtu {iface.nameif} 1500"))
            ctx.log(f"INFO: Defaulting MTU to 1500 for interface {iface.nameif}")


def emit_nat_rules(ctx: ConversionContext) -> None:
    """Emit ASA object-based NAT statements for all collected PIX nat/global pairs.

    Called once after the engine pass.  For each nat_id found in
    ``ctx.pix_nat_rules``, the matching ``ctx.pix_global_rules`` entries are
    consulted to determine the outside interface and translated address pool.

    - nat_id **0**: NAT exemption — emits ``source static <obj> <obj>`` identity NAT.
    - Normal nat_id: emits ``source dynamic <real_obj> <pool_obj>`` (or ``interface``
      for PAT) using :data:`dynamic_nat.j2`.
    - If no global entry exists for a nat_id, the original ``nat`` line is emitted
      as a passthrough comment so information is not silently lost.
    """
    for nat_id, nat_entries in sorted(ctx.pix_nat_rules.items()):
        for (src_if, network, mask) in nat_entries:
            real_obj = _ensure_static_object(network, mask, ctx)

            # --- NAT exemption (nat_id == 0) ---
            if nat_id == 0:
                emit_lines("nat_exempt.j2", {"src_if": src_if, "real_obj": real_obj}, ctx)
                continue

            global_entries = ctx.pix_global_rules.get(nat_id)
            if not global_entries:
                ctx.log(f"WARNING: No global for nat id {nat_id} on {src_if} {network} {mask}")
                emit_lines("passthrough.j2",
                           {"line": f"! pix2asa: no global for nat id {nat_id}: nat ({src_if}) {nat_id} {network} {mask}"},
                           ctx)
                continue

            # Group globals by dst_if — entries with the same (nat_id, dst_if) form a pool
            by_dst_if: dict[str, list[tuple[str, str]]] = {}
            for (dst_if, pool_spec, pool_type) in global_entries:
                by_dst_if.setdefault(dst_if, []).append((pool_spec, pool_type))

            for dst_if, pool_list in by_dst_if.items():
                non_iface = [(s, t) for (s, t) in pool_list if t != "interface"]
                has_iface  = any(t == "interface" for (_, t) in pool_list)

                if non_iface:
                    if len(non_iface) == 1:
                        mapped_obj = _resolve_pool_entry(non_iface[0][0], non_iface[0][1], ctx)
                    else:
                        # Multiple pool entries — emit object-group with inline member forms
                        members = [_resolve_pool_member(s, t, ctx) for (s, t) in non_iface]
                        group_name = f"natpool_{nat_id}_{dst_if}"
                        if group_name not in ctx.static_objects:
                            emit_lines("nat_pool_group.j2", {"name": group_name, "members": members}, ctx)
                            ctx.static_objects[group_name] = ("object-group", "", "")
                        mapped_obj = group_name
                    emit_lines("dynamic_nat.j2",
                               {"src_if": src_if, "dst_if": dst_if, "real_obj": real_obj, "mapped_obj": mapped_obj,
                                "pat_pool": ctx.target_version >= TargetVersion.ASA84},
                               ctx)

                if has_iface:
                    emit_lines("dynamic_nat.j2",
                               {"src_if": src_if, "dst_if": dst_if, "real_obj": real_obj, "mapped_obj": "interface",
                                "pat_pool": False},
                               ctx)

    # Warn about global entries that have no corresponding nat rule
    for nat_id in sorted(ctx.pix_global_rules):
        if nat_id not in ctx.pix_nat_rules:
            for (dst_if, pool_spec, pool_type) in ctx.pix_global_rules[nat_id]:
                ctx.log(f"WARNING: No nat rule for global id {nat_id} on {dst_if}")
                emit_lines("passthrough.j2",
                           {"line": f"! pix2asa: no nat rule for global id {nat_id}: global ({dst_if}) {nat_id} {pool_spec or 'interface'}"},
                           ctx)
