"""Tests for pix2asa.converter — the pure convert() entry point."""

from __future__ import annotations

import pytest

from pix2asa.converter import ConversionOptions, ConversionResult, convert
from pix2asa.models import SourceVersion, TargetVersion

from .conftest import opts


# ---------------------------------------------------------------------------
# Minimal inline configs
# ---------------------------------------------------------------------------

PIX6_MINIMAL = """\
: Saved
:
PIX Version 6.3(1)
interface ethernet0 auto
interface ethernet1 100full
nameif ethernet0 outside security0
nameif ethernet1 inside security100
hostname testfw
domain-name example.com
fixup protocol ftp 21
fixup protocol http 80
fixup protocol dns maximum-length 512
no fixup protocol smtp 25
mtu outside 1500
mtu inside 1500
ip address outside 10.0.0.1 255.255.255.0
ip address inside 192.168.1.1 255.255.255.0
: end
"""

PIX6_DHCP = """\
PIX Version 6.3(1)
interface ethernet0 auto
interface ethernet1 100full
nameif ethernet0 outside security0
nameif ethernet1 inside security100
ip address outside dhcp setroute
ip address inside 192.168.1.1 255.255.255.0
: end
"""

PIX6_PPPOE = """\
PIX Version 6.3(1)
interface ethernet0 auto
interface ethernet1 100full
nameif ethernet0 outside security0
nameif ethernet1 inside security100
vpdn group mypppoe request dialout pppoe
ip address outside pppoe setroute
ip address inside 192.168.1.1 255.255.255.0
: end
"""

PIX6_FAILOVER = """\
PIX Version 6.3(5)
interface ethernet0 auto
interface ethernet1 auto
interface ethernet2 auto
nameif ethernet0 outside security0
nameif ethernet1 inside security100
nameif ethernet2 failover security90
ip address outside 10.0.0.1 255.255.255.0
ip address inside 192.168.1.1 255.255.255.0
failover ip address outside 10.0.0.2
failover ip address inside 192.168.1.2
failover poll 15
: end
"""

PIX6_CUSTOM_IFACE = """\
PIX Version 6.3(1)
interface ethernet0 auto
interface ethernet1 100full
nameif ethernet0 outside security0
nameif ethernet1 inside security100
ip address outside 10.0.0.1 255.255.255.0
ip address inside 192.168.1.1 255.255.255.0
: end
"""


# ---------------------------------------------------------------------------
# Return type
# ---------------------------------------------------------------------------

class TestConvertReturnType:
    def test_returns_conversion_result(self):
        result = convert(PIX6_MINIMAL, opts())
        assert isinstance(result, ConversionResult)

    def test_output_is_str(self):
        result = convert(PIX6_MINIMAL, opts())
        assert isinstance(result.output, str)

    def test_log_is_str(self):
        result = convert(PIX6_MINIMAL, opts())
        assert isinstance(result.log, str)

    def test_warnings_is_list(self):
        result = convert(PIX6_MINIMAL, opts())
        assert isinstance(result.warnings, list)

    def test_errors_is_list(self):
        result = convert(PIX6_MINIMAL, opts())
        assert isinstance(result.errors, list)


# ---------------------------------------------------------------------------
# Output header
# ---------------------------------------------------------------------------

class TestOutputHeader:
    def test_asa_version_header_84(self):
        result = convert(PIX6_MINIMAL, opts())
        assert result.output.startswith("ASA Version 8.4")

    def test_pix_version_line_removed(self):
        result = convert(PIX6_MINIMAL, opts())
        assert "PIX Version" not in result.output

    def test_end_line_removed(self):
        result = convert(PIX6_MINIMAL, opts())
        assert ": end" not in result.output

    def test_cryptochecksum_removed(self):
        """Cryptochecksum: line must be stripped — hash varies per config and is no longer valid."""
        cfg = "PIX Version 6.3\nCryptochecksum:78d170ad73fc3964b4c512ecfe3f0514\n"
        result = convert(cfg, opts())
        assert "Cryptochecksum" not in result.output


# ---------------------------------------------------------------------------
# Interface stanzas
# ---------------------------------------------------------------------------

class TestInterfaceOutput:
    def test_outside_interface_present(self):
        result = convert(PIX6_MINIMAL, opts())
        assert "nameif outside" in result.output

    def test_inside_interface_present(self):
        result = convert(PIX6_MINIMAL, opts())
        assert "nameif inside" in result.output

    def test_ip_address_in_interface(self):
        result = convert(PIX6_MINIMAL, opts())
        assert "ip address 10.0.0.1 255.255.255.0" in result.output

    def test_security_levels(self):
        result = convert(PIX6_MINIMAL, opts())
        assert "security-level 0" in result.output
        assert "security-level 100" in result.output

    def test_mtu_in_interface(self):
        result = convert(PIX6_MINIMAL, opts())
        assert "mtu 1500" in result.output

    def test_dhcp_interface(self):
        result = convert(PIX6_DHCP, opts())
        assert "ip address dhcp setroute" in result.output

    def test_pppoe_interface(self):
        result = convert(PIX6_PPPOE, opts())
        assert "ip address pppoe" in result.output

    def test_vpdn_group_before_interfaces(self):
        result = convert(PIX6_PPPOE, opts())
        vpdn_pos = result.output.find("vpdn group")
        iface_pos = result.output.find("interface ")
        assert vpdn_pos < iface_pos, "vpdn group must appear before interface stanzas"


# ---------------------------------------------------------------------------
# Failover
# ---------------------------------------------------------------------------

class TestFailoverOutput:
    def test_standby_ip_in_output(self):
        result = convert(PIX6_FAILOVER, opts())
        assert "standby 10.0.0.2" in result.output

    def test_failover_polltime_normalised(self):
        result = convert(PIX6_FAILOVER, opts())
        # "failover polltime 15" must appear as a command (not just in the :::: comment)
        output_commands = [l for l in result.output.splitlines() if not l.startswith("::::")]
        assert any("failover polltime 15" in l for l in output_commands)
        assert not any(l.strip() == "failover poll 15" for l in output_commands)


# ---------------------------------------------------------------------------
# Inspect / policy-map
# ---------------------------------------------------------------------------

class TestInspectOutput:
    def test_policy_map_present(self):
        result = convert(PIX6_MINIMAL, opts())
        assert "policy-map global_policy" in result.output

    def test_service_policy_present(self):
        result = convert(PIX6_MINIMAL, opts())
        assert "service-policy global_policy global" in result.output

    def test_inspect_ftp_present(self):
        result = convert(PIX6_MINIMAL, opts())
        assert "inspect ftp" in result.output

    def test_inspect_http_present(self):
        result = convert(PIX6_MINIMAL, opts())
        assert "inspect http" in result.output

    def test_no_inspect_smtp(self):
        result = convert(PIX6_MINIMAL, opts())
        assert "no inspect esmtp" in result.output or "no inspect smtp" in result.output

    def test_dns_policy_map(self):
        result = convert(PIX6_MINIMAL, opts())
        assert "policy-map type inspect dns" in result.output
        assert "message-length maximum 512" in result.output

    def test_bare_h323_emits_both_subtypes(self):
        """'fixup protocol h323 1720' (bare, no qualifier) → inspect h323 h225 AND inspect h323 ras."""
        cfg = "PIX Version 6.3\nfixup protocol h323 1720\n"
        result = convert(cfg, opts())
        assert "inspect h323 h225" in result.output
        assert "inspect h323 ras" in result.output

    def test_no_bare_h323_negates_both_subtypes(self):
        """'no fixup protocol h323 1720' → no inspect h323 h225 AND no inspect h323 ras."""
        cfg = "PIX Version 6.3\nno fixup protocol h323 1720\n"
        result = convert(cfg, opts())
        assert "no inspect h323 h225" in result.output
        assert "no inspect h323 ras" in result.output

    def test_generic_fallback_unknown_protocol(self):
        """fixup for an unrecognised protocol is caught by generic fallback."""
        cfg = "PIX Version 6.3\nfixup protocol myproto 9999\n"
        result = convert(cfg, opts())
        assert "inspect myproto" in result.output


# ---------------------------------------------------------------------------
# Hostname renaming
# ---------------------------------------------------------------------------

class TestHostnameRename:
    def test_hostname_suffixed(self):
        result = convert(PIX6_MINIMAL, opts())
        assert "hostname testfw-migrated" in result.output

    def test_original_hostname_removed(self):
        result = convert(PIX6_MINIMAL, opts())
        assert "hostname testfw\n" not in result.output


# ---------------------------------------------------------------------------
# Custom interface mapping
# ---------------------------------------------------------------------------

class TestCustomInterfaceMapping:
    def test_explicit_mapping_applied(self):
        result = convert(
            PIX6_CUSTOM_IFACE,
            opts(platform="", interface_map={"ethernet0": "GigabitEthernet0/0",
                                              "ethernet1": "GigabitEthernet0/1"}),
        )
        assert "interface GigabitEthernet0/0" in result.output
        assert "interface GigabitEthernet0/1" in result.output

    def test_mapping_comment_in_output(self):
        result = convert(
            PIX6_CUSTOM_IFACE,
            opts(platform="", interface_map={"ethernet0": "GigabitEthernet0/0",
                                              "ethernet1": "GigabitEthernet0/1"}),
        )
        assert "Interface mapping" in result.output


# ---------------------------------------------------------------------------
# Log content
# ---------------------------------------------------------------------------

class TestLogContent:
    def test_log_contains_info(self):
        result = convert(PIX6_MINIMAL, opts())
        assert "INFO:" in result.log

    def test_warnings_extracted(self):
        # floodguard produces a WARNING
        config = PIX6_MINIMAL + "floodguard enable\n"
        result = convert(config, opts())
        # If floodguard matched, it should appear in warnings
        assert all(w.startswith("WARNING:") for w in result.warnings)

    def test_errors_extracted(self):
        result = convert(PIX6_MINIMAL, opts())
        assert all(e.startswith("ERROR:") for e in result.errors)

    def test_no_errors_clean_config(self):
        result = convert(PIX6_MINIMAL, opts())
        assert result.errors == []


# ---------------------------------------------------------------------------
# name command → host object
# ---------------------------------------------------------------------------

class TestNameCommand:
    NAME_CONFIG = """\
PIX Version 6.3
name 10.50.50.100 wmmgt.wm.orbitz.com
name 192.168.1.1 inside-gw description Default gateway
"""

    def test_basic_name_becomes_object(self):
        result = convert(self.NAME_CONFIG, opts())
        assert "object network wmmgt.wm.orbitz.com" in result.output
        assert " host 10.50.50.100" in result.output

    def test_name_with_description(self):
        result = convert(self.NAME_CONFIG, opts())
        assert "object network inside-gw" in result.output
        assert " host 192.168.1.1" in result.output
        assert " description Default gateway" in result.output

    def test_name_without_description_no_desc_line(self):
        result = convert(self.NAME_CONFIG, opts())
        lines = result.output.splitlines()
        obj_idx = next(i for i, l in enumerate(lines) if "wmmgt.wm.orbitz.com" in l)
        block = "\n".join(lines[obj_idx : obj_idx + 3])
        assert "description" not in block

    def test_name_logged(self):
        result = convert(self.NAME_CONFIG, opts())
        assert "wmmgt.wm.orbitz.com" in result.log

    def test_works_in_pix7(self):
        result = convert(self.NAME_CONFIG, opts(src=7))
        assert "object network wmmgt.wm.orbitz.com" in result.output

    def test_convert_names_false_passes_through(self):
        from pix2asa.converter import ConversionOptions
        from pix2asa.models import SourceVersion, TargetVersion
        o = ConversionOptions(
            source_version=SourceVersion.PIX6,
            target_version=TargetVersion.ASA84,
            convert_names=False,
        )
        result = convert(self.NAME_CONFIG, o)
        assert "object network" not in result.output
        assert "name 10.50.50.100 wmmgt.wm.orbitz.com" in result.output

    def test_convert_names_true_is_default(self):
        from pix2asa.converter import ConversionOptions
        from pix2asa.models import SourceVersion, TargetVersion
        o = ConversionOptions(
            source_version=SourceVersion.PIX6,
            target_version=TargetVersion.ASA84,
        )
        assert o.convert_names is True


# ---------------------------------------------------------------------------
# access-list: name-object substitution + extended keyword
# ---------------------------------------------------------------------------

class TestAccessListNameSubstitution:
    BASE = """\
PIX Version 6.3
name 10.50.50.100 wmmgt.wm.orbitz.com
name 192.168.1.1 inside-gw
"""

    def _convert(self, extra="", **kw):
        from pix2asa.converter import ConversionOptions
        from pix2asa.models import SourceVersion, TargetVersion
        o = ConversionOptions(
            source_version=SourceVersion.PIX6,
            target_version=TargetVersion.ASA84,
            **kw,
        )
        return convert(self.BASE + extra, o)

    def test_ip_replaced_by_object(self):
        r = self._convert("access-list acl permit tcp any host 10.50.50.100 eq 443\n")
        assert "object wmmgt.wm.orbitz.com" in r.output
        # The access-list line itself must not contain host <ip>
        acl_line = next(l for l in r.output.splitlines() if l.startswith("access-list"))
        assert "host 10.50.50.100" not in acl_line

    def test_name_replaced_by_object(self):
        r = self._convert("access-list acl permit tcp any host wmmgt.wm.orbitz.com eq 80\n")
        assert "object wmmgt.wm.orbitz.com" in r.output
        assert "host wmmgt.wm.orbitz.com" not in r.output

    def test_unrelated_host_unchanged(self):
        r = self._convert("access-list acl permit tcp any host 10.10.10.1 eq 22\n")
        assert "host 10.10.10.1" in r.output

    def test_extended_injected(self):
        r = self._convert("access-list acl permit tcp any any\n")
        assert "access-list acl extended permit" in r.output

    def test_no_substitution_when_convert_names_false(self):
        r = self._convert(
            "access-list acl permit tcp any host 10.50.50.100 eq 443\n",
            convert_names=False,
        )
        assert "object" not in r.output
        assert "host 10.50.50.100" in r.output

    def test_remark_line_unchanged(self):
        r = self._convert("access-list acl remark This is a comment\n")
        assert "access-list acl remark This is a comment" in r.output


# ---------------------------------------------------------------------------
# Universal name substitution (non-access-list lines)
# ---------------------------------------------------------------------------

class TestUniversalNameSubstitution:
    """Verify that host <ip> references are replaced in ALL output lines,
    not just access-list lines."""

    BASE = """\
PIX Version 6.3
name 10.4.32.81 db-primary
name 172.20.32.100 mgmt-server
"""

    def _convert(self, extra=""):
        from pix2asa.converter import ConversionOptions
        from pix2asa.models import SourceVersion, TargetVersion
        o = ConversionOptions(source_version=SourceVersion.PIX6, target_version=TargetVersion.ASA84)
        return convert(self.BASE + extra, o)

    def test_network_object_host_substituted(self):
        """network-object host <ip> in object-group body → network-object object <name>."""
        r = self._convert("object-group network DB_SERVERS\n  network-object host 10.4.32.81\n")
        assert "network-object object db-primary" in r.output
        assert "network-object host 10.4.32.81" not in r.output

    def test_aaa_server_host_substituted(self):
        """aaa-server ... host <ip> → aaa-server ... object <name>."""
        r = self._convert("aaa-server TACACS+ (inside) host 172.20.32.100 secret timeout 5\n")
        aaa_line = next(l for l in r.output.splitlines() if l.startswith("aaa-server"))
        assert "object mgmt-server" in aaa_line
        assert "host 172.20.32.100" not in aaa_line

    def test_snmp_server_host_syntax_note(self):
        """snmp-server uses 'host <nameif> <ip>' — 'host' precedes the nameif, not the IP.
        The bare IP is not substituted (it doesn't follow 'host' directly)."""
        r = self._convert("snmp-server host inside 10.4.32.81\n")
        # IP present but not preceded by 'host' — remains unchanged
        assert "10.4.32.81" in r.output

    def test_object_definition_body_not_substituted(self):
        """The ' host <ip>' body of the object network definition must not be self-replaced."""
        r = self._convert()
        assert " host 10.4.32.81" in r.output
        assert " host 172.20.32.100" in r.output

    def test_unrelated_host_ip_not_substituted(self):
        """host <ip> where ip has no name mapping must remain unchanged."""
        r = self._convert("aaa-server TACACS+ (inside) host 10.99.99.99 secret timeout 5\n")
        aaa_line = next(l for l in r.output.splitlines() if l.startswith("aaa-server"))
        assert "host 10.99.99.99" in aaa_line
        assert "object" not in aaa_line

    def test_no_substitution_when_convert_names_false(self):
        """When convert_names=False, nothing is substituted anywhere."""
        from pix2asa.converter import ConversionOptions
        from pix2asa.models import SourceVersion, TargetVersion
        o = ConversionOptions(
            source_version=SourceVersion.PIX6,
            target_version=TargetVersion.ASA84,
            convert_names=False,
        )
        r = convert(self.BASE + "aaa-server TACACS+ (inside) host 10.4.32.81 secret timeout 5\n", o)
        assert "object db-primary" not in r.output
        aaa_line = next(l for l in r.output.splitlines() if l.startswith("aaa-server"))
        assert "host 10.4.32.81" in aaa_line

    def test_converted_names_in_result(self):
        """ConversionResult.converted_names must contain the name→IP mapping."""
        r = self._convert()
        assert r.converted_names == {"db-primary": "10.4.32.81", "mgmt-server": "172.20.32.100"}


# ---------------------------------------------------------------------------
# Real sample configs (integration-level)
# ---------------------------------------------------------------------------

class TestRealConfigs:
    """These use the actual files from configs/; marked as integration tests."""

    @pytest.mark.integration
    def test_pix501(self, pix501_config):
        result = convert(pix501_config, opts("asa-5505"))
        assert result.output.startswith("ASA Version")
        assert "nameif outside" in result.output
        assert "policy-map global_policy" in result.output

    @pytest.mark.integration
    def test_pix515_fo(self, pix515_fo_config):
        result = convert(pix515_fo_config, opts("asa-5520"))
        assert result.output.startswith("ASA Version")
        assert "nameif outside" in result.output

    @pytest.mark.integration
    def test_pix535(self, pix535_config):
        result = convert(pix535_config, opts("asa-5580-4ge"))
        assert result.output.startswith("ASA Version")

    @pytest.mark.integration
    def test_pix38_large(self, pix38_config):
        result = convert(pix38_config, opts("asa-5520"))
        lines = result.output.splitlines()
        assert len(lines) > 100
        assert result.output.startswith("ASA Version")

    @pytest.mark.integration
    def test_pix525_latin1(self, pix525_latin1_config):
        result = convert(pix525_latin1_config, opts("asa-5520"))
        assert result.output.startswith("ASA Version")

    @pytest.mark.integration
    def test_conduit(self, conduit_config):
        result = convert(conduit_config, opts("asa-5520"))
        assert result.output.startswith("ASA Version")

    @pytest.mark.integration
    def test_pix535_trunk(self, pix535_trunk_config):
        result = convert(pix535_trunk_config, opts("asa-5580-4ge"))
        assert result.output.startswith("ASA Version")

    @pytest.mark.integration
    def test_all_real_configs_produce_output(
        self,
        pix501_config,
        pix515_fo_config,
        pix535_config,
        pix38_config,
        pix525_latin1_config,
        conduit_config,
        pix535_trunk_config,
    ):
        configs = [
            (pix501_config, "asa-5505"),
            (pix515_fo_config, "asa-5520"),
            (pix535_config, "asa-5580-4ge"),
            (pix38_config, "asa-5520"),
            (pix525_latin1_config, "asa-5520"),
            (conduit_config, "asa-5520"),
            (pix535_trunk_config, "asa-5580-4ge"),
        ]
        for config, platform in configs:
            result = convert(config, opts(platform))
            assert result.output, f"Empty output for platform {platform}"
            assert result.output.startswith("ASA Version")


# ---------------------------------------------------------------------------
# Static NAT conversion
# ---------------------------------------------------------------------------

class TestStaticNatConversion:
    """Tests for PIX static NAT → ASA object-based NAT conversion."""

    def _convert(self, config: str, convert_names: bool = True):
        from pix2asa.converter import ConversionOptions
        from pix2asa.models import SourceVersion, TargetVersion
        o = ConversionOptions(
            source_version=SourceVersion.PIX6,
            target_version=TargetVersion.ASA84,
            convert_names=convert_names,
        )
        return convert("PIX Version 6.3\n" + config, o)

    def test_host_static_both_named(self):
        """Both IPs have name mappings — no extra object network blocks; nat uses names."""
        config = (
            "name 192.168.1.100 webserver\n"
            "name 198.51.100.101 webserver-ext\n"
            "static (inside,outside) 198.51.100.101 192.168.1.100 netmask 255.255.255.255\n"
        )
        r = self._convert(config)
        # Named objects from 'name' commands must be present
        assert "object network webserver" in r.output
        assert "object network webserver-ext" in r.output
        # No auto-generated host_ objects
        assert "object network host_" not in r.output
        # nat statement uses name-derived objects
        assert "nat (inside,outside) source static webserver webserver-ext" in r.output

    def test_host_static_no_names(self):
        """Neither IP has a name mapping — auto objects are created."""
        config = (
            "static (inside,outside) 198.51.100.101 192.168.1.100 netmask 255.255.255.255\n"
        )
        r = self._convert(config)
        assert "object network host_192_168_1_100" in r.output
        assert "object network host_198_51_100_101" in r.output
        assert "nat (inside,outside) source static host_192_168_1_100 host_198_51_100_101" in r.output

    def test_host_static_only_real_named(self):
        """Real IP named, mapped IP gets an auto object."""
        config = (
            "name 192.168.1.100 webserver\n"
            "static (inside,outside) 198.51.100.101 192.168.1.100 netmask 255.255.255.255\n"
        )
        r = self._convert(config)
        # named object used for real
        assert "nat (inside,outside) source static webserver host_198_51_100_101" in r.output
        # auto object for mapped
        assert "object network host_198_51_100_101" in r.output
        # no redundant host_ for real
        assert "host_192_168_1_100" not in r.output

    def test_subnet_static(self):
        """Subnet static NAT produces net_ auto objects with prefix notation."""
        config = (
            "static (inside,outside) 10.0.0.0 192.168.0.0 netmask 255.255.255.0\n"
        )
        r = self._convert(config)
        assert "object network net_192_168_0_0_24" in r.output
        assert "object network net_10_0_0_0_24" in r.output
        assert "nat (inside,outside) source static net_192_168_0_0_24 net_10_0_0_0_24" in r.output

    def test_identity_subnet_static(self):
        """Identity NAT (mapped == real) produces a single object used on both sides."""
        config = (
            "static (inside,outside) 192.168.0.0 192.168.0.0 netmask 255.255.255.0\n"
        )
        r = self._convert(config)
        # Only one object network block for this name
        obj_count = r.output.count("object network net_192_168_0_0_24")
        assert obj_count == 1
        assert "nat (inside,outside) source static net_192_168_0_0_24 net_192_168_0_0_24" in r.output

    def test_acl_substitution_for_static_objects(self):
        """Auto-created static NAT objects feed into apply_name_substitutions for ACL rewriting."""
        config = (
            "static (inside,outside) 198.51.100.101 192.168.1.100 netmask 255.255.255.255\n"
            "access-list outside permit tcp any host 192.168.1.100 eq 80\n"
        )
        r = self._convert(config, convert_names=True)
        # The ACL should reference the auto-generated object, not the raw IP
        acl_line = next(l for l in r.output.splitlines() if l.startswith("access-list"))
        assert "object host_192_168_1_100" in acl_line
        assert "host 192.168.1.100" not in acl_line

    def test_static_with_name_in_real_field(self):
        """static real field can be a PIX name (not just an IP); name object is reused."""
        config = (
            "name 192.168.254.2 bdns1\n"
            "static (inside,outside) 198.51.100.10 bdns1 netmask 255.255.255.255\n"
        )
        r = self._convert(config)
        assert "object network bdns1" in r.output
        assert "nat (inside,outside) source static bdns1" in r.output
        # No duplicate auto host_ object for the inside address
        assert "host_192_168_254_2" not in r.output

    def test_static_with_name_in_mapped_field(self):
        """static mapped field can also be a PIX name."""
        config = (
            "name 192.168.254.2 bdns1\n"
            "name 198.51.100.10 ext-dns\n"
            "static (inside,outside) ext-dns bdns1 netmask 255.255.255.255\n"
        )
        r = self._convert(config)
        assert "nat (inside,outside) source static bdns1 ext-dns" in r.output

    def test_reserved_keyword_name_renamed(self):
        """PIX name that is an ASA reserved keyword is renamed to <name>_object."""
        config = (
            "name 192.168.254.2 bdns1\n"
            "name 198.164.220.2 source\n"
            "static (inside,outside) 198.164.220.2 bdns1 netmask 255.255.255.255 0 0\n"
        )
        r = self._convert(config)
        # 'source' renamed to 'source_object'
        assert "object network source_object" in r.output
        assert "object network source\n" not in r.output
        # nat statement uses safe name
        assert "nat (inside,outside) source static bdns1 source_object" in r.output

    def test_reserved_keyword_name_in_acl(self):
        """Renamed keyword-conflicting object is also used correctly in ACL substitution."""
        config = (
            "name 198.164.220.2 source\n"
            "access-list outside permit tcp any host 198.164.220.2 eq 80\n"
        )
        r = self._convert(config, convert_names=True)
        acl_line = next(l for l in r.output.splitlines() if l.startswith("access-list"))
        assert "object source_object" in acl_line
        assert "object source " not in acl_line


class TestPortRedirectStaticConversion:
    """Tests for PIX port-redirect static → ASA object NAT with service redirect."""

    def _convert(self, config: str, convert_names: bool = True):
        from pix2asa.converter import ConversionOptions
        from pix2asa.models import SourceVersion, TargetVersion
        o = ConversionOptions(
            source_version=SourceVersion.PIX6,
            target_version=TargetVersion.ASA84,
            convert_names=convert_names,
        )
        return convert("PIX Version 6.3\n" + config, o)

    def test_tcp_interface_ext_addr(self):
        """interface keyword as external address → passes through as 'interface' in nat."""
        config = "static (inside,outside) tcp interface 15001 192.168.0.1 https\n"
        r = self._convert(config)
        assert "object network host_192_168_0_1" in r.output
        assert " host 192.168.0.1" in r.output
        assert "nat (inside,outside) static interface service tcp 15001 https" in r.output

    def test_tcp_explicit_ext_ip(self):
        """Explicit external IP in tcp port redirect."""
        config = "static (inside,outside) tcp 198.51.100.101 80 192.168.1.100 8080\n"
        r = self._convert(config)
        assert "object network host_192_168_1_100" in r.output
        assert " host 192.168.1.100" in r.output
        assert "nat (inside,outside) static 198.51.100.101 service tcp 80 8080" in r.output

    def test_udp_port_redirect(self):
        """UDP port redirect — proto is lower-cased in output."""
        config = "static (inside,outside) udp 198.51.100.101 53 192.168.0.53 53\n"
        r = self._convert(config)
        assert "nat (inside,outside) static 198.51.100.101 service udp 53 53" in r.output

    def test_named_internal_ip_uses_existing_object(self):
        """When internal IP has a name mapping, that object name is reused."""
        config = (
            "name 192.168.1.100 webserver\n"
            "static (inside,outside) tcp interface 443 192.168.1.100 443\n"
        )
        r = self._convert(config)
        assert "object network webserver" in r.output
        assert "nat (inside,outside) static interface service tcp 443 443" in r.output
        assert "host_192_168_1_100" not in r.output

    def test_does_not_match_ip_only_static(self):
        """IP-only static (no tcp/udp) still routes to the old handler, not port-redirect."""
        config = "static (inside,outside) 198.51.100.101 192.168.1.100 netmask 255.255.255.255\n"
        r = self._convert(config)
        # Old handler emits twice-NAT form, NOT the port-redirect object-NAT form
        assert "nat (inside,outside) source static" in r.output
        assert "service tcp" not in r.output
        assert "service udp" not in r.output

    def test_port_redirect_does_not_emit_netmask_auto_object(self):
        """Port redirect never emits a subnet auto_object — only host objects."""
        config = "static (inside,outside) tcp interface 8080 10.0.0.5 8080\n"
        r = self._convert(config)
        assert "object network host_10_0_0_5" in r.output
        assert "subnet" not in r.output


class TestNatGlobalConversion:
    """Tests for PIX nat/global pair → ASA dynamic object-based NAT conversion."""

    def _convert(self, config: str, convert_names: bool = True):
        from pix2asa.converter import ConversionOptions
        from pix2asa.models import SourceVersion, TargetVersion
        o = ConversionOptions(
            source_version=SourceVersion.PIX6,
            target_version=TargetVersion.ASA84,
            convert_names=convert_names,
        )
        return convert("PIX Version 6.3\n" + config, o)

    def test_single_host_global(self):
        """Single-host global produces dynamic NAT with host_ auto-objects."""
        config = (
            "nat (inside) 1 10.0.0.0 255.0.0.0\n"
            "global (outside) 1 198.51.100.10\n"
        )
        r = self._convert(config)
        assert "object network net_10_0_0_0_8" in r.output
        assert "object network host_198_51_100_10" in r.output
        assert "nat (inside,outside) source dynamic net_10_0_0_0_8 pat-pool host_198_51_100_10 destination static any any" in r.output

    def test_ip_range_global(self):
        """IP range global produces a range_ auto-object and dynamic NAT."""
        config = (
            "nat (inside) 1 192.168.0.0 255.255.255.0\n"
            "global (outside) 1 198.51.100.2-198.51.100.254 netmask 255.255.255.0\n"
        )
        r = self._convert(config)
        assert "object network net_192_168_0_0_24" in r.output
        assert "object network range_198_51_100_2_198_51_100_254" in r.output
        assert "nat (inside,outside) source dynamic net_192_168_0_0_24 pat-pool range_198_51_100_2_198_51_100_254 destination static any any" in r.output

    def test_interface_pat(self):
        """Interface PAT global produces dynamic NAT with 'interface' as mapped object."""
        config = (
            "nat (inside) 1 10.0.0.0 255.0.0.0\n"
            "global (outside) 1 interface\n"
        )
        r = self._convert(config)
        assert "object network net_10_0_0_0_8" in r.output
        assert "nat (inside,outside) source dynamic net_10_0_0_0_8 interface destination static any any" in r.output

    def test_nat_exemption_id_zero(self):
        """nat_id=0 produces ASA identity/exemption NAT (source static <obj> <obj>)."""
        config = "nat (inside) 0 192.168.1.0 255.255.255.0\n"
        r = self._convert(config)
        assert "object network net_192_168_1_0_24" in r.output
        assert "nat (inside,any) source static net_192_168_1_0_24 net_192_168_1_0_24 destination static any any" in r.output

    def test_named_inside_network(self):
        """Named inside network reuses the name-derived object, not an auto net_ object."""
        config = (
            "name 10.0.0.0 corp-net\n"
            "nat (inside) 1 10.0.0.0 255.0.0.0\n"
            "global (outside) 1 interface\n"
        )
        r = self._convert(config)
        # name-derived object — not the auto net_ variant
        assert "object network corp-net" in r.output
        assert "object network net_10_0_0_0_8" not in r.output
        assert "nat (inside,outside) source dynamic corp-net interface destination static any any" in r.output

    def test_unmatched_nat_id_no_global(self):
        """When no global matches a nat_id, a passthrough comment is emitted and a warning logged."""
        config = "nat (inside) 5 10.0.0.0 255.0.0.0\n"
        r = self._convert(config)
        assert "no global for nat id 5" in r.output
        assert any("WARNING" in line and "nat id 5" in line for line in r.log.splitlines())

    def test_nat_with_trailing_connection_params(self):
        """nat lines with optional max-conns/emb-limit trailing params are handled correctly."""
        config = (
            "nat (inside) 1 10.0.0.0 255.0.0.0 0 0\n"
            "global (outside) 1 198.51.100.10\n"
        )
        r = self._convert(config)
        # Must produce dynamic NAT, not a passthrough comment
        assert "nat (inside,outside) source dynamic" in r.output
        assert "no global for nat id" not in r.output
        assert "No nat rule for global" not in r.log

    def test_nat_with_norandomseq(self):
        """nat lines with 'norandomseq' trailing keyword are handled correctly."""
        config = (
            "nat (inside) 1 192.168.0.0 255.255.0.0 norandomseq\n"
            "global (outside) 1 interface\n"
        )
        r = self._convert(config)
        assert "nat (inside,outside) source dynamic" in r.output
        assert "no global for nat id" not in r.output

    def test_multiple_globals_same_nat_id(self):
        """Multiple range globals sharing the same nat_id and dst_if emit one object-group and one nat statement."""
        config = (
            "nat (inside) 1 10.0.0.0 255.0.0.0\n"
            "global (outside) 1 198.51.100.2-198.51.100.100\n"
            "global (outside) 1 203.0.113.2-203.0.113.100\n"
        )
        r = self._convert(config)
        # Both range objects must be declared (ranges still need object network blocks)
        assert "object network range_198_51_100_2_198_51_100_100" in r.output
        assert "object network range_203_0_113_2_203_0_113_100" in r.output
        # The object-group collecting them must be present with object-reference members
        assert "object-group network natpool_1_outside" in r.output
        assert " network-object object range_198_51_100_2_198_51_100_100" in r.output
        assert " network-object object range_203_0_113_2_203_0_113_100" in r.output
        # Exactly ONE nat statement for this (inside,outside) pair
        nat_lines = [ln for ln in r.output.splitlines()
                     if ln.startswith("nat (inside,outside)")]
        assert len(nat_lines) == 1
        assert "natpool_1_outside" in nat_lines[0]
        # The old "N global pools" comment must NOT appear
        assert "global pools for nat id" not in r.output

    def test_multiple_host_globals_inline(self):
        """Multiple bare-host globals use inline network-object host — no intermediate object network."""
        config = (
            "nat (inside) 1 10.0.0.0 255.0.0.0\n"
            "global (outside) 1 198.51.100.10\n"
            "global (outside) 1 198.51.100.11\n"
        )
        r = self._convert(config)
        # object-group present
        assert "object-group network natpool_1_outside" in r.output
        # Members are inline host, not object references
        assert " network-object host 198.51.100.10" in r.output
        assert " network-object host 198.51.100.11" in r.output
        # No intermediate host_ objects
        assert "object network host_198_51_100_10" not in r.output
        assert "object network host_198_51_100_11" not in r.output

    def test_multiple_globals_named_host(self):
        """Named host in multi-pool uses network-object object <name>, not inline."""
        config = (
            "name 198.51.100.10 ext-a\n"
            "nat (inside) 1 10.0.0.0 255.0.0.0\n"
            "global (outside) 1 198.51.100.10\n"
            "global (outside) 1 198.51.100.11\n"
        )
        r = self._convert(config)
        # Named entry uses object reference
        assert " network-object object ext-a" in r.output
        # Unnamed entry uses inline host
        assert " network-object host 198.51.100.11" in r.output

    def test_subnet_global_single(self):
        """Single subnet-form global produces a net_ auto-object and dynamic NAT."""
        config = (
            "nat (inside) 1 10.0.0.0 255.0.0.0\n"
            "global (outside) 1 172.20.4.46 255.255.255.254\n"
        )
        r = self._convert(config)
        assert "object network net_172_20_4_46_31" in r.output
        assert "nat (inside,outside) source dynamic net_10_0_0_0_8 pat-pool net_172_20_4_46_31 destination static any any" in r.output

    def test_subnet_global_multi_inline(self):
        """Multiple subnet-form globals in same pool use inline network-object <ip> <mask>."""
        config = (
            "nat (inside) 1 10.0.0.0 255.0.0.0\n"
            "global (outside) 1 172.20.4.46 255.255.255.254\n"
            "global (outside) 1 172.20.4.48 255.255.255.254\n"
        )
        r = self._convert(config)
        assert "object-group network natpool_1_outside" in r.output
        assert " network-object 172.20.4.46 255.255.255.254" in r.output
        assert " network-object 172.20.4.48 255.255.255.254" in r.output
        # No intermediate net_ object blocks for these
        assert "object network net_172_20_4_46_31" not in r.output

    def test_multi_interface_same_nat_id(self):
        """Globals on different dst interfaces for the same nat_id each produce their own nat statement."""
        config = (
            "nat (inside) 1 10.0.0.0 255.0.0.0\n"
            "global (outside) 1 198.51.100.10\n"
            "global (extranet) 1 interface\n"
        )
        r = self._convert(config)
        # Host object for the outside pool
        assert "object network host_198_51_100_10" in r.output
        # One nat per distinct dst interface
        outside_nat = [ln for ln in r.output.splitlines()
                       if ln.startswith("nat (inside,outside)")]
        extranet_nat = [ln for ln in r.output.splitlines()
                        if ln.startswith("nat (inside,extranet)")]
        assert len(outside_nat) == 1
        assert "host_198_51_100_10" in outside_nat[0]
        assert len(extranet_nat) == 1
        assert "interface" in extranet_nat[0]


class TestAsa84Conversion:
    """Tests for ASA 8.4+ target: pat-pool syntax and correct version header."""

    def _convert84(self, config: str):
        from pix2asa.converter import ConversionOptions
        from pix2asa.models import SourceVersion, TargetVersion
        o = ConversionOptions(
            source_version=SourceVersion.PIX6,
            target_version=TargetVersion.ASA84,
        )
        return convert("PIX Version 6.3\n" + config, o)

    def test_version_header_asa84(self):
        """ASA 8.4 target emits correct version header."""
        r = self._convert84("")
        assert "ASA Version 8.4(2)" in r.output

    def test_single_host_global_pat_pool(self):
        """Single-host global on ASA84 uses pat-pool keyword."""
        config = (
            "nat (inside) 1 10.0.0.0 255.0.0.0\n"
            "global (outside) 1 198.51.100.10\n"
        )
        r = self._convert84(config)
        assert "nat (inside,outside) source dynamic net_10_0_0_0_8 pat-pool host_198_51_100_10" in r.output

    def test_range_global_pat_pool(self):
        """Range global on ASA84 uses pat-pool keyword."""
        config = (
            "nat (inside) 1 192.168.0.0 255.255.255.0\n"
            "global (outside) 1 198.51.100.2-198.51.100.254 netmask 255.255.255.0\n"
        )
        r = self._convert84(config)
        assert "nat (inside,outside) source dynamic net_192_168_0_0_24 pat-pool range_198_51_100_2_198_51_100_254" in r.output

    def test_interface_global_no_pat_pool(self):
        """Interface global on ASA84 does NOT use pat-pool — uses 'interface' keyword directly."""
        config = (
            "nat (inside) 1 10.0.0.0 255.0.0.0\n"
            "global (outside) 1 interface\n"
        )
        r = self._convert84(config)
        assert "nat (inside,outside) source dynamic" in r.output
        assert "pat-pool" not in r.output
        assert "interface destination static any any" in r.output

    def test_multi_range_pool_pat_pool(self):
        """Multiple range globals on ASA84 build an object-group and use pat-pool for it."""
        config = (
            "nat (inside) 1 10.0.0.0 255.0.0.0\n"
            "global (outside) 1 198.51.100.2-198.51.100.10 netmask 255.255.255.0\n"
            "global (outside) 1 203.0.113.2-203.0.113.10 netmask 255.255.255.0\n"
        )
        r = self._convert84(config)
        assert "object-group network natpool_1_outside" in r.output
        assert "nat (inside,outside) source dynamic net_10_0_0_0_8 pat-pool natpool_1_outside" in r.output



class TestConduitConversion:
    """Tests for PIX conduit → ASA ACL-Global extended access-list conversion."""

    def _convert(self, config: str, convert_names: bool = True):
        from pix2asa.converter import ConversionOptions
        from pix2asa.models import SourceVersion, TargetVersion
        o = ConversionOptions(
            source_version=SourceVersion.PIX6,
            target_version=TargetVersion.ASA84,
            convert_names=convert_names,
        )
        return convert("PIX Version 6.3\n" + config, o)

    def test_basic_host_to_any(self):
        """conduit permit tcp host <ip> eq www any → ACL with src=any, dst=host <ip> eq www."""
        config = "conduit permit tcp host 198.51.100.1 eq www any\n"
        r = self._convert(config)
        assert "access-list ACL-Global extended permit tcp any host 198.51.100.1 eq www" in r.output

    def test_source_subnet(self):
        """conduit with a subnet source → ACL with subnet as source."""
        config = "conduit permit tcp host 198.51.100.1 eq ftp 10.0.0.0 255.0.0.0\n"
        r = self._convert(config)
        assert "access-list ACL-Global extended permit tcp 10.0.0.0 255.0.0.0 host 198.51.100.1 eq ftp" in r.output

    def test_named_object_substitution(self):
        """name command creates an object; conduit host <ip> is rewritten to object <name>."""
        config = "name 198.51.100.1 webserver\nconduit permit tcp host 198.51.100.1 eq www any\n"
        r = self._convert(config)
        assert "access-list ACL-Global extended permit tcp any object webserver eq www" in r.output

    def test_permit_ip_any_any(self):
        """conduit permit ip any any → full pass-through ACL entry."""
        config = "conduit permit ip any any\n"
        r = self._convert(config)
        assert "access-list ACL-Global extended permit ip any any" in r.output

    def test_deny(self):
        """conduit deny produces a deny ACE with src and dst swapped."""
        config = "conduit deny tcp host 198.51.100.1 any\n"
        r = self._convert(config)
        assert "access-list ACL-Global extended deny tcp any host 198.51.100.1" in r.output

    def test_access_group_emission(self):
        """static command registers outside interface; access-group lines are emitted."""
        config = (
            "static (inside,outside) 198.51.100.1 192.168.1.1 netmask 255.255.255.255\n"
            "conduit permit tcp host 198.51.100.1 eq www any\n"
        )
        r = self._convert(config)
        assert "access-group ACL-Global in interface outside" in r.output
        assert "access-group ACL-Global global" in r.output

    # -----------------------------------------------------------------------
    # NAT address translation (mapped → real)
    # -----------------------------------------------------------------------

    def test_static_nat_translates_host_in_conduit(self):
        """Host static NAT: conduit dst IP (external) is translated to real (internal) IP."""
        config = (
            "static (inside,outside) 203.0.113.10 192.168.1.10 netmask 255.255.255.255\n"
            "conduit permit tcp host 203.0.113.10 eq 80 any\n"
        )
        r = self._convert(config)
        # ACL must reference the auto-generated object for the REAL (internal) IP.
        # After translation (mapped→real) and object substitution (IP→object name),
        # the ACL line uses "object host_192_168_1_10", not the literal IP.
        assert "object host_192_168_1_10 eq 80" in r.output
        # Mapped IP must not appear in any ACL line (it may appear in object definitions)
        acl_text = " ".join(l for l in r.output.splitlines() if l.startswith("access-list"))
        assert "203.0.113.10" not in acl_text

    def test_static_nat_translate_conduit_before_static(self):
        """Translation works even when conduit appears before static in the config."""
        config = (
            "conduit permit tcp host 203.0.113.10 eq 443 any\n"
            "static (inside,outside) 203.0.113.10 192.168.1.10 netmask 255.255.255.255\n"
        )
        r = self._convert(config)
        assert "object host_192_168_1_10 eq 443" in r.output
        acl_text = " ".join(l for l in r.output.splitlines() if l.startswith("access-list"))
        assert "203.0.113.10" not in acl_text

    def test_static_nat_translate_multiple_statics(self):
        """Multiple statics each map their respective conduit entries independently."""
        config = (
            "static (inside,outside) 203.0.113.10 192.168.1.10 netmask 255.255.255.255\n"
            "static (inside,outside) 203.0.113.20 192.168.1.20 netmask 255.255.255.255\n"
            "conduit permit tcp host 203.0.113.10 eq 80 any\n"
            "conduit permit tcp host 203.0.113.20 eq 25 any\n"
        )
        r = self._convert(config)
        assert "object host_192_168_1_10 eq 80" in r.output
        assert "object host_192_168_1_20 eq 25" in r.output
        acl_text = " ".join(l for l in r.output.splitlines() if l.startswith("access-list"))
        assert "203.0.113.10" not in acl_text
        assert "203.0.113.20" not in acl_text

    def test_conduit_any_any_unaffected_by_static(self):
        """conduit permit ip any any is not altered by static NAT entries."""
        config = (
            "static (inside,outside) 203.0.113.10 192.168.1.10 netmask 255.255.255.255\n"
            "conduit permit ip any any\n"
        )
        r = self._convert(config)
        assert "access-list ACL-Global extended permit ip any any" in r.output

    def test_conduit_no_static_warns_and_passes_through(self):
        """Conduit dst IP with no matching static NAT emits a WARNING and is left unchanged."""
        config = "conduit permit tcp host 203.0.113.99 eq 80 any\n"
        r = self._convert(config)
        # Address passes through unchanged
        assert "host 203.0.113.99 eq 80" in r.output
        # A WARNING is logged
        assert any("WARNING" in w and "203.0.113.99" in w for w in r.warnings)

    def test_port_redirect_static_translates_conduit(self):
        """Port-redirect static: conduit dst IP mapped to the real (internal) server IP."""
        config = (
            "static (inside,outside) tcp 203.0.113.10 443 192.168.1.10 443\n"
            "conduit permit tcp host 203.0.113.10 eq 443 any\n"
        )
        r = self._convert(config)
        # After translation+substitution the ACL references the real IP's object name.
        assert "object host_192_168_1_10 eq 443" in r.output
        # Mapped IP must not appear in any ACL line (it does appear in the NAT statement)
        acl_text = " ".join(l for l in r.output.splitlines() if l.startswith("access-list"))
        assert "203.0.113.10" not in acl_text

    def test_named_object_used_after_nat_translation(self):
        """After NAT translation, the real IP is substituted with its named object."""
        config = (
            "name 192.168.1.10 webserver\n"
            "static (inside,outside) 203.0.113.10 192.168.1.10 netmask 255.255.255.255\n"
            "conduit permit tcp host 203.0.113.10 eq 80 any\n"
        )
        r = self._convert(config)
        # Real IP 192.168.1.10 has name 'webserver' — ACL must use the named object
        assert "object webserver eq 80" in r.output
        # Neither IP should appear in ACL lines (mapped IP may appear in object definitions)
        acl_text = " ".join(l for l in r.output.splitlines() if l.startswith("access-list"))
        assert "203.0.113.10" not in acl_text
        assert "192.168.1.10" not in acl_text

    # -----------------------------------------------------------------------
    # Named object remapping: 'name' assigned to the mapped (external) IP
    # -----------------------------------------------------------------------

    def test_name_on_mapped_ip_remapped_to_real(self):
        """name command on the mapped IP: object is updated to the real (internal) IP."""
        config = (
            "name 203.0.113.10 webserver\n"
            "static (inside,outside) 203.0.113.10 192.168.1.10 netmask 255.255.255.255\n"
        )
        r = self._convert(config)
        # The named object must reference the real (internal) IP
        assert "object network webserver" in r.output
        assert " host 192.168.1.10" in r.output
        # The mapped IP gets its own auto-object; the old body must be gone
        assert "object network host_203_0_113_10" in r.output
        assert " host 203.0.113.10" in r.output
        # NAT uses name on the real side, auto-object on the mapped side
        assert "nat (inside,outside) source static webserver host_203_0_113_10" in r.output

    def test_name_on_mapped_ip_conduit_uses_named_object(self):
        """Conduit ACL for a remapped name uses the named object after translation."""
        config = (
            "name 203.0.113.10 webserver\n"
            "static (inside,outside) 203.0.113.10 192.168.1.10 netmask 255.255.255.255\n"
            "conduit permit tcp host 203.0.113.10 eq 80 any\n"
        )
        r = self._convert(config)
        assert "access-list ACL-Global extended permit tcp any object webserver eq 80" in r.output

    def test_name_on_real_ip_not_remapped(self):
        """name on the real (internal) IP is left unchanged — only mapped-IP names are remapped."""
        config = (
            "name 192.168.1.10 webserver\n"
            "static (inside,outside) 203.0.113.10 192.168.1.10 netmask 255.255.255.255\n"
        )
        r = self._convert(config)
        # Name was already on the real IP — object stays pointing to the real IP
        assert "object network webserver" in r.output
        assert " host 192.168.1.10" in r.output
        assert "nat (inside,outside) source static webserver" in r.output

    def test_both_ips_named_no_remap(self):
        """When both mapped and real IPs have names, neither is remapped."""
        config = (
            "name 203.0.113.10 webserver-ext\n"
            "name 192.168.1.10 webserver-int\n"
            "static (inside,outside) 203.0.113.10 192.168.1.10 netmask 255.255.255.255\n"
        )
        r = self._convert(config)
        # Each name keeps its own IP
        assert " host 203.0.113.10" in r.output
        assert " host 192.168.1.10" in r.output
        assert "nat (inside,outside) source static webserver-int webserver-ext" in r.output

    # -----------------------------------------------------------------------
    # Bug regression: reserved-word name remap (Bug 1)
    # -----------------------------------------------------------------------

    def test_reserved_word_name_remapped_correctly(self):
        """A name that is an ASA reserved word (renamed <name>_object) is correctly remapped.

        Bug: _remap_name_to_real_ip was writing converted_names[safe_name] but
        _handle_name stores converted_names[original_name].  When they differ (reserved
        word case) the original-name key was left pointing to the old mapped IP.
        """
        config = (
            "name 203.0.113.10 source\n"   # 'source' is a reserved word → renamed source_object
            "static (inside,outside) 203.0.113.10 192.168.1.10 netmask 255.255.255.255\n"
        )
        r = self._convert(config)
        # Object must exist with the safe name and must use the REAL IP
        assert "object network source_object" in r.output
        assert " host 192.168.1.10" in r.output
        # Mapped IP gets its own auto-object
        assert "object network host_203_0_113_10" in r.output
        assert " host 203.0.113.10" in r.output
        # NAT uses safe name on the real side
        assert "nat (inside,outside) source static source_object host_203_0_113_10" in r.output

    # -----------------------------------------------------------------------
    # Bug regression: static-before-name ordering (Bug 2)
    # -----------------------------------------------------------------------

    def test_name_after_static_remapped_in_post_processing(self):
        """When static precedes name, the post-processing pass remaps the named object.

        Bug: _remap_name_to_real_ip only fires during the engine pass when converted_names_r
        already has the mapped IP.  If static appears before name, the remap was silently
        skipped, leaving the named object pointing to the external (mapped) IP.
        """
        config = (
            "static (inside,outside) 203.0.113.10 192.168.1.10 netmask 255.255.255.255\n"
            "name 203.0.113.10 webserver\n"   # name AFTER static
        )
        r = self._convert(config)
        # Named object must be patched to the real (internal) IP
        assert "object network webserver" in r.output
        assert " host 192.168.1.10" in r.output
        # A WARNING must be logged to flag the ordering
        assert any("WARNING" in w and "webserver" in w for w in r.warnings)

    def test_name_after_static_conduit_uses_named_object(self):
        """Conduit ACL uses the named object even when static precedes name."""
        config = (
            "static (inside,outside) 203.0.113.10 192.168.1.10 netmask 255.255.255.255\n"
            "name 203.0.113.10 webserver\n"
            "conduit permit tcp host 203.0.113.10 eq 80 any\n"
        )
        r = self._convert(config)
        assert "object webserver eq 80" in r.output

    # -----------------------------------------------------------------------
    # Description line survives remap patch (Gap 1)
    # -----------------------------------------------------------------------

    def test_name_description_survives_remap(self):
        """A description on the name object is preserved after the IP is remapped."""
        config = (
            "name 203.0.113.10 webserver description The web server\n"
            "static (inside,outside) 203.0.113.10 192.168.1.10 netmask 255.255.255.255\n"
        )
        r = self._convert(config)
        assert " host 192.168.1.10" in r.output
        assert " description The web server" in r.output
