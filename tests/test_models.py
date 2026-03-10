"""Tests for pix2asa.models — dataclasses, enums, device registry."""

from __future__ import annotations

import pytest
from pix2asa.models import (
    ConfigLine,
    Inspect,
    InterfaceConfig,
    SourceVersion,
    TARGET_DEVICES,
    VALID_TARGET_SLUGS,
    TargetDevice,
    TargetVersion,
)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class TestEnums:
    def test_source_version_values(self):
        assert SourceVersion.PIX6 == 6
        assert SourceVersion.PIX7 == 7

    def test_target_version_ordering(self):
        assert TargetVersion.ASA84 == 84

    def test_target_version_comparison(self):
        from pix2asa.models import TargetVersion
        assert TargetVersion.ASA84 >= TargetVersion.ASA84
        assert TargetVersion.ASA84 == 84


# ---------------------------------------------------------------------------
# Device registry
# ---------------------------------------------------------------------------

class TestDeviceRegistry:
    def test_target_devices_loaded(self):
        assert len(TARGET_DEVICES) >= 16

    def test_known_slugs_present(self):
        for slug in ("asa-5505", "asa-5520", "asa-5540", "asa-5550", "custom"):
            assert slug in TARGET_DEVICES, f"Missing slug: {slug}"

    def test_valid_slugs_frozenset(self):
        assert isinstance(VALID_TARGET_SLUGS, frozenset)
        assert "asa-5520" in VALID_TARGET_SLUGS

    def test_target_device_is_frozen(self):
        dev = TARGET_DEVICES["asa-5520"]
        with pytest.raises((AttributeError, TypeError)):
            dev.slug = "hacked"  # type: ignore[misc]

    def test_interfaces_are_tuple(self):
        for dev in TARGET_DEVICES.values():
            assert isinstance(dev.interfaces, tuple)

    def test_5505_detection(self):
        assert TARGET_DEVICES["asa-5505"].is_5505 is True
        assert TARGET_DEVICES["asa-5505-plus"].is_5505 is True
        assert TARGET_DEVICES["asa-5520"].is_5505 is False

    def test_max_vlans_positive(self):
        # 'custom' has max_vlans=0 by design (no fixed interface list)
        for slug, dev in TARGET_DEVICES.items():
            if slug != "custom":
                assert dev.max_vlans > 0, f"{slug}.max_vlans should be > 0"


# ---------------------------------------------------------------------------
# InterfaceConfig
# ---------------------------------------------------------------------------

class TestInterfaceConfig:
    def test_set_nameif(self):
        iface = InterfaceConfig("ethernet0", mapped_name="GigabitEthernet0/0")
        iface.set_nameif("outside", 0)
        assert iface.nameif == "outside"
        assert iface.security_level == 0

    def test_set_nameif_string_level(self):
        iface = InterfaceConfig("ethernet1", mapped_name="GigabitEthernet0/1")
        iface.set_nameif("inside", "100")
        assert iface.security_level == 100

    def test_render_static_ip(self):
        iface = InterfaceConfig("ethernet0", mapped_name="GigabitEthernet0/0")
        iface.set_nameif("outside", 0)
        iface.ip_address = "10.0.0.1"
        iface.netmask = "255.255.255.0"
        rendered = iface.render()
        assert "interface GigabitEthernet0/0" in rendered
        assert "nameif outside" in rendered
        assert "security-level 0" in rendered
        assert "ip address 10.0.0.1 255.255.255.0" in rendered
        assert "no shutdown" in rendered

    def test_render_dhcp(self):
        iface = InterfaceConfig("ethernet0", mapped_name="GigabitEthernet0/0")
        iface.set_nameif("outside", 0)
        iface.set_dhcp(set_route=True)
        rendered = iface.render()
        assert "ip address dhcp setroute" in rendered

    def test_render_pppoe(self):
        iface = InterfaceConfig("ethernet0", mapped_name="GigabitEthernet0/0")
        iface.set_nameif("outside", 0)
        iface.set_pppoe(set_route=False)
        rendered = iface.render()
        assert "ip address pppoe" in rendered

    def test_render_with_standby(self):
        iface = InterfaceConfig("ethernet0", mapped_name="GigabitEthernet0/0")
        iface.set_nameif("outside", 0)
        iface.ip_address = "10.0.0.1"
        iface.netmask = "255.255.255.0"
        iface.standby_ip = "10.0.0.2"
        rendered = iface.render()
        assert "standby 10.0.0.2" in rendered

    def test_render_with_mtu(self):
        iface = InterfaceConfig("ethernet0", mapped_name="GigabitEthernet0/0")
        iface.set_nameif("outside", 0)
        iface.mtu = 1500  # mtu is stored as int
        rendered = iface.render()
        assert "mtu 1500" in rendered

    def test_render_ends_with_bang(self):
        iface = InterfaceConfig("ethernet0", mapped_name="GigabitEthernet0/0")
        iface.set_nameif("outside", 0)
        assert iface.render().strip().endswith("!")

    def test_set_vlan(self):
        iface = InterfaceConfig("ethernet0.10", mapped_name="GigabitEthernet0/0.10")
        iface.set_vlan("10")
        assert iface.vlan == "10"

    def test_failover_lan_flag(self):
        iface = InterfaceConfig("ethernet2", mapped_name="GigabitEthernet0/2")
        iface.set_failover_lan()
        assert iface.failover_lan is True  # field is failover_lan, not is_failover_lan


# ---------------------------------------------------------------------------
# ConfigLine
# ---------------------------------------------------------------------------

class TestConfigLine:
    def test_passthrough(self):
        line = ConfigLine("hostname myfirewall")
        assert line.render() == "hostname myfirewall"

    def test_interface_marker(self):
        line = ConfigLine("__INTERFACE__")
        line.mark_interface("ethernet0")
        assert line.is_interface_marker()
        assert line.get_interface() == "ethernet0"
        assert not line.is_inspect_marker()

    def test_inspect_marker(self):
        line = ConfigLine("__INSPECT__")
        line.mark_inspect()
        assert line.is_inspect_marker()
        assert not line.is_interface_marker()

    def test_failover_lan_marker(self):
        line = ConfigLine("failover lan interface failover ethernet2")
        line.set_failover_lan("ethernet2")
        assert line.is_failover_lan()
        assert not line.is_failover_link()

    def test_failover_link_marker(self):
        line = ConfigLine("failover link failover ethernet2")
        line.set_failover_link("ethernet2")
        assert line.is_failover_link()


# ---------------------------------------------------------------------------
# Inspect
# ---------------------------------------------------------------------------

class TestInspect:
    def test_render_basic(self):
        ins = Inspect(name="ftp")
        assert "inspect ftp" in ins.render()

    def test_render_negated(self):
        ins = Inspect(name="ftp", negated=True)
        assert "no inspect ftp" in ins.render()

    def test_render_with_port(self):
        ins = Inspect(name="http", port="8080")
        rendered = ins.render()
        assert "inspect http" in rendered

    def test_dns_skipped_in_render(self):
        # DNS is handled separately in _render_inspects; render() returns ""
        ins = Inspect(name="dns", port="512")
        assert ins.render() == ""
