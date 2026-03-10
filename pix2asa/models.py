"""Domain model dataclasses for pix2asa.

All classes use explicit typed fields — no class-level mutable state,
no dynamic attribute assignment — to ease the eventual Rust port.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class SourceVersion(IntEnum):
    """Supported source PIX OS major versions."""

    PIX6 = 6
    PIX7 = 7


class TargetVersion(IntEnum):
    """Supported target ASA software versions."""

    ASA84 = 84


# ---------------------------------------------------------------------------
# Device model (loaded from data/devices.json)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TargetDevice:
    """Immutable descriptor for a supported Cisco ASA target platform."""

    slug: str
    display_name: str
    family: str
    model: int
    max_vlans: int
    min_asa_version: str
    interfaces: tuple[str, ...]
    switchport_prefix: str = ""
    max_asa_version: str = ""

    @property
    def is_5505(self) -> bool:
        """Return True if this device is the ASA 5505 model."""
        return self.model == 5505


@dataclass(frozen=True)
class SourceDevice:
    """Immutable descriptor identifying the source PIX device being converted."""

    family: str
    model: int
    type_name: str
    max_vlans: int


_DEVICES_JSON = Path(__file__).parent / "data" / "devices.json"

def _load_target_devices() -> dict[str, TargetDevice]:
    """Load and return a slug-keyed dict of TargetDevice objects from devices.json."""
    data = json.loads(_DEVICES_JSON.read_text())
    result: dict[str, TargetDevice] = {}
    for d in data["target_devices"]:
        dev = TargetDevice(
            slug=d["slug"],
            display_name=d["display_name"],
            family=d["family"],
            model=d["model"],
            max_vlans=d["max_vlans"],
            min_asa_version=d["min_asa_version"],
            interfaces=tuple(d["interfaces"]),
            switchport_prefix=d.get("switchport_prefix", ""),
            max_asa_version=d.get("max_asa_version", ""),
        )
        result[dev.slug] = dev
    return result


# Module-level registry — immutable after import.
TARGET_DEVICES: dict[str, TargetDevice] = _load_target_devices()
VALID_TARGET_SLUGS: frozenset[str] = frozenset(TARGET_DEVICES.keys())


# ---------------------------------------------------------------------------
# Per-conversion domain objects
# ---------------------------------------------------------------------------

@dataclass
class InterfaceConfig:
    """Represents a single network interface being converted."""

    phys_name: str
    speed: str = "auto"
    state: str = "no shutdown"
    logical: bool = False

    # Set by nameif command
    nameif: str = ""
    security_level: int = 0

    # Layer 3
    ip_address: str = ""
    netmask: str = ""
    standby_ip: str = ""
    dhcp: bool = False
    pppoe: bool = False
    set_route: bool = False

    # Sub-interface / VLAN
    vlan: str = ""
    mtu: int = 0
    duplex: str = ""

    # Failover roles
    failover_lan: bool = False
    failover_state: bool = False

    # Mapped destination interface name (populated during conversion)
    mapped_name: str = ""

    def set_nameif(self, name: str, level: int | str = 0) -> None:
        """Set the logical interface name and its security level."""
        self.nameif = name
        self.security_level = int(level)

    def set_logical(self) -> None:
        """Mark this interface as a logical (sub-interface) rather than a physical port."""
        self.logical = True

    def set_vlan(self, vlan: str) -> None:
        """Assign a VLAN ID to this interface."""
        self.vlan = vlan

    def set_dhcp(self, set_route: bool = False) -> None:
        """Configure this interface to obtain its IP address via DHCP."""
        self.dhcp = True
        self.set_route = set_route

    def set_pppoe(self, set_route: bool = False) -> None:
        """Configure this interface to obtain its IP address via PPPoE."""
        self.pppoe = True
        self.set_route = set_route

    def set_failover_lan(self) -> None:
        """Mark this interface as the failover LAN link."""
        self.failover_lan = True

    def set_failover_state(self) -> None:
        """Mark this interface as the failover state link."""
        self.failover_state = True

    def render(self) -> str:
        """Return ASA interface stanza as a string, rendered from interface_stanza.j2."""
        from pix2asa.rendering import render_template
        mapped = self.mapped_name or self.phys_name
        return render_template("interface_stanza.j2", {
            "mapped": mapped,
            "logical": self.logical,
            "vlan": self.vlan,
            "nameif": self.nameif,
            "security_level": self.security_level,
            "ip_address": self.ip_address,
            "netmask": self.netmask,
            "standby_ip": self.standby_ip,
            "dhcp": self.dhcp,
            "pppoe": self.pppoe,
            "set_route": self.set_route,
            "mtu": self.mtu,
            "duplex": self.duplex,
            "speed": self.speed,
            "state": self.state,
        })


@dataclass
class ConfigLine:
    """One line (or marker) in the converted output config."""

    text: str
    _interface: str = field(default="", repr=False)
    _inspect_marker: bool = field(default=False, repr=False)
    _failover_lan: str = field(default="", repr=False)
    _failover_link: str = field(default="", repr=False)

    # --- marker setters ---

    def mark_interface(self, name: str) -> None:
        """Tag this line as a placeholder for interface *name*."""
        self._interface = name

    def mark_inspect(self) -> None:
        """Tag this line as the inspect/policy-map insertion point."""
        self._inspect_marker = True

    def set_failover_lan(self, if_id: str) -> None:
        """Associate this line with the failover LAN interface *if_id*."""
        self._failover_lan = if_id

    def set_failover_link(self, if_id: str) -> None:
        """Associate this line with the failover state link interface *if_id*."""
        self._failover_link = if_id

    # --- predicates ---

    def is_interface_marker(self) -> bool:
        """Return True if this line marks an interface insertion point."""
        return bool(self._interface)

    def get_interface(self) -> str:
        """Return the interface name stored in this marker, or an empty string."""
        return self._interface

    def is_inspect_marker(self) -> bool:
        """Return True if this line marks the inspect policy-map insertion point."""
        return self._inspect_marker

    def is_failover_lan(self) -> bool:
        """Return True if this line is associated with the failover LAN interface."""
        return bool(self._failover_lan)

    def is_failover_link(self) -> bool:
        """Return True if this line is associated with the failover state link interface."""
        return bool(self._failover_link)

    def render(self) -> str:
        """Return the raw config text for this line."""
        return self.text


@dataclass
class Inspect:
    """Represents a fixup/inspect protocol entry."""

    name: str
    port: str = "0"
    port1: str = "0"
    port_range: bool = False
    negated: bool = False   # True when the original line was "no fixup ..."

    def render(self) -> str:
        """Return the ASA inspect sub-command string, or an empty string for DNS."""
        if self.name == "dns":
            return ""   # dns rendered separately via policy-map
        prefix = "  no inspect" if self.negated else "  inspect"
        return f"{prefix} {self.name}"
