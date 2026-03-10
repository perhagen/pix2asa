"""ConversionContext — all mutable state for one PIX-to-ASA conversion pass.

Replaces the 15+ module-level globals in the original pix2asa.py.
A new instance is created per conversion; call reset() to reuse one.

Rust equivalent: a plain struct passed as &mut Context through every handler.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field

from .models import (
    ConfigLine,
    Inspect,
    InterfaceConfig,
    SourceVersion,
    TargetVersion,
)


@dataclass
class ConversionContext:
    """Holds all mutable state for a single PIX-to-ASA conversion pass."""

    # -----------------------------------------------------------------------
    # Conversion options (set once before the pass begins)
    # -----------------------------------------------------------------------
    source_version: SourceVersion = SourceVersion.PIX6
    target_version: TargetVersion = TargetVersion.ASA84
    target_platform: str = ""       # e.g. "asa-5520"
    custom_5505: bool = False
    boot_system: str = ""
    convert_names: bool = True   # when False, 'name' commands are passed through unchanged
    debug: bool = False

    # Original hostname before the '-migrated' suffix is appended (set by _handle_hostname)
    original_hostname: str = ""

    # -----------------------------------------------------------------------
    # Name-to-IP table (populated by 'name' command when convert_names=True)
    # -----------------------------------------------------------------------

    # name → ip  (e.g. "wmmgt.wm.orbitz.com" → "10.50.50.100")
    converted_names: dict[str, str] = field(default_factory=dict)
    # ip → name  (reverse lookup for ACL substitution)
    converted_names_r: dict[str, str] = field(default_factory=dict)

    # Auto-generated objects from static NAT commands: name → (type, ip, mask)
    # where type is "host" or "subnet"
    static_objects: dict[str, tuple[str, str, str]] = field(default_factory=dict)

    # PIX nat/global rule collectors (two-phase approach)
    # nat_id → list of (nameif, network, mask)
    pix_nat_rules: dict[int, list[tuple[str, str, str]]] = field(default_factory=dict)
    # nat_id → list of (nameif, pool_spec, pool_type)
    # pool_type: "host" | "range" | "interface"
    # pool_spec: "ip" for host, "ip1-ip2" for range, "" for interface
    pix_global_rules: dict[int, list[tuple[str, str, str]]] = field(default_factory=dict)

    # -----------------------------------------------------------------------
    # Interface tables
    # -----------------------------------------------------------------------

    # Physical interface name → InterfaceConfig
    interfaces: dict[str, InterfaceConfig] = field(default_factory=dict)

    # Logical (nameif) name → physical interface name
    name_ifs: dict[str, str] = field(default_factory=dict)
    # Reverse: physical name → logical name
    name_ifs_r: dict[str, str] = field(default_factory=dict)

    # physical/logical name → canonical physical name (for sub-interface vlan logic)
    logical_to_phys: dict[str, str] = field(default_factory=dict)
    logical_to_phys_r: dict[str, str] = field(default_factory=dict)

    # -----------------------------------------------------------------------
    # Interface platform mapping
    # -----------------------------------------------------------------------

    # source interface name → destination interface name
    platform_if_mapping: dict[str, str] = field(default_factory=dict)
    # Reverse: destination → source
    platform_if_mapping_r: dict[str, str] = field(default_factory=dict)

    # Index into the target device's ordered interface list
    platform_if_index: int = 0
    platform_if_exceeded: bool = False

    # -----------------------------------------------------------------------
    # Accumulated output
    # -----------------------------------------------------------------------

    # Ordered list of ConfigLine objects that form the converted config body
    config_lines: list[ConfigLine] = field(default_factory=list)

    # Inspect/fixup entries (rendered as a policy-map at the end)
    inspects: list[Inspect] = field(default_factory=list)

    # PPPoE VPDN group names (must be emitted before interface stanzas)
    vpdn_groups: list[str] = field(default_factory=list)

    # -----------------------------------------------------------------------
    # Log buffer (INFO / WARNING / ERROR messages)
    # -----------------------------------------------------------------------
    _log_buf: io.StringIO = field(default_factory=io.StringIO, repr=False)

    # Conduit tracking (PIX conduit → ACL-Global)
    conduit_seen: bool = False
    conduit_outside_ifs: set[str] = field(default_factory=set)

    # Static NAT address translation table, populated by _handle_pix_static and
    # _handle_pix_port_redirect during the engine pass.
    # mapped_ip → (src_if, dst_if, real_ip, mask)
    # Used by emit_conduit_acl_entries() to translate external IPs in conduit
    # rules to their real/internal equivalents, as required by ASA 8.4+ ACLs.
    static_nat_map: dict[str, tuple[str, str, str, str]] = field(default_factory=dict)

    # Collected conduit entries — parsed during the engine pass but not emitted
    # until post-processing (after static_nat_map is fully populated).
    # Each entry is a dict with keys:
    #   action, proto, dst_addr, dport_str, src_addr, sport_str, icmp_str, raw_line
    conduit_entries: list[dict] = field(default_factory=list)

    # Failover tracking
    failover_lan_if: str = ""
    failover_state_if: str = ""

    # -----------------------------------------------------------------------
    # Logging helpers
    # -----------------------------------------------------------------------

    def log(self, message: str = "") -> None:
        """Append *message* to the internal log buffer."""
        print(message, file=self._log_buf)

    def get_log(self) -> str:
        """Return the accumulated log output as a single string."""
        return self._log_buf.getvalue()

    # -----------------------------------------------------------------------
    # Interface mapping helpers
    # -----------------------------------------------------------------------

    def map_interface(self, source_if: str, target_if: str) -> None:
        """Record an explicit bidirectional interface mapping."""
        # Clean up any stale reverse entry for the old target of this source
        old_target = self.platform_if_mapping.get(source_if)
        if old_target and old_target != target_if:
            self.platform_if_mapping_r.pop(old_target, None)
        # Clean up any stale forward entry for the old source of this target
        old_source = self.platform_if_mapping_r.get(target_if)
        if old_source and old_source != source_if:
            self.platform_if_mapping.pop(old_source, None)
        self.platform_if_mapping[source_if] = target_if
        self.platform_if_mapping_r[target_if] = source_if

    def get_real_phys(self, name: str) -> str:
        """Resolve a logical name to its canonical physical interface name."""
        try:
            if name in self.name_ifs:
                phys = self.name_ifs[name]
                if phys not in self.interfaces and phys in self.logical_to_phys:
                    phys = self.logical_to_phys[phys]
                return phys
        except KeyError:
            self.log(f"ERROR: Could not find matching physical interface to {name}")
        # Fall through: name is already a physical name (identity)
        return name

    # -----------------------------------------------------------------------
    # Reset (allows reuse across multiple conversions in one process)
    # -----------------------------------------------------------------------

    def reset(self) -> None:
        """Clear all accumulated conversion state so this instance can be reused."""
        self.interfaces.clear()
        self.name_ifs.clear()
        self.name_ifs_r.clear()
        self.logical_to_phys.clear()
        self.logical_to_phys_r.clear()
        self.platform_if_mapping.clear()
        self.platform_if_mapping_r.clear()
        self.platform_if_index = 0
        self.platform_if_exceeded = False
        self.converted_names.clear()
        self.converted_names_r.clear()
        self.static_objects.clear()
        self.pix_nat_rules.clear()
        self.pix_global_rules.clear()
        self.config_lines.clear()
        self.inspects.clear()
        self.vpdn_groups.clear()
        self._log_buf = io.StringIO()
        self.conduit_seen = False
        self.conduit_outside_ifs.clear()
        self.static_nat_map.clear()
        self.conduit_entries.clear()
        self.failover_lan_if = ""
        self.failover_state_if = ""
        self.boot_system = ""
        self.target_platform = ""
        self.custom_5505 = False
