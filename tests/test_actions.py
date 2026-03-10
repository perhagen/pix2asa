"""Tests for pix2asa.actions — individual handlers and rule tables."""

from __future__ import annotations

import pytest

from pix2asa.actions import (
    RULES_COMMON,
    RULES_V6,
    RULES_V7,
    build_dispatcher,
    setup_custom_if,
)
from pix2asa.context import ConversionContext
from pix2asa.engine import Rule
from pix2asa.models import InterfaceConfig, SourceVersion, TargetVersion


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ctx6(platform="asa-5520") -> ConversionContext:
    return ConversionContext(
        source_version=SourceVersion.PIX6,
        target_version=TargetVersion.ASA84,
        target_platform=platform,
    )


def _ctx7(platform="asa-5520") -> ConversionContext:
    return ConversionContext(
        source_version=SourceVersion.PIX7,
        target_version=TargetVersion.ASA84,
        target_platform=platform,
    )


def dispatch(line: str, ctx: ConversionContext) -> bool:
    from pix2asa.actions import build_dispatcher
    return build_dispatcher(ctx).dispatch(line, ctx)


# ---------------------------------------------------------------------------
# Rule table integrity
# ---------------------------------------------------------------------------

class TestRuleTables:
    def test_rules_are_rule_instances(self):
        for table in (RULES_COMMON, RULES_V6, RULES_V7):
            for r in table:
                assert isinstance(r, Rule), f"Not a Rule: {r!r}"

    def test_all_patterns_compiled(self):
        import re
        for table in (RULES_COMMON, RULES_V6, RULES_V7):
            for r in table:
                assert isinstance(r.pattern, re.Pattern)

    def test_all_handlers_callable(self):
        for table in (RULES_COMMON, RULES_V6, RULES_V7):
            for r in table:
                assert callable(r.handler)

    def test_no_duplicate_keyword_pattern_pairs(self):
        """No two rules in the same table share identical (keyword, pattern.pattern)."""
        for table_name, table in [("COMMON", RULES_COMMON), ("V6", RULES_V6), ("V7", RULES_V7)]:
            seen = set()
            for r in table:
                key = (r.keyword, r.pattern.pattern)
                assert key not in seen, f"Duplicate rule in {table_name}: {key}"
                seen.add(key)

    def test_v6_contains_nameif(self):
        assert any(r.keyword == "nameif" for r in RULES_V6)

    def test_v6_contains_fixup(self):
        assert any(r.keyword == "fixup" for r in RULES_V6)

    def test_v7_contains_interface(self):
        assert any(r.keyword == "interface" for r in RULES_V7)

    def test_no_fixup_rule_exists(self):
        """There must be at least one 'no' keyword rule handling negated fixup."""
        no_rules = [r for r in RULES_V6 if r.keyword == "no"]
        assert len(no_rules) > 0, "Expected at least one 'no' keyword rule"
        # The _neg() wrapper is applied for compound handlers; check keyword directly
        assert any("neg" in r.handler.__name__ or r.negated for r in no_rules)


# ---------------------------------------------------------------------------
# setup_custom_if
# ---------------------------------------------------------------------------

class TestSetupCustomIf:
    def test_valid_mapping(self):
        ctx = _ctx6()
        ok = setup_custom_if("ethernet0", "GigabitEthernet0/0", ctx)
        assert ok is True
        assert ctx.platform_if_mapping["ethernet0"] == "GigabitEthernet0/0"
        assert ctx.platform_if_mapping_r["GigabitEthernet0/0"] == "ethernet0"

    def test_creates_mapping(self):
        ctx = _ctx6()
        setup_custom_if("ethernet0", "GigabitEthernet0/0", ctx)
        assert ctx.platform_if_mapping["ethernet0"] == "GigabitEthernet0/0"
        # Explicit user mapping is intentional — should NOT flag platform_if_exceeded
        assert ctx.platform_if_exceeded is False

    def test_duplicate_source_returns_false(self):
        ctx = _ctx6()
        setup_custom_if("ethernet0", "GigabitEthernet0/0", ctx)
        ok = setup_custom_if("ethernet0", "GigabitEthernet0/1", ctx)
        assert ok is False

    def test_duplicate_dest_returns_false(self):
        ctx = _ctx6()
        setup_custom_if("ethernet0", "GigabitEthernet0/0", ctx)
        ok = setup_custom_if("ethernet1", "GigabitEthernet0/0", ctx)
        assert ok is False


# ---------------------------------------------------------------------------
# nameif handler (PIX 6)
# ---------------------------------------------------------------------------

class TestHandleNameif:
    def test_basic_nameif(self):
        ctx = _ctx6()
        dispatch("nameif ethernet0 outside security0", ctx)
        assert ctx.name_ifs.get("outside") == "ethernet0"
        assert ctx.name_ifs_r.get("ethernet0") == "outside"

    def test_nameif_inside(self):
        ctx = _ctx6()
        dispatch("nameif ethernet1 inside security100", ctx)
        assert ctx.name_ifs.get("inside") == "ethernet1"

    def test_nameif_creates_interface(self):
        ctx = _ctx6()
        dispatch("nameif ethernet0 outside security0", ctx)
        assert "ethernet0" in ctx.interfaces

    def test_nameif_sets_security_level(self):
        ctx = _ctx6()
        dispatch("nameif ethernet0 outside security0", ctx)
        assert ctx.interfaces["ethernet0"].security_level == 0

    def test_nameif_inside_security100(self):
        ctx = _ctx6()
        dispatch("nameif ethernet1 inside security100", ctx)
        assert ctx.interfaces["ethernet1"].security_level == 100

    def test_nameif_dmz_security50(self):
        ctx = _ctx6()
        dispatch("nameif ethernet2 dmz security50", ctx)
        assert ctx.interfaces["ethernet2"].security_level == 50


# ---------------------------------------------------------------------------
# ip address handler
# ---------------------------------------------------------------------------

class TestHandleIpAddress:
    def _setup(self, ctx):
        dispatch("nameif ethernet0 outside security0", ctx)

    def test_static_ip(self):
        ctx = _ctx6()
        self._setup(ctx)
        dispatch("ip address outside 192.168.1.1 255.255.255.0", ctx)
        iface = ctx.interfaces["ethernet0"]
        assert iface.ip_address == "192.168.1.1"
        assert iface.netmask == "255.255.255.0"

    def test_dhcp(self):
        ctx = _ctx6()
        self._setup(ctx)
        dispatch("ip address outside dhcp setroute", ctx)
        assert ctx.interfaces["ethernet0"].dhcp is True
        assert ctx.interfaces["ethernet0"].set_route is True

    def test_dhcp_no_setroute(self):
        ctx = _ctx6()
        self._setup(ctx)
        dispatch("ip address outside dhcp", ctx)
        iface = ctx.interfaces["ethernet0"]
        assert iface.dhcp is True
        assert iface.set_route is False

    def test_pppoe(self):
        ctx = _ctx6()
        self._setup(ctx)
        dispatch("ip address outside pppoe setroute", ctx)
        assert ctx.interfaces["ethernet0"].pppoe is True


# ---------------------------------------------------------------------------
# fixup / no fixup handler
# ---------------------------------------------------------------------------

class TestHandleFixup:
    def test_fixup_adds_inspect(self):
        ctx = _ctx6()
        dispatch("fixup protocol ftp 21", ctx)
        names = [i.name for i in ctx.inspects]
        assert "ftp" in names

    def test_fixup_negated(self):
        ctx = _ctx6()
        dispatch("no fixup protocol ftp 21", ctx)
        neg = [i for i in ctx.inspects if i.name == "ftp"]
        assert len(neg) == 1
        assert neg[0].negated is True

    def test_fixup_dns_with_length(self):
        ctx = _ctx6()
        dispatch("fixup protocol dns maximum-length 512", ctx)
        dns = [i for i in ctx.inspects if i.name == "dns"]
        assert len(dns) == 1
        assert dns[0].port == "512"

    def test_fixup_http(self):
        ctx = _ctx6()
        dispatch("fixup protocol http 80", ctx)
        assert any(i.name == "http" for i in ctx.inspects)

    def test_fixup_h323(self):
        ctx = _ctx6()
        dispatch("fixup protocol h323 h225 1720", ctx)
        assert any("h323" in i.name for i in ctx.inspects)

    def test_fixup_smtp(self):
        ctx = _ctx6()
        dispatch("fixup protocol smtp 25", ctx)
        assert any(i.name == "smtp" or i.name == "esmtp" for i in ctx.inspects)

    def test_fixup_sip(self):
        ctx = _ctx6()
        dispatch("fixup protocol sip 5060", ctx)
        assert any(i.name == "sip" for i in ctx.inspects)

    def test_no_fixup_not_duplicated(self):
        ctx = _ctx6()
        dispatch("no fixup protocol smtp 25", ctx)
        smtp = [i for i in ctx.inspects if i.name in ("smtp", "esmtp")]
        # Should have exactly one entry, negated
        assert len(smtp) == 1
        assert smtp[0].negated


# ---------------------------------------------------------------------------
# MTU handler
# ---------------------------------------------------------------------------

class TestHandleMtu:
    def test_mtu_set(self):
        ctx = _ctx6()
        dispatch("nameif ethernet0 outside security0", ctx)
        dispatch("mtu outside 1500", ctx)
        assert ctx.interfaces["ethernet0"].mtu == 1500


# ---------------------------------------------------------------------------
# Failover handlers
# ---------------------------------------------------------------------------

class TestFailoverHandlers:
    def test_failover_poll_normalised(self):
        ctx = _ctx6()
        dispatch("nameif ethernet0 outside security0", ctx)
        dispatch("nameif ethernet1 inside security100", ctx)
        dispatch("nameif ethernet2 failover security90", ctx)
        dispatch("failover poll 15", ctx)
        lines = [cl.render() for cl in ctx.config_lines]
        assert any("failover polltime 15" in l for l in lines)

    def test_failover_standby_ip(self):
        ctx = _ctx6()
        dispatch("nameif ethernet0 outside security0", ctx)
        dispatch("ip address outside 10.0.0.1 255.255.255.0", ctx)
        dispatch("failover ip address outside 10.0.0.2", ctx)
        assert ctx.interfaces["ethernet0"].standby_ip == "10.0.0.2"


# ---------------------------------------------------------------------------
# Hostname handler
# ---------------------------------------------------------------------------

class TestHandleHostname:
    def test_hostname_renamed(self):
        ctx = _ctx6()
        dispatch("hostname myfirewall", ctx)
        lines = [cl.render() for cl in ctx.config_lines]
        assert any("myfirewall-migrated" in l for l in lines)

    def test_hostname_logged(self):
        ctx = _ctx6()
        dispatch("hostname fw01", ctx)
        assert "fw01" in ctx.get_log()


# ---------------------------------------------------------------------------
# PIX version line (should be ignored)
# ---------------------------------------------------------------------------

class TestIgnoredLines:
    def test_pix_version_removed(self):
        ctx = _ctx6()
        matched = dispatch("PIX Version 6.3(1)", ctx)
        assert matched is True  # handled (ignored), not added to config_lines
        lines = [cl.render() for cl in ctx.config_lines]
        assert not any("PIX Version" in l for l in lines)

    def test_end_line_removed(self):
        ctx = _ctx6()
        matched = dispatch(": end", ctx)
        assert matched is True
        lines = [cl.render() for cl in ctx.config_lines]
        assert not any(": end" in l for l in lines)


# ---------------------------------------------------------------------------
# ASDM → ASDM rename
# ---------------------------------------------------------------------------

class TestAsdmHistory:
    def test_pdm_renamed_to_asdm(self):
        ctx = _ctx6()
        dispatch("pdm history enable", ctx)
        lines = [cl.render() for cl in ctx.config_lines]
        assert any("asdm history enable" in l for l in lines)
        assert not any("pdm history enable" in l for l in lines)


# ---------------------------------------------------------------------------
# VPDN groups
# ---------------------------------------------------------------------------

class TestVpdnGroup:
    def test_vpdn_group_registered(self):
        ctx = _ctx6()
        dispatch("vpdn group mypppoe request dialout pppoe", ctx)
        assert "mypppoe" in ctx.vpdn_groups


# ---------------------------------------------------------------------------
# build_dispatcher — version selection
# ---------------------------------------------------------------------------

class TestBuildDispatcher:
    def test_v6_dispatcher_handles_nameif(self):
        ctx = _ctx6()
        d = build_dispatcher(ctx)
        result = d.dispatch("nameif ethernet0 outside security0", ctx)
        assert result is True

    def test_v7_dispatcher_handles_interface(self):
        ctx = _ctx7()
        d = build_dispatcher(ctx)
        result = d.dispatch("interface GigabitEthernet0/0", ctx)
        assert result is True

    def test_v6_dispatcher_rejects_v7_interface_block(self):
        """PIX 6 dispatcher should not handle 'interface' as a v7 block opener."""
        ctx = _ctx6()
        d = build_dispatcher(ctx)
        # v6 does have 'interface <phys> <speed>' as a repeated line
        # but not the v7 sub-command block style — just verify no crash
        result = d.dispatch("interface ethernet0 auto", ctx)
        # result may be True (repeat) or False; just should not raise
        assert isinstance(result, bool)
