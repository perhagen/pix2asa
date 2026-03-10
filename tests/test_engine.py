"""Tests for pix2asa.engine — Rule, Dispatcher, dispatch logic."""

from __future__ import annotations

import re
import pytest

from pix2asa.engine import Dispatcher, Rule, _r
from pix2asa.context import ConversionContext
from pix2asa.models import SourceVersion, TargetVersion


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ctx() -> ConversionContext:
    return ConversionContext(
        source_version=SourceVersion.PIX6,
        target_version=TargetVersion.ASA84,
        target_platform="asa-5520",
    )


def _rule(keyword: str, pattern: str, side_effect: list | None = None) -> Rule:
    """Build a Rule whose handler appends the line to side_effect."""
    captured: list = side_effect if side_effect is not None else []

    def handler(m: re.Match, ctx: ConversionContext) -> bool:
        captured.append(m.string)
        return True

    return Rule(keyword=keyword, pattern=_r(pattern), handler=handler)


# ---------------------------------------------------------------------------
# _r() helper
# ---------------------------------------------------------------------------

class TestRHelper:
    def test_compiles(self):
        p = _r(r"nameif\s+(\S+)")
        assert isinstance(p, re.Pattern)

    def test_ignorecase(self):
        p = _r(r"nameif")
        assert p.match("NAMEIF ethernet0")
        assert p.match("nameif ethernet0")

    def test_named_groups(self):
        p = _r(r"nameif\s+(?P<phys>\S+)\s+(?P<logical>\S+)")
        m = p.match("nameif ethernet0 outside security0")
        assert m["phys"] == "ethernet0"
        assert m["logical"] == "outside"


# ---------------------------------------------------------------------------
# Rule dataclass
# ---------------------------------------------------------------------------

class TestRule:
    def test_frozen(self):
        rule = _rule("nameif", r"nameif\s+\S+")
        with pytest.raises((AttributeError, TypeError)):
            rule.keyword = "other"  # type: ignore[misc]

    def test_default_negated_false(self):
        rule = _rule("nameif", r"nameif")
        assert rule.negated is False


# ---------------------------------------------------------------------------
# Dispatcher construction
# ---------------------------------------------------------------------------

class TestDispatcherConstruction:
    def test_keyed_rules_bucketed(self):
        r1 = _rule("nameif", r"nameif\s+\S+")
        r2 = _rule("nameif", r"nameif\s+\S+\s+\S+")
        r3 = _rule("interface", r"interface\s+\S+")
        d = Dispatcher([r1, r2, r3])
        # nameif bucket has 2 rules; interface has 1
        assert len(d._keyed["nameif"]) == 2
        assert len(d._keyed["interface"]) == 1

    def test_empty_keyword_goes_to_fallback(self):
        r = _rule("", r".*something.*")
        d = Dispatcher([r])
        assert len(d._fallback) == 1
        assert len(d._keyed) == 0

    def test_empty_rule_list(self):
        d = Dispatcher([])
        assert d.dispatch("anything", _ctx()) is False


# ---------------------------------------------------------------------------
# Dispatcher.dispatch
# ---------------------------------------------------------------------------

class TestDispatcherDispatch:
    def test_keyed_match(self):
        hits: list = []
        rule = _rule("nameif", r"nameif\s+(?P<phys>\S+)", hits)
        d = Dispatcher([rule])
        ctx = _ctx()
        result = d.dispatch("nameif ethernet0 outside security0", ctx)
        assert result is True
        assert len(hits) == 1

    def test_keyed_no_match_returns_false(self):
        rule = _rule("nameif", r"nameif\s+IMPOSSIBLE_TOKEN")
        d = Dispatcher([rule])
        assert d.dispatch("nameif ethernet0 outside security0", _ctx()) is False

    def test_wrong_keyword_returns_false(self):
        rule = _rule("nameif", r"nameif\s+\S+")
        d = Dispatcher([rule])
        assert d.dispatch("interface ethernet0", _ctx()) is False

    def test_fallback_used_when_no_keyword_match(self):
        hits: list = []
        rule = _rule("", r".*ethernet0.*", hits)
        d = Dispatcher([rule])
        d.dispatch("nameif ethernet0 outside security0", _ctx())
        assert len(hits) == 1

    def test_keyed_takes_priority_over_fallback(self):
        keyed_hits: list = []
        fallback_hits: list = []
        keyed = _rule("nameif", r"nameif\s+\S+", keyed_hits)
        fallback = _rule("", r".*nameif.*", fallback_hits)
        d = Dispatcher([keyed, fallback])
        d.dispatch("nameif ethernet0 outside security0", _ctx())
        assert len(keyed_hits) == 1
        assert len(fallback_hits) == 0

    def test_first_matching_rule_wins(self):
        """First rule in a bucket that matches should stop further attempts."""
        hits1: list = []
        hits2: list = []
        r1 = _rule("nameif", r"nameif\s+\S+", hits1)   # broad — matches
        r2 = _rule("nameif", r"nameif\s+\S+\s+\S+", hits2)  # also matches
        d = Dispatcher([r1, r2])
        d.dispatch("nameif ethernet0 outside security0", _ctx())
        assert len(hits1) == 1
        assert len(hits2) == 0  # never reached

    def test_case_insensitive_keyword(self):
        hits: list = []
        rule = _rule("nameif", r"nameif\s+\S+", hits)
        d = Dispatcher([rule])
        d.dispatch("NAMEIF ethernet0 outside security0", _ctx())
        assert len(hits) == 1

    def test_empty_line_returns_false(self):
        rule = _rule("nameif", r"nameif\s+\S+")
        d = Dispatcher([rule])
        assert d.dispatch("", _ctx()) is False

    def test_whitespace_only_returns_false(self):
        rule = _rule("nameif", r"nameif\s+\S+")
        d = Dispatcher([rule])
        assert d.dispatch("   ", _ctx()) is False

    def test_handler_returning_false_continues_to_next_rule(self):
        """If a handler returns False the dispatcher tries the next rule in the bucket."""
        hits: list = []

        def picky(m: re.Match, ctx: ConversionContext) -> bool:
            return False  # decline even though pattern matched

        def greedy(m: re.Match, ctx: ConversionContext) -> bool:
            hits.append(True)
            return True

        r1 = Rule(keyword="nameif", pattern=_r(r"nameif\s+\S+"), handler=picky)
        r2 = Rule(keyword="nameif", pattern=_r(r"nameif\s+\S+"), handler=greedy)
        d = Dispatcher([r1, r2])
        result = d.dispatch("nameif ethernet0 outside security0", _ctx())
        assert result is True
        assert hits == [True]
