"""Tiny Markdown rendering helpers.

These produce the human-readable artifacts (``agent_context_pack.md``,
``content_opportunities.md``). They never accept arbitrary HTML; all input
is plain text or simple lists.
"""

from __future__ import annotations

from collections.abc import Iterable


def render_heading(level: int, text: str) -> str:
    level = max(1, min(level, 6))
    return f"{'#' * level} {text}\n"


def render_paragraph(text: str) -> str:
    return f"{text.strip()}\n"


def render_bullet_list(items: Iterable[str]) -> str:
    items = [item for item in items if item]
    if not items:
        return "_none_\n"
    return "\n".join(f"- {item}" for item in items) + "\n"


def render_definition_list(pairs: Iterable[tuple[str, str | int | float | None]]) -> str:
    """Render a simple ``key: value`` list using Markdown bullets."""
    rendered = []
    for key, value in pairs:
        if value is None or value == "":
            value_str = "_unset_"
        else:
            value_str = str(value)
        rendered.append(f"- **{key}:** {value_str}")
    if not rendered:
        return "_none_\n"
    return "\n".join(rendered) + "\n"


def render_link(anchor: str, url: str) -> str:
    safe_anchor = anchor.replace("[", "(").replace("]", ")") if anchor else url
    return f"[{safe_anchor}]({url})"
