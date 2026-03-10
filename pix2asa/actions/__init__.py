"""PIX-to-ASA conversion actions package.

Public API — identical to the former single-file actions.py.
All callers (converter.py, tests) continue to work without modification.
"""

from .conduit import emit_conduit_access_groups
from .interfaces import setup_custom_if
from .names import apply_name_substitutions, apply_nat_remap_to_names
from .nat_emit import emit_default_mtus, emit_nat_rules
from .rules import RULES_COMMON, RULES_V6, RULES_V7, build_dispatcher

__all__ = [
    "setup_custom_if",
    "build_dispatcher",
    "RULES_COMMON",
    "RULES_V6",
    "RULES_V7",
    "emit_nat_rules",
    "emit_default_mtus",
    "emit_conduit_access_groups",
    "apply_name_substitutions",
    "apply_nat_remap_to_names",
]
