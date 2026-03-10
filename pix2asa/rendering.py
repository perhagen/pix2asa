"""Jinja2 rendering environment for pix2asa output templates.

All ASA output text lives in pix2asa/templates/*.j2 files.
This module provides the shared Jinja2 Environment and helpers
used by actions.py (handler output) and converter.py (stanza output).

Template file names mirror the handler or concept they represent,
e.g. hostname.j2 for _handle_hostname output.

Rust port note: the same .j2 files can be loaded unchanged by
minijinja in the future Rust engine.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from jinja2 import Environment, FileSystemLoader, StrictUndefined

if TYPE_CHECKING:
    from pix2asa.context import ConversionContext

_TMPL_DIR = Path(__file__).parent / "templates"

#: Shared Jinja2 environment.  auto_reload=True lets template files be
#: edited on disk without restarting the server (same as ssh-mock-server).
env = Environment(
    loader=FileSystemLoader(_TMPL_DIR),
    undefined=StrictUndefined,
    keep_trailing_newline=True,
    trim_blocks=False,
    auto_reload=True,
)

# Add repr filter so templates can do {{ line | repr }}
env.filters["repr"] = repr


def render_template(tpl_name: str, variables: dict) -> str:
    """Render *tpl_name* with *variables* and return the result as a string."""
    return env.get_template(tpl_name).render(**variables)


def emit_lines(tpl_name: str, variables: dict, ctx: ConversionContext) -> None:
    """Render *tpl_name* and append each non-empty output line as a ConfigLine.

    Blank lines produced by the template are silently dropped so that
    conditional blocks that produce no output leave no gaps.
    """
    from pix2asa.models import ConfigLine

    rendered = render_template(tpl_name, variables)
    for line in rendered.splitlines():
        if line:
            ctx.config_lines.append(ConfigLine(line))
