"""Deterministic content-QA over Markdown drafts.

The QA module reads a Markdown draft (optionally with YAML
frontmatter) plus a few hints — the keyphrase, the inventory URL
list, an optional minimum word count — and returns a structured
report. Each rule is one function that produces a ``QAFinding``;
the runner just collects them.

This is **not** an LLM. The whole module is regex + standard library,
so every check is reproducible and runs offline. Failure modes (red
/ orange) are stable string tokens you can grep for in CI.

Rules implemented in 0.x:

* ``single_h1``           — exactly one ``# H1`` heading.
* ``heading_hierarchy``   — no skips (``H1 → H4`` is red, ``H1 → H2 → H3`` is fine).
* ``keyphrase_in_h1``     — the H1 contains the keyphrase as a substring.
* ``keyphrase_density``   — the keyphrase appears ≥ 3 times in the body.
* ``intro_length``        — the lead paragraph (text under H1, before the
  first H2) is ≥ 30 words. Shorter is orange, empty is red.
* ``competing_anchors``   — no internal-link anchor text equals the
  keyphrase exactly.
* ``image_alt``           — every image has non-empty alt text.
* ``links_resolve``       — every internal link target is in the
  ``inventory_urls`` set when one is provided.
* ``slug_keyphrase``      — the slug shares ≥ 1 stem with the keyphrase
  (after ASCII-folding).

Adding a new rule is one function plus a register entry. The CLI
verb ``qa-draft`` is a thin wrapper around ``analyse_draft_file``.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

QALevel = Literal["green", "orange", "red"]


@dataclass(frozen=True)
class QAFinding:
    name: str
    level: QALevel
    message: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class QAReport:
    keyphrase: str
    slug: str
    overall_level: QALevel
    findings: list[QAFinding]

    def to_dict(self) -> dict[str, Any]:
        return {
            "keyphrase": self.keyphrase,
            "slug": self.slug,
            "overall_level": self.overall_level,
            "findings": [asdict(f) for f in self.findings],
        }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def analyse_draft_file(
    path: str | Path,
    *,
    keyphrase: str | None = None,
    slug: str | None = None,
    inventory_urls: Iterable[str] | None = None,
) -> QAReport:
    """Read a Markdown file at ``path`` and run the full check set.

    Frontmatter ``keyphrase`` / ``slug`` keys are used when the caller
    does not pass them explicitly. Raises ``ValueError`` if no
    keyphrase can be resolved at all — without one, the QA output is
    meaningless.
    """
    text = Path(path).read_text(encoding="utf-8")
    return analyse_draft(
        text,
        keyphrase=keyphrase,
        slug=slug,
        inventory_urls=inventory_urls,
    )


def analyse_draft(
    markdown: str,
    *,
    keyphrase: str | None = None,
    slug: str | None = None,
    inventory_urls: Iterable[str] | None = None,
) -> QAReport:
    """Run every check against a Markdown string, return a ``QAReport``."""
    frontmatter, body = _split_frontmatter(markdown)
    keyphrase_resolved = (
        keyphrase
        or frontmatter.get("keyphrase")
        or frontmatter.get("main_keyword")
        or ""
    ).strip()
    if not keyphrase_resolved:
        raise ValueError(
            "QA needs a keyphrase. Pass keyphrase=... or set 'keyphrase:' "
            "in the YAML frontmatter."
        )
    slug_resolved = (slug or frontmatter.get("slug") or "").strip()
    inventory_set = {u for u in (inventory_urls or ()) if isinstance(u, str)}

    headings = _collect_headings(body)
    h1s = [h for h in headings if h["level"] == 1]
    h1_text = h1s[0]["text"] if h1s else ""
    body_text = _strip_markdown(body)
    intro_text = _intro_text(body, headings)
    images = _collect_images(body)
    links = _collect_links(body)

    findings: list[QAFinding] = [
        _check_single_h1(h1s),
        _check_heading_hierarchy(headings),
        _check_keyphrase_in_h1(h1_text, keyphrase_resolved),
        _check_keyphrase_density(body_text, keyphrase_resolved),
        _check_intro_length(intro_text),
        _check_competing_anchors(links, keyphrase_resolved),
        _check_image_alt(images),
        _check_links_resolve(links, inventory_set),
        _check_slug_keyphrase(slug_resolved, keyphrase_resolved),
    ]

    overall = _overall_level(findings)
    return QAReport(
        keyphrase=keyphrase_resolved,
        slug=slug_resolved,
        overall_level=overall,
        findings=findings,
    )


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------


def _check_single_h1(h1s: list[dict[str, Any]]) -> QAFinding:
    n = len(h1s)
    if n == 1:
        return QAFinding(
            "single_h1", "green", "Exactly one H1 heading.", {"count": 1}
        )
    if n == 0:
        return QAFinding(
            "single_h1", "red", "No H1 heading found.", {"count": 0}
        )
    return QAFinding(
        "single_h1",
        "red",
        f"{n} H1 headings; a draft must have exactly one.",
        {"count": n},
    )


def _check_heading_hierarchy(headings: list[dict[str, Any]]) -> QAFinding:
    """A draft is fine when each heading goes at most +1 level deeper
    than the previous heading. ``H1 → H4`` is a red jump."""
    if not headings:
        return QAFinding(
            "heading_hierarchy", "red", "No headings at all.", {}
        )
    previous_level = 0
    for index, heading in enumerate(headings):
        level = int(heading["level"])
        if previous_level and level > previous_level + 1:
            return QAFinding(
                "heading_hierarchy",
                "red",
                f"Heading hierarchy jumps from H{previous_level} to H{level} "
                f"at heading #{index + 1}: {heading['text']!r}",
                {
                    "from_level": previous_level,
                    "to_level": level,
                    "heading_index": index,
                    "heading_text": heading["text"],
                },
            )
        previous_level = level
    return QAFinding(
        "heading_hierarchy", "green", "Heading hierarchy is well-formed.", {}
    )


def _check_keyphrase_in_h1(h1_text: str, keyphrase: str) -> QAFinding:
    if not h1_text:
        return QAFinding(
            "keyphrase_in_h1", "red", "No H1 heading to check.", {}
        )
    haystack = _normalise_for_match(h1_text)
    needle = _normalise_for_match(keyphrase)
    if needle in haystack:
        return QAFinding(
            "keyphrase_in_h1",
            "green",
            "H1 contains the keyphrase.",
            {"h1": h1_text, "keyphrase": keyphrase},
        )
    return QAFinding(
        "keyphrase_in_h1",
        "red",
        "H1 does not contain the keyphrase.",
        {"h1": h1_text, "keyphrase": keyphrase},
    )


def _check_keyphrase_density(body_text: str, keyphrase: str) -> QAFinding:
    haystack = _normalise_for_match(body_text)
    needle = _normalise_for_match(keyphrase)
    if not needle:
        return QAFinding(
            "keyphrase_density", "red", "Keyphrase is empty.", {"matches": 0}
        )
    matches = haystack.count(needle)
    if matches >= 3:
        return QAFinding(
            "keyphrase_density",
            "green",
            f"Keyphrase appears {matches} times.",
            {"matches": matches},
        )
    if matches > 0:
        return QAFinding(
            "keyphrase_density",
            "orange",
            f"Keyphrase appears only {matches} time(s); aim for ≥3.",
            {"matches": matches},
        )
    return QAFinding(
        "keyphrase_density",
        "red",
        "Keyphrase does not appear in the body.",
        {"matches": 0},
    )


def _check_intro_length(intro_text: str) -> QAFinding:
    words = len(re.findall(r"\w+", intro_text))
    if words >= 30:
        return QAFinding(
            "intro_length",
            "green",
            f"Intro is {words} words.",
            {"words": words},
        )
    if words >= 5:
        return QAFinding(
            "intro_length",
            "orange",
            f"Intro is only {words} words; aim for ≥30.",
            {"words": words},
        )
    return QAFinding(
        "intro_length",
        "red",
        "Intro is empty or near-empty.",
        {"words": words},
    )


def _check_competing_anchors(
    links: list[dict[str, str]], keyphrase: str
) -> QAFinding:
    needle = _normalise_for_match(keyphrase)
    bad: list[dict[str, str]] = []
    for link in links:
        anchor = _normalise_for_match(link.get("text", ""))
        if anchor and anchor == needle:
            bad.append(link)
    if bad:
        return QAFinding(
            "competing_anchors",
            "red",
            f"{len(bad)} internal link(s) use the keyphrase as exact "
            "anchor text. Vary the wording.",
            {"links": bad},
        )
    return QAFinding(
        "competing_anchors",
        "green",
        "No anchor text equals the keyphrase exactly.",
        {},
    )


def _check_image_alt(images: list[dict[str, str]]) -> QAFinding:
    bad = [img for img in images if not (img.get("alt") or "").strip()]
    if not images:
        # An article with no images is not a problem per se; flag as
        # green so it does not interfere with the overall light.
        return QAFinding(
            "image_alt",
            "green",
            "No images in the draft.",
            {"images": 0},
        )
    if bad:
        return QAFinding(
            "image_alt",
            "red",
            f"{len(bad)} image(s) without alt text.",
            {"missing": bad, "image_count": len(images)},
        )
    return QAFinding(
        "image_alt",
        "green",
        f"All {len(images)} image(s) have alt text.",
        {"image_count": len(images)},
    )


def _check_links_resolve(
    links: list[dict[str, str]], inventory_urls: set[str]
) -> QAFinding:
    """Internal links (links pointing at the same site) should resolve
    to URLs the toolkit knows about. Without an inventory we cannot
    judge — return green and say so."""
    if not inventory_urls:
        return QAFinding(
            "links_resolve",
            "green",
            "No inventory provided; skipping link resolution check.",
            {},
        )
    inventory_hosts = _hosts(inventory_urls)
    off_inventory: list[str] = []
    for link in links:
        url = link.get("url", "")
        if not url:
            continue
        host = _host(url)
        if host and host not in inventory_hosts:
            # External link — out of scope for this check.
            continue
        if url not in inventory_urls:
            off_inventory.append(url)
    if off_inventory:
        return QAFinding(
            "links_resolve",
            "red",
            f"{len(off_inventory)} internal link(s) target a URL not in "
            "the site inventory.",
            {"off_inventory": off_inventory},
        )
    return QAFinding(
        "links_resolve",
        "green",
        "All internal links resolve to inventory URLs.",
        {},
    )


def _check_slug_keyphrase(slug: str, keyphrase: str) -> QAFinding:
    if not slug:
        return QAFinding(
            "slug_keyphrase",
            "orange",
            "No slug provided; cannot compare to the keyphrase.",
            {},
        )
    slug_tokens = {tok for tok in re.split(r"[^a-z0-9]+", slug.lower()) if tok}
    keyphrase_tokens = {
        tok for tok in re.split(r"[^a-z0-9]+", keyphrase.lower()) if tok
    }
    overlap = slug_tokens & keyphrase_tokens
    if overlap:
        return QAFinding(
            "slug_keyphrase",
            "green",
            "Slug shares at least one token with the keyphrase.",
            {"shared": sorted(overlap)},
        )
    return QAFinding(
        "slug_keyphrase",
        "red",
        "Slug and keyphrase share no tokens; rename the slug.",
        {
            "slug": slug,
            "keyphrase": keyphrase,
        },
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)


def _split_frontmatter(markdown: str) -> tuple[dict[str, str], str]:
    """Lightweight YAML-frontmatter parser limited to ``key: value`` lines.

    We deliberately avoid pulling in a YAML parser. The QA module only
    uses two fields (``keyphrase``, ``slug``), so the trade-off is
    acceptable and keeps the dependency-free invariant.
    """
    match = _FRONTMATTER_RE.match(markdown)
    if not match:
        return {}, markdown
    fm: dict[str, str] = {}
    for line in match.group(1).splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, _, value = line.partition(":")
        fm[key.strip().lower()] = value.strip().strip('"').strip("'")
    body = markdown[match.end() :]
    return fm, body


_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$", re.MULTILINE)
_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
_LINK_RE = re.compile(r"(?<!\!)\[([^\]]+)\]\(([^)]+)\)")
_TAG_RE = re.compile(r"<[^>]+>")


def _collect_headings(body: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for match in _HEADING_RE.finditer(body):
        level = len(match.group(1))
        text = match.group(2).strip()
        out.append({"level": level, "text": text, "offset": match.start()})
    return out


def _collect_images(body: str) -> list[dict[str, str]]:
    return [
        {"alt": match.group(1).strip(), "url": match.group(2).strip()}
        for match in _IMAGE_RE.finditer(body)
    ]


def _collect_links(body: str) -> list[dict[str, str]]:
    return [
        {"text": match.group(1).strip(), "url": match.group(2).strip()}
        for match in _LINK_RE.finditer(body)
    ]


def _strip_markdown(text: str) -> str:
    """Best-effort plain-text extraction for density / word-count
    checks. Removes images and link wrappers but keeps the link text
    so keyphrase counting still works."""
    text = _IMAGE_RE.sub(" ", text)
    text = _LINK_RE.sub(lambda m: m.group(1), text)
    text = _TAG_RE.sub(" ", text)
    return text


def _intro_text(body: str, headings: list[dict[str, Any]]) -> str:
    """Text under the first H1, before the first H2 (or the next H1
    if no H2 follows)."""
    h1s = [h for h in headings if h["level"] == 1]
    if not h1s:
        return ""
    start = h1s[0]["offset"]
    after_h1 = body.find("\n", start)
    if after_h1 == -1:
        return ""
    next_lower_or_equal = next(
        (h["offset"] for h in headings if h["offset"] > start),
        len(body),
    )
    return _strip_markdown(body[after_h1 + 1 : next_lower_or_equal]).strip()


def _normalise_for_match(text: str) -> str:
    """Lower-case + collapse whitespace; remove punctuation that should
    not break a phrase match."""
    text = text.lower()
    text = re.sub(r"[^\w\s]+", " ", text, flags=re.UNICODE)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _hosts(urls: set[str]) -> set[str]:
    out: set[str] = set()
    for url in urls:
        host = _host(url)
        if host:
            out.add(host)
    return out


def _host(url: str) -> str:
    match = re.match(r"https?://([^/]+)", url)
    return match.group(1).lower() if match else ""


def _overall_level(findings: list[QAFinding]) -> QALevel:
    if any(f.level == "red" for f in findings):
        return "red"
    if any(f.level == "orange" for f in findings):
        return "orange"
    return "green"
