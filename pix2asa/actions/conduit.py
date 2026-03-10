"""PIX conduit/apply/outbound conversion to ASA extended access-lists.

PIX conduit rules reference **external/mapped** IP addresses — the addresses
the outside world sees after static NAT.  ASA 8.4+ access-list rules for
inbound traffic use **real/internal** IP addresses (the un-NATed destination).

To handle both orderings (conduit before or after static in the config) the
handler collects structured entries into ctx.conduit_entries during the engine
pass.  emit_conduit_acl_entries() then translates mapped→real using the
static_nat_map built by the static NAT handlers, and emits the final ACL lines.

Covers:
  - Conduit address/port token parsers
  - _handle_conduit: collects each conduit line for post-processing
  - _translate_mapped_addr: maps external IP to internal IP via static_nat_map
  - emit_conduit_acl_entries: translates + emits ACL lines (post-processing)
  - emit_conduit_access_groups: emits access-group statements (post-processing)
"""

from __future__ import annotations

import re

from ..context import ConversionContext
from ..rendering import emit_lines


_CONDUIT_ACL_NAME = "ACL-Global"


# ---------------------------------------------------------------------------
# Conduit token parsers
# ---------------------------------------------------------------------------

def _parse_conduit_addr(tokens: list[str], i: int) -> tuple[str, int]:
    """Parse an address token group from a conduit command at position *i*.

    Recognises three forms: ``any`` (single token), ``host <ip>`` (two tokens),
    and ``<ip> <mask>`` (two tokens).  Returns the formatted address string and
    the updated index.
    """
    if i >= len(tokens):
        return "", i
    if tokens[i] == "any":
        return "any", i + 1
    if tokens[i] == "host":
        if i + 1 >= len(tokens):
            return "", i
        return f"host {tokens[i+1]}", i + 2
    # ip mask form
    if i + 1 < len(tokens):
        return f"{tokens[i]} {tokens[i+1]}", i + 2
    return tokens[i], i + 1


def _parse_conduit_port(tokens: list[str], i: int) -> tuple[str, int]:
    """Parse an optional port qualifier from a conduit command at position *i*.

    Recognises ``eq``, ``gt``, ``lt``, ``neq`` (single port) and ``range``
    (two ports).  Returns an empty string and unchanged index if no port
    qualifier is found.
    """
    if i >= len(tokens):
        return "", i
    op = tokens[i]
    if op in ("eq", "gt", "lt", "neq"):
        if i + 1 >= len(tokens):
            return "", i
        return f"{op} {tokens[i+1]}", i + 2
    if op == "range":
        if i + 2 >= len(tokens):
            return "", i
        return f"range {tokens[i+1]} {tokens[i+2]}", i + 3
    return "", i


def _is_address_start(token: str) -> bool:
    """Return True if *token* looks like the start of an address group (any/host/IP)."""
    return token == "any" or token == "host" or (len(token) > 0 and token[0].isdigit())


# ---------------------------------------------------------------------------
# Address translation
# ---------------------------------------------------------------------------

def _translate_mapped_addr(addr: str, ctx: ConversionContext) -> str:
    """Translate an external/mapped address to its real/internal equivalent.

    Uses ``ctx.static_nat_map`` (populated by ``_handle_pix_static`` and
    ``_handle_pix_port_redirect`` during the engine pass).

    Three address forms are handled:
    - ``any``              → unchanged (no NAT translation needed)
    - ``host <ip>``        → ``host <real_ip>`` if *ip* is in static_nat_map
    - ``<ip> <mask>``      → ``<real_ip> <mask>`` if *ip* is in static_nat_map

    If the IP is not found in static_nat_map, the address is returned unchanged
    and a WARNING is logged so the operator can review the output.
    """
    if addr == "any":
        return addr

    # host <ip> form
    m = re.match(r'^host\s+(\S+)$', addr, re.IGNORECASE)
    if m:
        mapped_ip = m.group(1)
        entry = ctx.static_nat_map.get(mapped_ip)
        if entry:
            _, _, real_ip, _ = entry
            return f"host {real_ip}"
        ctx.log(
            f"WARNING: conduit references {mapped_ip!r} but no static NAT entry found — "
            f"address left as-is; verify this ACL entry manually."
        )
        return addr

    # <ip> <mask> subnet form
    m = re.match(r'^(\S+)\s+(\S+)$', addr)
    if m:
        mapped_ip, mask = m.group(1), m.group(2)
        entry = ctx.static_nat_map.get(mapped_ip)
        if entry:
            _, _, real_ip, _ = entry
            return f"{real_ip} {mask}"
        ctx.log(
            f"WARNING: conduit references {mapped_ip!r} but no static NAT entry found — "
            f"address left as-is; verify this ACL entry manually."
        )
        return addr

    return addr


def _conduit_substitute(line: str, ctx: ConversionContext) -> str:
    """Replace ``host <real_ip>`` with ``object <name>`` where a named object exists.

    Called after _translate_mapped_addr so that substitution operates on the
    real (internal) IP, which is what the object network entries are keyed on.
    """
    ip_to_obj: dict[str, str] = dict(ctx.converted_names_r)
    for obj_name, (_type, ip, _mask) in ctx.static_objects.items():
        if ip not in ip_to_obj:
            ip_to_obj[ip] = obj_name

    def _repl(m: re.Match) -> str:
        ip = m.group(1)
        if ip in ip_to_obj:
            return f"object {ip_to_obj[ip]}"
        return m.group(0)

    return re.sub(r'\bhost\s+(\S+)', _repl, line)


# ---------------------------------------------------------------------------
# Conduit handler — collect during engine pass
# ---------------------------------------------------------------------------

def _handle_conduit(m: re.Match, ctx: ConversionContext) -> bool:
    """Parse a PIX ``conduit`` command and collect it for post-processing.

    Conduit rules reference **external/mapped** destination IPs.  Rather than
    emitting ACL lines immediately (when static_nat_map may be incomplete), the
    parsed entry is stored in ``ctx.conduit_entries``.

    ``emit_conduit_acl_entries()`` translates the destination addresses and
    emits the final ACL lines after the full engine pass completes.
    """
    tokens = m.group(0).split()
    if len(tokens) < 4:
        emit_lines("conduit_unsupported.j2", {"line": m.group(0)}, ctx)
        return True

    action = tokens[1]   # permit / deny
    proto  = tokens[2]   # tcp / udp / ip / icmp
    i = 3

    dst_addr, i = _parse_conduit_addr(tokens, i)

    dport_str = ""
    icmp_str  = ""
    if proto == "icmp":
        if i < len(tokens) and not _is_address_start(tokens[i]):
            icmp_str = tokens[i]
            i += 1
    else:
        dport_str, i = _parse_conduit_port(tokens, i)

    src_addr, i = _parse_conduit_addr(tokens, i)

    sport_str = ""
    if proto not in ("icmp", "ip"):
        sport_str, i = _parse_conduit_port(tokens, i)

    ctx.conduit_entries.append({
        "action":    action,
        "proto":     proto,
        "dst_addr":  dst_addr,
        "dport_str": dport_str,
        "src_addr":  src_addr,
        "sport_str": sport_str,
        "icmp_str":  icmp_str,
        "raw_line":  m.group(0),
    })
    ctx.conduit_seen = True
    return True


# ---------------------------------------------------------------------------
# Post-processing
# ---------------------------------------------------------------------------

def _log_nat_table(ctx: ConversionContext) -> None:
    """Log the static NAT translation table to the conversion log.

    Called by ``emit_conduit_acl_entries`` when ``ctx.debug`` is True.
    Each entry shows: mapped_ip → (src_if, dst_if, real_ip, mask).
    """
    ctx.log("DEBUG: NAT Translation Table (mapped → real):")
    if not ctx.static_nat_map:
        ctx.log("DEBUG:   (empty — no static NAT entries found)")
        return
    for mapped_ip, (src_if, dst_if, real_ip, mask) in sorted(ctx.static_nat_map.items()):
        ctx.log(
            f"DEBUG:   {mapped_ip} → {real_ip}"
            f"  [mask={mask}  src_if={src_if}  dst_if={dst_if}]"
        )


def emit_conduit_acl_entries(ctx: ConversionContext) -> None:
    """Translate and emit ACL lines for all collected conduit entries.

    Called once from ``emit_conduit_access_groups`` after the engine pass, so
    that ``ctx.static_nat_map`` is fully populated before translation occurs.

    For each entry:
    1. Translate the destination address from mapped (external) to real (internal)
       using ``ctx.static_nat_map``.
    2. Apply object substitution (``host <real_ip>`` → ``object <name>``).
    3. Emit the final ``access-list ACL-Global extended ...`` line.
    """
    if ctx.debug:
        _log_nat_table(ctx)
    for entry in ctx.conduit_entries:
        action    = entry["action"]
        proto     = entry["proto"]
        src_addr  = entry["src_addr"] or "any"
        sport_str = entry["sport_str"]
        icmp_str  = entry["icmp_str"]

        # Translate destination from external/mapped to real/internal
        dst_addr  = _translate_mapped_addr(entry["dst_addr"], ctx)
        dport_str = entry["dport_str"]

        src_part   = f" {src_addr}"
        sport_part = f" {sport_str}"  if sport_str  else ""
        dst_part   = f" {dst_addr}"   if dst_addr   else " any"
        dport_part = f" {dport_str}"  if dport_str  else ""
        icmp_part  = f" {icmp_str}"   if icmp_str   else ""

        acl_line = (
            f"access-list {_CONDUIT_ACL_NAME} extended {action} {proto}"
            f"{src_part}{sport_part}{dst_part}{dport_part}{icmp_part}"
        )

        # Replace host <real_ip> with object <name> where a named object exists
        acl_line = _conduit_substitute(acl_line, ctx)

        ctx.log(f"INFO: conduit → ACL: {entry['raw_line']!r} → {acl_line!r}")
        emit_lines("passthrough.j2", {"line": acl_line}, ctx)


def emit_conduit_access_groups(ctx: ConversionContext) -> None:
    """Emit translated ACL entries and ``access-group`` statements.

    Called once after the engine pass.  Emits (in order):
    1. All translated ``access-list ACL-Global`` entries.
    2. One ``access-group ACL-Global in interface <nameif>`` per outside
       interface discovered from ``static`` commands.
    3. The global catch-all ``access-group ACL-Global global``.
    """
    if not ctx.conduit_seen:
        return
    emit_conduit_acl_entries(ctx)
    for nameif in sorted(ctx.conduit_outside_ifs):
        emit_lines("passthrough.j2",
                   {"line": f"access-group {_CONDUIT_ACL_NAME} in interface {nameif}"},
                   ctx)
    emit_lines("passthrough.j2",
               {"line": f"access-group {_CONDUIT_ACL_NAME} global"},
               ctx)
