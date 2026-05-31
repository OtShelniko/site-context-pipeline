"""Tests for the deterministic content QA module.

The QA module reads a Markdown draft + an optional context pack and
returns a structured report with one finding per check. Each finding
has:

* ``name`` — stable token (e.g. ``single_h1``, ``keyphrase_in_h1``);
* ``level`` — ``"green"``, ``"orange"``, or ``"red"``;
* ``message`` — short human description;
* ``details`` — provider-specific diagnostic dict.

The tests use 11 fixtures under ``tests/fixtures/qa/``. Each fixture
is named so the rule it should fail is obvious from the filename.

Coverage:
  * happy path: green draft passes every check;
  * missing H1 → red on ``single_h1``;
  * multiple H1 → red on ``single_h1``;
  * heading jump (H1 → H4) → red on ``heading_hierarchy``;
  * keyphrase missing in H1 → red on ``keyphrase_in_h1``;
  * keyphrase density too low → red on ``keyphrase_density``;
  * short intro → orange on ``intro_length``;
  * anchor equals keyphrase → red on ``competing_anchors``;
  * image without alt text → red on ``image_alt``;
  * link off inventory → red on ``links_resolve``;
  * slug mismatch → red on ``slug_keyphrase``;
  * Markdown without YAML frontmatter still works (uses defaults).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from site_context_pipeline.qa import QAFinding, QAReport, analyse_draft, analyse_draft_file

FIXTURES = Path(__file__).parent / "fixtures" / "qa"

# Inventory we hand to the QA tests. URLs that resolve in this list are
# considered "in the inventory"; anything outside is flagged.
INVENTORY_URLS = {
    "https://example.com/services/local-delivery/",
    "https://example.com/services/long-haul-delivery/",
    "https://example.com/blog/delivery-cost-guide/",
    "https://example.com/pricing/",
}


def _findings(report: QAReport) -> dict[str, QAFinding]:
    return {finding.name: finding for finding in report.findings}


def test_green_draft_has_no_red_findings() -> None:
    report = analyse_draft_file(
        FIXTURES / "green_draft.md",
        inventory_urls=INVENTORY_URLS,
    )
    reds = [f for f in report.findings if f.level == "red"]
    assert reds == [], f"unexpected red findings: {[f.name for f in reds]}"
    assert report.overall_level in {"green", "orange"}


def test_no_h1_is_red() -> None:
    report = analyse_draft_file(FIXTURES / "red_no_h1.md", inventory_urls=INVENTORY_URLS)
    assert _findings(report)["single_h1"].level == "red"


def test_multiple_h1_is_red() -> None:
    report = analyse_draft_file(
        FIXTURES / "red_multiple_h1.md", inventory_urls=INVENTORY_URLS
    )
    assert _findings(report)["single_h1"].level == "red"


def test_heading_jump_is_red() -> None:
    report = analyse_draft_file(
        FIXTURES / "red_heading_jump.md", inventory_urls=INVENTORY_URLS
    )
    finding = _findings(report)["heading_hierarchy"]
    assert finding.level == "red"
    assert "H4" in finding.message or "h4" in finding.message


def test_keyphrase_missing_in_h1_is_red() -> None:
    report = analyse_draft_file(
        FIXTURES / "red_keyphrase_missing_in_h1.md",
        inventory_urls=INVENTORY_URLS,
    )
    assert _findings(report)["keyphrase_in_h1"].level == "red"


def test_keyphrase_density_too_low_is_red() -> None:
    report = analyse_draft_file(
        FIXTURES / "red_keyphrase_density_too_low.md",
        inventory_urls=INVENTORY_URLS,
    )
    assert _findings(report)["keyphrase_density"].level == "red"


def test_short_intro_is_orange() -> None:
    report = analyse_draft_file(
        FIXTURES / "orange_short_intro.md", inventory_urls=INVENTORY_URLS
    )
    finding = _findings(report)["intro_length"]
    assert finding.level == "orange"


def test_anchor_equals_keyphrase_is_red() -> None:
    report = analyse_draft_file(
        FIXTURES / "red_anchor_equals_keyphrase.md",
        inventory_urls=INVENTORY_URLS,
    )
    assert _findings(report)["competing_anchors"].level == "red"


def test_image_without_alt_is_red() -> None:
    report = analyse_draft_file(
        FIXTURES / "red_missing_alt.md", inventory_urls=INVENTORY_URLS
    )
    assert _findings(report)["image_alt"].level == "red"


def test_link_off_inventory_is_red() -> None:
    report = analyse_draft_file(
        FIXTURES / "red_link_off_inventory.md", inventory_urls=INVENTORY_URLS
    )
    finding = _findings(report)["links_resolve"]
    assert finding.level == "red"
    assert "legacy-page" in str(finding.details)


def test_slug_mismatch_is_red() -> None:
    report = analyse_draft_file(
        FIXTURES / "red_slug_mismatch.md", inventory_urls=INVENTORY_URLS
    )
    assert _findings(report)["slug_keyphrase"].level == "red"


def test_analyse_draft_accepts_string_input() -> None:
    """Library callers can pass markdown directly without a file."""
    md = "# Hello world\n\nA short body about hello world."
    report = analyse_draft(
        md, keyphrase="hello world", inventory_urls=INVENTORY_URLS
    )
    assert report.overall_level in {"green", "orange", "red"}
    # H1 contains the keyphrase, so this finding must be green.
    assert _findings(report)["keyphrase_in_h1"].level == "green"


def test_qa_report_serialises_to_dict() -> None:
    report = analyse_draft_file(
        FIXTURES / "green_draft.md", inventory_urls=INVENTORY_URLS
    )
    payload = report.to_dict()
    assert "overall_level" in payload
    assert "findings" in payload
    assert isinstance(payload["findings"], list)
    assert all("name" in f and "level" in f for f in payload["findings"])


def test_missing_keyphrase_falls_back_to_frontmatter(tmp_path: Path) -> None:
    """If the caller does not pass a keyphrase, the YAML frontmatter
    (`keyphrase:` key) wins."""
    md = (
        "---\n"
        "keyphrase: derived from frontmatter\n"
        "slug: derived-from-frontmatter\n"
        "---\n"
        "\n"
        "# Derived from frontmatter\n"
        "\n"
        "Body about derived from frontmatter. Derived from frontmatter "
        "is the topic. Derived from frontmatter once more.\n"
    )
    path = tmp_path / "fm.md"
    path.write_text(md, encoding="utf-8")
    report = analyse_draft_file(path, inventory_urls=INVENTORY_URLS)
    assert _findings(report)["keyphrase_in_h1"].level == "green"


def test_analyse_draft_raises_on_missing_keyphrase(tmp_path: Path) -> None:
    """If neither the caller nor frontmatter supply a keyphrase, the
    function raises so the CLI can surface a clean error."""
    path = tmp_path / "no-key.md"
    path.write_text("# Hello\n\nbody\n", encoding="utf-8")
    with pytest.raises(ValueError):
        analyse_draft_file(path, inventory_urls=INVENTORY_URLS)
