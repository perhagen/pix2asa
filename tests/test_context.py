"""Tests for pix2asa.context — ConversionContext state management."""

from __future__ import annotations

import pytest
from pix2asa.context import ConversionContext
from pix2asa.models import InterfaceConfig, SourceVersion, TargetVersion


def _ctx() -> ConversionContext:
    return ConversionContext(
        source_version=SourceVersion.PIX6,
        target_version=TargetVersion.ASA84,
        target_platform="asa-5520",
    )


class TestConversionContextInit:
    def test_all_collections_empty(self):
        ctx = _ctx()
        assert ctx.config_lines == []
        assert ctx.interfaces == {}
        assert ctx.name_ifs == {}
        assert ctx.name_ifs_r == {}
        assert ctx.inspects == []
        assert ctx.vpdn_groups == []

    def test_log_buffer_empty(self):
        ctx = _ctx()
        assert ctx.get_log() == ""

    def test_platform_if_mapping_empty(self):
        ctx = _ctx()
        assert ctx.platform_if_mapping == {}
        assert ctx.platform_if_mapping_r == {}


class TestLog:
    def test_log_appends(self):
        ctx = _ctx()
        ctx.log("INFO: first")
        ctx.log("WARNING: second")
        log = ctx.get_log()
        assert "INFO: first" in log
        assert "WARNING: second" in log

    def test_log_preserves_order(self):
        ctx = _ctx()
        for i in range(5):
            ctx.log(f"line {i}")
        lines = [l for l in ctx.get_log().splitlines() if l]
        assert lines == [f"line {i}" for i in range(5)]

    def test_empty_log_produces_empty_or_newline(self):
        # ctx.log("") delegates to print("") which adds a newline — acceptable
        ctx = _ctx()
        ctx.log("")
        assert ctx.get_log().strip() == ""


class TestMapInterface:
    def test_bidirectional(self):
        ctx = _ctx()
        ctx.map_interface("ethernet0", "GigabitEthernet0/0")
        assert ctx.platform_if_mapping["ethernet0"] == "GigabitEthernet0/0"
        assert ctx.platform_if_mapping_r["GigabitEthernet0/0"] == "ethernet0"

    def test_overwrite(self):
        ctx = _ctx()
        ctx.map_interface("ethernet0", "GigabitEthernet0/0")
        ctx.map_interface("ethernet0", "GigabitEthernet0/1")
        assert ctx.platform_if_mapping["ethernet0"] == "GigabitEthernet0/1"
        assert "GigabitEthernet0/0" not in ctx.platform_if_mapping_r

    def test_multiple_mappings(self):
        ctx = _ctx()
        ctx.map_interface("ethernet0", "GigabitEthernet0/0")
        ctx.map_interface("ethernet1", "GigabitEthernet0/1")
        assert len(ctx.platform_if_mapping) == 2
        assert len(ctx.platform_if_mapping_r) == 2


class TestGetRealPhys:
    def test_direct_lookup(self):
        ctx = _ctx()
        ctx.name_ifs["outside"] = "ethernet0"
        assert ctx.get_real_phys("outside") == "ethernet0"

    def test_unknown_name_returns_self(self):
        # If name is not in name_ifs it is assumed to already be physical
        ctx = _ctx()
        assert ctx.get_real_phys("ethernet0") == "ethernet0"

    def test_logical_to_phys_fallback(self):
        ctx = _ctx()
        ctx.name_ifs["dmz"] = "ethernet0.1"
        ctx.logical_to_phys["ethernet0.1"] = "ethernet0"
        assert ctx.get_real_phys("dmz") == "ethernet0"

    def test_chain_nameif_then_logical(self):
        ctx = _ctx()
        ctx.name_ifs["dmz"] = "ethernet0.1"
        ctx.logical_to_phys["ethernet0.1"] = "ethernet0"
        assert ctx.get_real_phys("dmz") == "ethernet0"


class TestReset:
    def test_reset_clears_everything(self):
        ctx = _ctx()
        ctx.log("INFO: some log")
        ctx.map_interface("ethernet0", "GigabitEthernet0/0")
        ctx.name_ifs["outside"] = "ethernet0"
        iface = InterfaceConfig("ethernet0", mapped_name="GigabitEthernet0/0")
        ctx.interfaces["ethernet0"] = iface
        ctx.vpdn_groups.append("mygroup")

        ctx.reset()

        assert ctx.get_log() == ""
        assert ctx.interfaces == {}
        assert ctx.name_ifs == {}
        assert ctx.platform_if_mapping == {}
        assert ctx.vpdn_groups == []

    def test_reset_preserves_options(self):
        # reset() clears everything including target_platform (by design).
        # After reset the context is blank — caller must re-set options.
        ctx = _ctx()
        ctx.reset()
        assert ctx.source_version == SourceVersion.PIX6  # enum value preserved
