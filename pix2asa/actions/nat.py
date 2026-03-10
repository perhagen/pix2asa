"""Static NAT handlers and PIX nat/global collection for PIX-to-ASA conversion.

Covers:
  - Object name helpers (_ip_to_underscores, _mask_to_prefix, _auto_obj_name)
  - _ensure_static_object: creates/reuses 'object network' entries
  - _handle_pix_port_redirect: converts port-redirect static NAT
  - _handle_pix_static: converts IP-to-IP static NAT
  - _handle_nat / _handle_global: collect PIX nat/global rules for emit_nat_rules()
  - _handle_route / _handle_access_group: pass-through with failover warnings
  - _handle_access_list: injects 'extended' keyword into access-list lines
"""

from __future__ import annotations

import re

from ..context import ConversionContext
from ..rendering import emit_lines
from .misc import _repeat


# ---------------------------------------------------------------------------
# Dynamic NAT (nat/global pair) regexes
# ---------------------------------------------------------------------------

_NAT_FULL_RE = re.compile(
    r"nat\s+\((?P<nameif>\S+)\)\s+(?P<nat_id>\d+)\s+"
    r"(?P<network>\d{1,3}(?:\.\d{1,3}){3})\s+"
    r"(?P<mask>\d{1,3}(?:\.\d{1,3}){3})(?:\s+\S+)*\s*$",
    re.IGNORECASE,
)
_GLOBAL_IFACE_RE = re.compile(
    r"global\s+\((?P<nameif>\S+)\)\s+(?P<nat_id>\d+)\s+interface",
    re.IGNORECASE,
)
_GLOBAL_POOL_RE = re.compile(
    r"global\s+\((?P<nameif>\S+)\)\s+(?P<nat_id>\d+)\s+"
    r"(?P<ip1>\d{1,3}(?:\.\d{1,3}){3})(?:-(?P<ip2>\d{1,3}(?:\.\d{1,3}){3}))?"
    r"(?:\s+(?:netmask\s+)?(?P<mask>\d{1,3}(?:\.\d{1,3}){3}))?",
    re.IGNORECASE,
)

_IP4_BARE_RE = re.compile(r'^\d{1,3}(?:\.\d{1,3}){3}$')


# ---------------------------------------------------------------------------
# Object name helpers
# ---------------------------------------------------------------------------

def _ip_to_underscores(ip: str) -> str:
    """Convert an IP address string to an underscore-separated form safe for use as an object name."""
    return ip.replace(".", "_")


def _mask_to_prefix(mask: str) -> int:
    """Convert a dotted-decimal subnet mask to its CIDR prefix length."""
    return sum(bin(int(o)).count("1") for o in mask.split("."))


def _auto_obj_name(ip: str, mask: str) -> str:
    """Generate an auto object name for an IP/mask pair that has no name mapping.

    Host (255.255.255.255): ``host_<ip_underscored>``
    Subnet: ``net_<ip_underscored>_<prefix>``
    """
    if mask == "255.255.255.255":
        return f"host_{_ip_to_underscores(ip)}"
    prefix = _mask_to_prefix(mask)
    return f"net_{_ip_to_underscores(ip)}_{prefix}"


def _ensure_static_object(ip: str, mask: str, ctx: ConversionContext) -> str:
    """Return the object name for *ip*/*mask*, creating the object network entry if needed.

    If *ip* already has a ``name``-derived object (in ``converted_names_r``), return that name.
    Otherwise auto-generate a name, emit an ``object network`` block, and record the
    mapping in ``ctx.static_objects`` so the post-processing substitution pass can use it.
    """
    # Check if already has a name from a 'name' command
    if ip in ctx.converted_names_r:
        return ctx.converted_names_r[ip]
    obj_type = "host" if mask == "255.255.255.255" else "subnet"
    name = _auto_obj_name(ip, mask)
    if name not in ctx.static_objects:
        mask_part = f" {mask}" if obj_type == "subnet" else ""
        emit_lines("auto_object.j2", {"name": name, "type": obj_type, "ip": ip, "mask_part": mask_part}, ctx)
        ctx.static_objects[name] = (obj_type, ip, mask)
    return name


# ---------------------------------------------------------------------------
# Name-to-real-IP remapping helper
# ---------------------------------------------------------------------------

def _remap_name_to_real_ip(mapped_raw: str, real_raw: str, mask: str, ctx: ConversionContext) -> None:
    """If *mapped_raw* (an external/post-NAT IP) has a ``name``-derived object and *real_raw*
    (the internal/pre-NAT IP) does not, update the named object to refer to the real IP.

    Called at the start of static NAT handlers **before** any objects are resolved or emitted,
    so that downstream ``_resolve_static_field`` calls see the correct mappings and emit a
    clean NAT statement (``nat source static <name> <auto_mapped_obj>``) with no redundant
    auto-object for the real IP.

    Steps performed when the condition is met:
    1. Patch the ``object network`` body line already emitted by ``_handle_name``
       (`` host <mapped_ip>`` → `` host <real_ip>``).
    2. Update ``ctx.converted_names[name]`` = real_ip.
    3. Move the reverse entry: delete ``converted_names_r[mapped_ip]``,
       add ``converted_names_r[real_ip]`` = safe_name.
    4. Log an INFO message.

    Nothing is done when:
    - *mapped_raw* is not a bare IPv4 address (name-reference in mapped field).
    - The mapped IP has no ``name``-derived object.
    - The real IP already has its own ``name``-derived object (no remap needed).
    - mapped and real IPs are identical (identity NAT).
    """
    if not _IP4_BARE_RE.match(mapped_raw):
        return
    if mapped_raw not in ctx.converted_names_r:
        return

    # Resolve the real IP (bare IP or PIX name reference)
    if _IP4_BARE_RE.match(real_raw):
        real_ip = real_raw
    else:
        real_ip = ctx.converted_names.get(real_raw)
    if not real_ip or real_ip == mapped_raw or real_ip in ctx.converted_names_r:
        return

    safe_name = ctx.converted_names_r[mapped_raw]

    # Patch the object-body ConfigLine already emitted by _handle_name.
    # The body line is the first line matching " host <mapped_raw>" that follows
    # the object header "object network <safe_name>".
    obj_header = f"object network {safe_name}"
    old_body   = f" host {mapped_raw}"
    new_body   = f" host {real_ip}"
    patched = False
    for i, cfg_line in enumerate(ctx.config_lines):
        if cfg_line.text == obj_header:
            if i + 1 < len(ctx.config_lines) and ctx.config_lines[i + 1].text == old_body:
                ctx.config_lines[i + 1].text = new_body
                patched = True
                break
    if not patched:
        # Fallback: find the body line without the header anchor.
        # Should not normally be reached; logged so unexpected layouts are visible.
        ctx.log(
            f"WARNING: _remap_name_to_real_ip could not locate object header for "
            f"{safe_name!r} — using fallback body-line patch."
        )
        for cfg_line in ctx.config_lines:
            if cfg_line.text == old_body:
                cfg_line.text = new_body
                break

    # Update ALL forward-mapping entries pointing to the old mapped IP.
    # _handle_name stores converted_names[original_name] (not safe_name), so when
    # the name is an ASA reserved word (e.g. "source" → "source_object") the keys
    # differ.  Updating by value-scan covers both cases safely.
    for k in [k for k, v in ctx.converted_names.items() if v == mapped_raw]:
        ctx.converted_names[k] = real_ip
    del ctx.converted_names_r[mapped_raw]
    ctx.converted_names_r[real_ip] = safe_name
    ctx.log(
        f"INFO: name {safe_name!r} remapped {mapped_raw} → {real_ip} "
        f"(object now reflects real/internal address)"
    )


# ---------------------------------------------------------------------------
# Static NAT handlers
# ---------------------------------------------------------------------------

def _handle_pix_port_redirect(m: re.Match, ctx: ConversionContext) -> bool:
    """Convert a PIX port-redirect ``static`` to ASA object NAT with service redirect.

    PIX ``static (<src_if>,<dst_if>) tcp|udp <ext_addr> <ext_port> <int_ip> <int_port>``
    becomes an object-NAT block::

        object network <obj_name>
          host <int_ip>
          nat (<src_if>,<dst_if>) static <ext_addr> service <proto> <ext_port> <int_port>

    *ext_addr* is either an IP address or the keyword ``interface``.  Object names for the
    internal IP are resolved from existing ``name`` mappings or auto-generated.
    """
    src_if = m["src_if"]
    dst_if = m["dst_if"]
    proto = m["proto"].lower()
    ext_addr = m["ext_addr"]
    ext_port = m["ext_port"]
    int_ip = m["int_ip"]
    int_port = m["int_port"]

    # If the external IP has a name, remap it to the internal (real) IP so the
    # named object represents the server's actual address.
    if ext_addr != "interface":
        _remap_name_to_real_ip(ext_addr, int_ip, "255.255.255.255", ctx)

    obj_name = ctx.converted_names_r.get(int_ip) or _auto_obj_name(int_ip, "255.255.255.255")
    emit_lines("port_redirect_nat.j2", {
        "obj_name": obj_name,
        "int_ip": int_ip,
        "src_if": src_if,
        "dst_if": dst_if,
        "ext_addr": ext_addr,
        "proto": proto,
        "ext_port": ext_port,
        "int_port": int_port,
    }, ctx)
    ctx.conduit_outside_ifs.add(dst_if)
    if obj_name not in ctx.static_objects:
        ctx.static_objects[obj_name] = ("host", int_ip, "255.255.255.255")
    # Record in static_nat_map so conduit rules referencing ext_addr can be
    # translated to the real (internal) IP when emitting ACL entries.
    if ext_addr != "interface" and ext_addr not in ctx.static_nat_map:
        ctx.static_nat_map[ext_addr] = (src_if, dst_if, int_ip, "255.255.255.255")
    return True


def _resolve_static_field(field: str, mask: str, ctx: ConversionContext) -> tuple[str, str]:
    """Resolve a static NAT field (IP address *or* PIX name) to *(ip, obj_name)*.

    - IP address → create/reuse object via ``_ensure_static_object``
    - PIX name (defined by a ``name`` command) → look up the IP and reuse the
      existing safe object name already stored in ``ctx.converted_names_r``
    """
    if _IP4_BARE_RE.match(field):
        return field, _ensure_static_object(field, mask, ctx)
    # It's a PIX name reference
    ip = ctx.converted_names.get(field)
    if ip:
        obj_name = ctx.converted_names_r.get(ip, field)
        return ip, obj_name
    # Unknown token — fall back to treating as IP (best effort)
    return field, _ensure_static_object(field, mask, ctx)


def _handle_pix_static(m: re.Match, ctx: ConversionContext) -> bool:
    """Convert a PIX ``static`` NAT command to ASA object-based NAT syntax.

    PIX ``static (inside,outside) <mapped> <real> netmask <mask>`` becomes:
    - One or two ``object network`` blocks (host or subnet type) for any IPs that lack
      an existing ``name``-derived object.
    - A ``nat (<src_if>,<dst_if>) source static <real_obj> <mapped_obj>`` statement.

    Both *mapped* and *real* fields may be either a dotted-decimal IP address or a
    PIX ``name`` label defined earlier in the config.

    If *mapped* and *real* resolve to the same IP (identity NAT), a single object is
    created and referenced on both sides of the ``nat`` statement.
    """
    src_if = m["src_if"]
    dst_if = m["dst_if"]
    mask = m["mask"]

    # If the mapped IP has a name, remap it to the real (internal) IP so the
    # named object reflects the server's actual address, not its NAT alias.
    _remap_name_to_real_ip(m["mapped"], m["real"], mask, ctx)

    real_ip, real_obj = _resolve_static_field(m["real"], mask, ctx)
    mapped_ip, mapped_obj = _resolve_static_field(m["mapped"], mask, ctx)
    if real_ip == mapped_ip:
        mapped_obj = real_obj  # identity NAT — same object on both sides
    emit_lines("static_nat.j2", {
        "src_if": src_if,
        "dst_if": dst_if,
        "real_obj": real_obj,
        "mapped_obj": mapped_obj,
    }, ctx)
    ctx.conduit_outside_ifs.add(dst_if)
    # Record mapped→real mapping so conduit rules can be translated in
    # post-processing.  Only record the first mapping for a given mapped_ip;
    # duplicate mapped IPs would be a config error on the real device.
    if mapped_ip not in ctx.static_nat_map:
        ctx.static_nat_map[mapped_ip] = (src_if, dst_if, real_ip, mask)
    return True


# ---------------------------------------------------------------------------
# Dynamic NAT collection handlers
# ---------------------------------------------------------------------------

def _handle_nat(m: re.Match, ctx: ConversionContext) -> bool:
    """Collect a PIX nat rule for later pairing with global entries.

    The rule is stored in ``ctx.pix_nat_rules`` keyed by nat_id and emitted
    after the engine pass via :func:`emit_nat_rules`.  Lines that do not match
    the expected form are passed through unchanged.  Failover-interface usage
    is always flagged as an error regardless.
    """
    nameif = m["nameif"]
    # Failover check
    if nameif in ctx.name_ifs:
        phys = ctx.name_ifs[nameif]
        if phys in ctx.interfaces:
            iface = ctx.interfaces[phys]
            if iface.failover_lan or iface.failover_state:
                ctx.log(f"ERROR: Failover interface ({nameif}) used for data: {m.group(0)}")
                emit_lines("failover_warning.j2", {"nameif": nameif, "line": m.group(0)}, ctx)
    fm = _NAT_FULL_RE.match(m.group(0))
    if fm:
        nat_id = int(fm["nat_id"])
        ctx.pix_nat_rules.setdefault(nat_id, []).append(
            (nameif, fm["network"], fm["mask"])
        )
        return True   # consumed — emit_nat_rules handles output
    # Unrecognised form — pass through
    return _repeat(m, ctx)


def _handle_global(m: re.Match, ctx: ConversionContext) -> bool:
    """Collect a PIX global pool entry for later pairing with nat rules.

    Stored in ``ctx.pix_global_rules`` keyed by nat_id.  Three pool forms are
    recognised: a single IP host, an IP range (``ip1-ip2``), and the special
    ``interface`` keyword for PAT.  Unrecognised forms are passed through.
    """
    nameif = m["nameif"]
    # Failover check (reuse same logic as _handle_nat)
    if nameif in ctx.name_ifs:
        phys = ctx.name_ifs[nameif]
        if phys in ctx.interfaces:
            iface = ctx.interfaces[phys]
            if iface.failover_lan or iface.failover_state:
                ctx.log(f"ERROR: Failover interface ({nameif}) used for data: {m.group(0)}")
                emit_lines("failover_warning.j2", {"nameif": nameif, "line": m.group(0)}, ctx)
    # Interface PAT
    gi = _GLOBAL_IFACE_RE.match(m.group(0))
    if gi:
        nat_id = int(gi["nat_id"])
        ctx.pix_global_rules.setdefault(nat_id, []).append((nameif, "", "interface"))
        return True
    # IP / range pool
    gp = _GLOBAL_POOL_RE.match(m.group(0))
    if gp:
        nat_id = int(gp["nat_id"])
        ip1 = gp["ip1"]
        ip2 = gp["ip2"]
        mask = gp["mask"]
        if ip2:
            ctx.pix_global_rules.setdefault(nat_id, []).append(
                (nameif, f"{ip1}-{ip2}", "range")
            )
        elif mask and mask != "255.255.255.255":
            ctx.pix_global_rules.setdefault(nat_id, []).append(
                (nameif, f"{ip1}/{mask}", "subnet")
            )
        else:
            ctx.pix_global_rules.setdefault(nat_id, []).append(
                (nameif, ip1, "host")
            )
        return True
    return _repeat(m, ctx)


# ---------------------------------------------------------------------------
# Route / access-group / access-list pass-through handlers
# ---------------------------------------------------------------------------

def _handle_route(m: re.Match, ctx: ConversionContext) -> bool:
    """Pass route lines through unchanged, warning if the referenced interface is a failover interface."""
    nameif = m["nameif"]
    if nameif not in ctx.name_ifs:
        return _repeat(m, ctx)
    phys = ctx.name_ifs[nameif]
    if phys in ctx.interfaces:
        iface = ctx.interfaces[phys]
        if iface.failover_lan or iface.failover_state:
            ctx.log(f"ERROR: Failover interface ({nameif}) used for data: {m.group(0)}")
            emit_lines("failover_warning.j2", {"nameif": nameif, "line": m.group(0)}, ctx)
    return _repeat(m, ctx)


def _handle_access_group(m: re.Match, ctx: ConversionContext) -> bool:
    """Pass access-group lines through unchanged, warning if the interface is a failover interface."""
    nameif = m["nameif"]
    if nameif not in ctx.name_ifs:
        return _repeat(m, ctx)
    phys = ctx.name_ifs[nameif]
    if phys in ctx.interfaces:
        iface = ctx.interfaces[phys]
        if iface.failover_lan or iface.failover_state:
            ctx.log(f"ERROR: Failover interface ({nameif}) used for data: {m.group(0)}")
    return _repeat(m, ctx)


def _handle_access_list(m: re.Match, ctx: ConversionContext) -> bool:
    """Pass access-list lines through, injecting the 'extended' keyword required by ASA 7.x named ACLs.

    Name-to-object substitution is applied globally by apply_name_substitutions()
    after the engine pass — not here.
    """
    line = m.group(0)

    # Inject 'extended' after 'access-list <name> permit|deny'
    # PIX: access-list acl_out permit ...
    # ASA: access-list acl_out extended permit ...
    line = re.sub(
        r'^(access-list\s+\S+\s+)(permit|deny)(\s)',
        r'\1extended \2\3',
        line,
        flags=re.IGNORECASE,
    )

    emit_lines("passthrough.j2", {"line": line}, ctx)
    return True
