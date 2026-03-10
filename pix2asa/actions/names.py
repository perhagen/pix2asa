"""PIX 'name' command conversion and name-to-object substitution.

Handles:
  - _handle_name: converts 'name <ip> <host>' to ASA 'object network' host blocks
  - _substitute_name_refs: replaces 'host <ip/name>' with 'object <name>' in a line
  - apply_name_substitutions: post-processing pass over all config lines
"""

from __future__ import annotations

import re

from ..context import ConversionContext
from ..rendering import emit_lines


# ASA keywords that are invalid as object-network names in NAT/ACL statements.
# When a PIX 'name' command uses one of these, the object is renamed <name>_object.
_ASA_RESERVED_NAMES: frozenset[str] = frozenset({
    "source", "destination", "any", "interface", "static", "dynamic",
    "object", "host", "network", "service", "route", "permit", "deny",
    "extended", "standard", "inactive", "log", "description",
})

# Matches the body line of an 'object network' stanza: " host <ip>" (leading whitespace, nothing else).
# These lines define the object itself and must NOT be substituted — they ARE the definition.
_OBJECT_BODY_RE = re.compile(r'^\s+host\s+\S+\s*$')


def _handle_name(m: re.Match, ctx: ConversionContext) -> bool:
    """Convert PIX 'name <ip> <hostname> [description <text>]' to an ASA host object.

    PIX:  name 10.50.50.100 wmmgt.wm.orbitz.com
    ASA:  object network wmmgt.wm.orbitz.com
           host 10.50.50.100

    When ctx.convert_names is False the original line is passed through unchanged.
    Populates ctx.converted_names / converted_names_r for later ACL substitution.

    If the hostname conflicts with an ASA reserved keyword (e.g. ``source``,
    ``destination``, ``any``) it is renamed to ``<name>_object`` to avoid
    producing ambiguous NAT or ACL statements.
    """
    if not ctx.convert_names:
        emit_lines("passthrough.j2", {"line": m.group(0)}, ctx)
        return True
    ip = m["ip"]
    name = m["name"]
    desc = m.groupdict().get("desc") or ""
    safe_name = f"{name}_object" if name.lower() in _ASA_RESERVED_NAMES else name
    if safe_name != name:
        ctx.log(f"INFO: name {name!r} conflicts with ASA keyword — renamed to {safe_name!r}")
    ctx.converted_names[name] = ip          # original name → IP (for ACL name-ref lookup)
    ctx.converted_names_r[ip] = safe_name   # IP → safe object name
    emit_lines("name_object.j2", {"name": safe_name, "ip": ip, "desc": desc.strip()}, ctx)
    ctx.log(f"INFO: name {ip} {name} -> object network {safe_name} host {ip}")
    return True


def _substitute_name_refs(line: str, ctx: ConversionContext, ip_to_obj: dict[str, str] | None = None) -> str:
    """Replace 'host <ip_or_name>' with 'object <name>' for every converted name.

    Handles both forms that appear in PIX access-lists:
      host 10.50.50.100      → object wmmgt.wm.orbitz.com  (IP lookup)
      host wmmgt.wm.orbitz.com → object wmmgt.wm.orbitz.com  (name lookup)

    *ip_to_obj* is an optional pre-built IP→name map (covers both ``name``-derived and
    auto-generated static NAT objects).  When omitted, falls back to ``ctx.converted_names_r``.
    """
    if not ctx.convert_names:
        return line
    _ip_map: dict[str, str] = ip_to_obj if ip_to_obj is not None else ctx.converted_names_r
    if not _ip_map and not ctx.converted_names:
        return line

    def _repl(mo: re.Match) -> str:
        """Return the object-reference replacement string for a matched 'host' token."""
        token = mo.group(1)
        # IP in reverse map
        name = _ip_map.get(token)
        if name:
            return f"object {name}"
        # Name itself was converted — look up the safe object name via IP
        if token in ctx.converted_names:
            obj_ip = ctx.converted_names[token]
            safe = _ip_map.get(obj_ip, token)
            return f"object {safe}"
        return mo.group(0)  # no match — leave unchanged

    return re.sub(r'\bhost\s+(\S+)', _repl, line)


def apply_nat_remap_to_names(ctx: ConversionContext) -> None:
    """Post-processing catch-up remap for names whose ``static`` preceded their ``name``.

    The engine-pass remap in ``_remap_name_to_real_ip`` only fires when the ``name``
    command appears *before* the ``static`` in the config.  In the reverse order the
    engine pass has no name entry to consult, so the named object is left pointing to
    the mapped (external) IP.

    This function runs after the full engine pass, when both ``converted_names_r`` and
    ``static_nat_map`` are complete.  Any named object whose IP is still present as a
    *mapped* address in ``static_nat_map`` (i.e. the engine-pass remap did not fire) is
    patched here:

    1. The ``object network`` body line is updated (`` host mapped`` → `` host real``).
    2. All ``converted_names`` forward-mapping keys pointing to ``mapped_ip`` are updated.
    3. The reverse entry is moved: ``converted_names_r[mapped_ip]`` →
       ``converted_names_r[real_ip]``.
    4. A WARNING is logged so the operator knows the NAT statement will reference
       auto-generated objects rather than the named object (the NAT line was already
       emitted during the engine pass and cannot be retroactively rewritten).
    """
    if not ctx.convert_names or not ctx.static_nat_map:
        return

    # Collect candidates: a named IP that is a mapped address with a different real IP
    # and whose real IP has no name of its own.  (If the real IP already has a name the
    # engine-pass remap would have been blocked by the `real_ip in converted_names_r`
    # guard, and no action is needed here either.)
    to_remap = [
        (mapped_ip, safe_name)
        for mapped_ip, safe_name in list(ctx.converted_names_r.items())
        if mapped_ip in ctx.static_nat_map
        and ctx.static_nat_map[mapped_ip][2] != mapped_ip
        and ctx.static_nat_map[mapped_ip][2] not in ctx.converted_names_r
    ]

    for mapped_ip, safe_name in to_remap:
        _, _, real_ip, _ = ctx.static_nat_map[mapped_ip]

        # Patch the object-body ConfigLine emitted by _handle_name
        obj_header = f"object network {safe_name}"
        old_body   = f" host {mapped_ip}"
        new_body   = f" host {real_ip}"
        patched = False
        for i, cfg_line in enumerate(ctx.config_lines):
            if cfg_line.text == obj_header:
                if i + 1 < len(ctx.config_lines) and ctx.config_lines[i + 1].text == old_body:
                    ctx.config_lines[i + 1].text = new_body
                    patched = True
                    break
        if not patched:
            for cfg_line in ctx.config_lines:
                if cfg_line.text == old_body:
                    cfg_line.text = new_body
                    break

        # Update forward-mapping entries (original name key, not safe_name)
        for k in [k for k, v in ctx.converted_names.items() if v == mapped_ip]:
            ctx.converted_names[k] = real_ip
        del ctx.converted_names_r[mapped_ip]
        ctx.converted_names_r[real_ip] = safe_name

        ctx.log(
            f"WARNING: name {safe_name!r} was defined after its static NAT — "
            f"object body patched {mapped_ip} → {real_ip} in post-processing; "
            f"NAT statement uses auto-generated object names."
        )


def apply_name_substitutions(ctx: ConversionContext) -> None:
    """Apply name-to-object substitution to every collected config line.

    Called once after the engine pass completes, before rendering.  Replaces
    ``host <ip>`` and ``host <name>`` tokens with ``object <name>`` in ALL
    non-marker config lines — not just access-list lines.  This ensures that
    object-group entries, aaa-server, snmp-server, and any other line that
    references a converted name is updated consistently.

    Lines that are ``object network`` definition bodies (e.g., `` host 10.x.x.x``)
    are intentionally skipped — they define the object and must not be self-referencing.

    The reverse mapping is built from both ``ctx.converted_names_r`` (populated by
    ``_handle_name`` during the engine pass) and ``ctx.static_objects`` (populated by
    ``_handle_pix_static`` for auto-generated NAT objects).
    """
    if not ctx.convert_names:
        return
    # Build combined IP→object name map covering 'name' commands and static NAT objects
    ip_to_obj: dict[str, str] = dict(ctx.converted_names_r)
    for obj_name, (_, ip, _mask) in ctx.static_objects.items():
        if ip not in ip_to_obj:
            ip_to_obj[ip] = obj_name
    if not ip_to_obj and not ctx.converted_names:
        return
    for cfg_line in ctx.config_lines:
        if cfg_line.is_interface_marker() or cfg_line.is_inspect_marker():
            continue
        if _OBJECT_BODY_RE.match(cfg_line.text):
            continue  # skip object-network body definition lines
        cfg_line.text = _substitute_name_refs(cfg_line.text, ctx, ip_to_obj)
