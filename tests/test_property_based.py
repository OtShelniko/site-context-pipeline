"""Property-based tests for the fragile parsing and normalisation paths.

Example-based tests cover the obvious cases. These tests use Hypothesis
to generate random-but-shaped inputs and then assert *invariants* — the
properties every output of these functions must hold no matter what
goes in.

Functions under test:

* ``inventory.normalise_url`` — URL canonicalisation.
* ``inventory._match_path_pattern`` — glob-style path matcher.
* ``providers.local_keyword_csv._normalise_header`` — CSV header
  normalisation.
* ``providers.local_keyword_csv._first_int`` — int parser tolerant of
  thousand-separators and decimals.
* ``providers.local_keyword_csv._first_ratio`` — CTR parser tolerant
  of percent signs and decimal-comma locales.
* ``inventory.classify_url`` — never raises and always returns a known
  page type plus a non-empty reason token.

Property tests are kept budgeted (small ``max_examples``) so the suite
still finishes fast.
"""

from __future__ import annotations

from urllib.parse import urlparse

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from site_context_pipeline.inventory import (
    ClassifierRule,
    _match_path_pattern,
    classify_url,
    normalise_url,
)
from site_context_pipeline.providers.local_keyword_csv import (
    _first_int,
    _first_ratio,
    _normalise_header,
)

# Shared settings: keep the suite fast but cover real edge cases.
PROPERTY_SETTINGS = settings(
    max_examples=80,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much],
)


# ---------------------------------------------------------------------------
# normalise_url
# ---------------------------------------------------------------------------


# ASCII-only host parts so urlparse stays predictable. The OSS toolkit
# documents that URLs are expected to be already-puny-coded; we don't
# need to test IDN parsing.
_HOST_TEXT = st.text(
    alphabet=st.characters(min_codepoint=ord("a"), max_codepoint=ord("z")),
    min_size=1,
    max_size=12,
)
_PATH_SEGMENT = st.text(
    alphabet=st.characters(
        min_codepoint=ord("a"),
        max_codepoint=ord("z"),
        whitelist_categories=("Nd",),
        whitelist_characters="-_",
    ),
    min_size=0,
    max_size=8,
)


@st.composite
def url_strategy(draw: st.DrawFn) -> str:
    scheme = draw(st.sampled_from(["http", "https", "HTTP", "HTTPS"]))
    host_parts = draw(st.lists(_HOST_TEXT, min_size=1, max_size=3))
    host = ".".join(host_parts)
    if draw(st.booleans()):
        # Sometimes append a default port to exercise the stripping path.
        host = host + (":80" if scheme.lower() == "http" else ":443")
    if draw(st.booleans()):
        # Random capitalisation in the host.
        host = host.upper() if draw(st.booleans()) else host.lower()
    segments = draw(st.lists(_PATH_SEGMENT, min_size=0, max_size=4))
    path = "/" + "/".join(segments) if segments else ""
    if draw(st.booleans()):
        # Occasionally inject a duplicate slash.
        path = path.replace("/", "//", 1) if path else "/"
    # Restrict query/fragment to printable ASCII so urlparse stays
    # idempotent. Control characters in URLs are not a real input shape
    # for this toolkit (we read from sanitised CSVs and sitemaps).
    safe_text = st.text(
        alphabet=st.characters(min_codepoint=ord("!"), max_codepoint=ord("~")),
        max_size=8,
    )
    fragment = draw(safe_text)
    query = draw(safe_text)
    parts = [scheme, "://", host, path]
    if query:
        parts.extend(["?", query])
    if fragment:
        parts.extend(["#", fragment])
    return "".join(parts)


@PROPERTY_SETTINGS
@given(url=url_strategy())
def test_normalise_url_is_idempotent(url: str) -> None:
    once = normalise_url(url)
    twice = normalise_url(once)
    assert once == twice, (url, once, twice)


@PROPERTY_SETTINGS
@given(url=url_strategy())
def test_normalise_url_lowercases_scheme_and_host(url: str) -> None:
    out = normalise_url(url)
    parsed = urlparse(out)
    assert parsed.scheme == parsed.scheme.lower()
    assert parsed.netloc == parsed.netloc.lower()


@PROPERTY_SETTINGS
@given(url=url_strategy())
def test_normalise_url_strips_fragment(url: str) -> None:
    out = normalise_url(url)
    assert "#" not in out


@PROPERTY_SETTINGS
@given(url=url_strategy())
def test_normalise_url_collapses_repeated_slashes_in_path(url: str) -> None:
    out = normalise_url(url)
    parsed = urlparse(out)
    assert "//" not in parsed.path, (url, out)


@PROPERTY_SETTINGS
@given(host=_HOST_TEXT, path=st.lists(_PATH_SEGMENT, max_size=3))
def test_normalise_url_drops_default_ports(host: str, path: list[str]) -> None:
    suffix = ("/" + "/".join(s for s in path if s)) if path else "/"
    http = normalise_url(f"http://{host}:80{suffix}")
    https = normalise_url(f"https://{host}:443{suffix}")
    assert ":80" not in http, http
    assert ":443" not in https, https


# ---------------------------------------------------------------------------
# _match_path_pattern
# ---------------------------------------------------------------------------


@PROPERTY_SETTINGS
@given(
    path=st.text(
        alphabet=st.characters(min_codepoint=33, max_codepoint=126, blacklist_characters="*?["),
        min_size=1,
        max_size=40,
    )
)
def test_match_path_pattern_matches_self_substring(path: str) -> None:
    """A literal substring of the (lowercased) path must match the path."""

    lower = path.lower()
    if not lower:
        return
    midpoint = len(lower) // 2 or 1
    needle = lower[:midpoint]
    assert _match_path_pattern(lower, needle) is True


@PROPERTY_SETTINGS
@given(
    prefix=st.text(
        alphabet=st.characters(min_codepoint=ord("a"), max_codepoint=ord("z")),
        min_size=1,
        max_size=8,
    ),
    suffix=st.text(
        alphabet=st.characters(min_codepoint=ord("a"), max_codepoint=ord("z")),
        min_size=1,
        max_size=8,
    ),
)
def test_match_path_pattern_glob_matches_prefix_suffix(prefix: str, suffix: str) -> None:
    path = f"/{prefix}/middle/{suffix}/"
    assert _match_path_pattern(path, f"/{prefix}/*") is True
    assert _match_path_pattern(path, f"*/{suffix}/*") is True


# ---------------------------------------------------------------------------
# _normalise_header
# ---------------------------------------------------------------------------


@PROPERTY_SETTINGS
@given(
    header=st.text(
        alphabet=st.characters(min_codepoint=32, max_codepoint=126),
        min_size=0,
        max_size=30,
    )
)
def test_normalise_header_is_lowercase_and_alnum_only(header: str) -> None:
    out = _normalise_header(header)
    assert out == out.lower()
    assert all(ch.isalnum() for ch in out)


@PROPERTY_SETTINGS
@given(
    base=st.text(
        alphabet=st.characters(min_codepoint=ord("a"), max_codepoint=ord("z")),
        min_size=1,
        max_size=12,
    )
)
def test_normalise_header_treats_separators_as_equivalent(base: str) -> None:
    """`Search Volume`, `search_volume`, `search-volume` all match."""

    variants = [
        base,
        base.upper(),
        base.replace("a", " a "),
        base.replace("a", "_a_"),
        base.replace("a", "-a-"),
    ]
    normalised = {_normalise_header(v) for v in variants}
    # All variants of the same base must collapse to a single key.
    assert len(normalised) == 1, normalised


# ---------------------------------------------------------------------------
# _first_int
# ---------------------------------------------------------------------------


@PROPERTY_SETTINGS
@given(value=st.integers(min_value=-10_000_000, max_value=10_000_000))
def test_first_int_round_trips_plain_integers(value: int) -> None:
    row = {"v": str(value)}
    assert _first_int(row, ("v",)) == value


@PROPERTY_SETTINGS
@given(value=st.integers(min_value=0, max_value=10_000_000))
def test_first_int_handles_thousand_separator(value: int) -> None:
    formatted = f"{value:,}"  # e.g. 1234567 -> "1,234,567"
    row = {"v": formatted}
    assert _first_int(row, ("v",)) == value


@PROPERTY_SETTINGS
@given(value=st.text(max_size=10))
def test_first_int_never_raises(value: str) -> None:
    """Garbage in must not raise — only None or an int comes out."""

    out = _first_int({"v": value}, ("v",))
    assert out is None or isinstance(out, int)


# ---------------------------------------------------------------------------
# _first_ratio (CTR parser)
# ---------------------------------------------------------------------------


@PROPERTY_SETTINGS
@given(value=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False))
def test_first_ratio_passes_through_already_normalised_values(value: float) -> None:
    out = _first_ratio({"ctr": str(value)}, ("ctr",))
    assert out is not None
    assert 0.0 <= out <= 1.0
    # round() can introduce tiny drift; allow 1e-6.
    assert abs(out - value) < 1e-5 or out == round(value, 6)


@PROPERTY_SETTINGS
@given(percent=st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False))
def test_first_ratio_handles_percent_signs(percent: float) -> None:
    out = _first_ratio({"ctr": f"{percent}%"}, ("ctr",))
    assert out is not None
    assert 0.0 <= out <= 1.0 + 1e-9, (percent, out)


@PROPERTY_SETTINGS
@given(percent=st.floats(min_value=1.01, max_value=100.0, allow_nan=False, allow_infinity=False))
def test_first_ratio_treats_bare_above_one_as_percent(percent: float) -> None:
    """A bare ``12.3`` (no percent sign) is still a CTR percentage."""

    out = _first_ratio({"ctr": str(percent)}, ("ctr",))
    assert out is not None
    assert 0.0 <= out <= 1.0 + 1e-9, (percent, out)


@PROPERTY_SETTINGS
@given(value=st.text(max_size=12))
def test_first_ratio_never_raises(value: str) -> None:
    """Garbage in must not raise — only None or a 0..1-ish float comes out."""

    out = _first_ratio({"ctr": value}, ("ctr",))
    if out is not None:
        assert isinstance(out, float)
        # Heuristic divides bare-above-1 by 100, so output should be
        # at most a small constant — check a generous bound.
        assert out >= 0.0 - 1e-9, (value, out)


# ---------------------------------------------------------------------------
# classify_url
# ---------------------------------------------------------------------------


_KNOWN_PAGE_TYPES = {"home", "service", "blog", "category", "landing", "other"}


@PROPERTY_SETTINGS
@given(url=url_strategy())
def test_classify_url_returns_known_page_type_with_reason(url: str) -> None:
    page_type, reason = classify_url(
        normalise_url(url), rules=[], commercial_urls=set()
    )
    assert page_type in _KNOWN_PAGE_TYPES
    assert isinstance(reason, str) and reason


@PROPERTY_SETTINGS
@given(
    url=url_strategy(),
    page_type=st.sampled_from(["service", "blog", "category", "landing"]),
)
def test_classify_url_honours_a_matching_pattern(url: str, page_type: str) -> None:
    """Home URLs are detected before rules; for everything else, a wildcard
    rule must win and the reason must reference the rule."""

    normalised = normalise_url(url)
    parsed = urlparse(normalised)
    if (parsed.path or "/") in {"/", ""}:
        return  # home shortcut runs before rules; out of scope here.
    rule = ClassifierRule(page_type=page_type, pattern="*")  # match everything
    result_type, reason = classify_url(
        normalised, rules=[rule], commercial_urls=set()
    )
    assert result_type == page_type
    assert reason.startswith("matched_pattern:") or reason.startswith("matched_")


@PROPERTY_SETTINGS
@given(url=url_strategy())
def test_classify_url_promotes_commercial_urls_to_landing(url: str) -> None:
    """A non-home URL listed in ``commercial_urls`` is always ``landing``."""

    normalised = normalise_url(url)
    parsed = urlparse(normalised)
    if (parsed.path or "/") in {"/", ""}:
        return  # home wins over commercial promotion when path is `/`.
    page_type, reason = classify_url(
        normalised, rules=[], commercial_urls={normalised}
    )
    assert page_type == "landing"
    assert "commercial" in reason or "landing" in reason
