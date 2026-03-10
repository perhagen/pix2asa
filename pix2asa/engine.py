"""Keyword-first pattern-matching dispatch engine.

Replaces the original linear MatchAction list + SetupActions() with:

  - Rule: frozen dataclass (keyword, pre-compiled pattern, handler)
  - Dispatcher: O(1) bucket lookup by first CLI token, then regex match

Rust equivalent:
    struct Rule { keyword: &'static str, pattern: Regex,
                  handler: fn(&Captures, &mut Context) -> bool }
    struct Dispatcher { keyed: HashMap<String, Vec<Rule>>, fallback: Vec<Rule> }
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from itertools import chain
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from .context import ConversionContext

Handler = Callable[[re.Match, "ConversionContext"], bool]


@dataclass(frozen=True)
class Rule:
    """One pattern-matching rule.

    keyword   — first CLI token used to select the rule's bucket.
                Empty string places the rule in the fallback list.
    pattern   — pre-compiled regex with IGNORECASE; use named groups throughout.
    handler   — callable(match, ctx) -> bool (True = stop processing this line).
    negated   — True for "no <cmd>" counterpart rules; passed into the handler
                so a single function can handle both the positive and negated form.
    """

    keyword: str
    pattern: re.Pattern
    handler: Handler
    negated: bool = False


class Dispatcher:
    """Routes each input line to the first matching Rule.

    Build once per conversion (or share across conversions — it is stateless).

    Algorithm per line:
        1. Extract first whitespace-delimited token and lower-case it.
        2. Fetch the bucket for that keyword (O(1) dict lookup).
        3. Try each rule in the bucket in order; stop on the first match.
        4. If no bucket match, try the fallback list.
        5. Return True if any rule matched, False otherwise.
    """

    def __init__(self, rules: list[Rule]) -> None:
        """Partition rules into per-keyword buckets and a fallback list."""
        self._keyed: dict[str, list[Rule]] = defaultdict(list)
        self._fallback: list[Rule] = []
        for rule in rules:
            if rule.keyword:
                self._keyed[rule.keyword].append(rule)
            else:
                self._fallback.append(rule)

    def dispatch(self, line: str, ctx: "ConversionContext") -> bool:
        """Dispatch one config line to the first matching rule; return True if a rule matched."""
        parts = line.split(None, 1)
        keyword = parts[0].lower() if parts else ""
        candidates = self._keyed.get(keyword, [])
        for rule in chain(candidates, self._fallback):
            m = rule.pattern.match(line)
            if m and rule.handler(m, ctx):
                return True
        return False


# ---------------------------------------------------------------------------
# Convenience: compile helper (enforces IGNORECASE everywhere)
# ---------------------------------------------------------------------------

def _r(pattern: str) -> re.Pattern:
    """Compile *pattern* with IGNORECASE and return the compiled regex."""
    return re.compile(pattern, re.IGNORECASE)
