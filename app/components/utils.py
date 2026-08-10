"""Formatting, parsing, and color helpers for plutometer's Streamlit UI."""

import re

SUFFIX_MULTIPLIERS = {"K": 1e3, "M": 1e6, "B": 1e9, "T": 1e12}
_VALUE_RE = re.compile(r"^([0-9]*\.?[0-9]+)\s*([KkMmBbTt]?)$")

GEO_LABELS = {"state": "Whole States", "county": "Whole Counties", "tract": "Whole Neighborhoods"}
_GEO_LABELS_SINGULAR = {"state": "whole state", "county": "whole county", "tract": "whole neighborhood"}
_GEO_NOUNS = {"state": "state", "county": "county", "tract": "neighborhood"}
LEVEL_LABELS = {"state": "State", "county": "County", "tract": "Neighborhood (tract)"}
LEVEL_ORDER = ["state", "county", "tract"]

# Boundaries for fractional_headline's house-count tiers -- see its docstring.
FEW_HOUSES_MAX = 50

HIGHLIGHT_FILL = "#F57C00"
HIGHLIGHT_BORDER = "#E65100"
TRACT_MIN_ZOOM = 8


def geo_label(level: str, count: float) -> str:
    """Singular/plural geography label, e.g. geo_label('state', 1) -> 'whole state',
    geo_label('county', 3) -> 'whole counties'."""
    if round(count) == 1:
        return _GEO_LABELS_SINGULAR.get(level, level)
    return GEO_LABELS.get(level, level).lower()


def fractional_headline(level: str, houses: float) -> str:
    """Headline for when a target undercuts even the single smallest geography at
    this level (num_selected == 0). "Smaller than a single whole neighborhood"
    reads as roughly the same non-answer whether the money buys 3 houses or 300 --
    a neighborhood-scale geography (a Census tract) can hold hundreds to thousands
    of homes, so this tiers the wording by the actual house count instead:
    under 1 house, a handful (up to FEW_HOUSES_MAX), or a partial geography above
    that. The exact fractional count is still shown separately in the caption below
    this headline -- this just picks the right words for the scale it's at.
    """
    noun = _GEO_NOUNS.get(level, level)
    if houses < 1:
        return "Part of a house here"
    if houses <= FEW_HOUSES_MAX:
        return "A few houses here"
    return f"Part of a {noun} here"


def parse_value(raw: str) -> float | None:
    """Parse a dollar amount with optional K/M/B/T shorthand (e.g. '500B', '1.5T').

    Returns None only when the string doesn't match the expected format at all.
    A well-formed but non-positive amount (e.g. '0') is returned as-is (0.0)
    rather than folded into None, so the caller can tell "couldn't read that"
    apart from "read it fine, but it's not a usable amount" and message accordingly.
    """
    if not raw:
        return None
    s = raw.strip().replace("$", "").replace(",", "").strip()
    match = _VALUE_RE.match(s)
    if not match:
        return None
    n = float(match.group(1))
    suffix = match.group(2).upper()
    n *= SUFFIX_MULTIPLIERS.get(suffix, 1)
    return n


def fmt_dollar(value: float) -> str:
    """Compact dollar format, e.g. $1.5T, $485.0B, $192.9K."""
    v = abs(value)
    if v >= 1e12:
        return f"${value / 1e12:.1f}T"
    if v >= 1e9:
        return f"${value / 1e9:.1f}B"
    if v >= 1e6:
        return f"${value / 1e6:.1f}M"
    if v >= 1e3:
        return f"${value / 1e3:.0f}K"
    return f"${value:.0f}"


def fmt_full(value: float) -> str:
    """Full dollar format with thousands separators, e.g. $1,234,567."""
    return f"${round(value):,}"


def fmt_num(value: float) -> str:
    """Integer with thousands separators, e.g. 12,345."""
    return f"{round(value):,}"


def fmt_houses(value: float) -> str:
    """House count, e.g. 12,345. Below one, keeps two decimals (e.g. '0.17') instead
    of rounding a real fractional-home amount down to a meaningless '0'."""
    if value >= 1:
        return fmt_num(value)
    return f"{value:.2f}"


def house_icon_row(houses: float, max_icons: int = 10) -> str:
    """Small HTML row of house glyphs standing in for a house count -- one icon per whole
    house, a faded icon for a fractional remainder, capped at max_icons with a "+N more"
    label past that so a six-figure house count doesn't render six figures of icons.
    """
    whole = int(houses)
    frac = houses - whole
    shown_whole = min(whole, max_icons)
    icons = "\U0001F3E0" * shown_whole
    if frac > 0.05 and shown_whole < max_icons:
        icons += f'<span style="opacity:{0.25 + 0.75 * frac:.2f}">\U0001F3E0</span>'
    remainder = whole - shown_whole
    extra = f' <span style="opacity:0.7;">+{fmt_num(remainder)} more</span>' if remainder > 0 else ""
    return f'<span style="font-size:1.6rem;letter-spacing:2px;">{icons}</span>{extra}'


def price_color(value: float, vmin: float, vmax: float) -> str:
    """Blue (high) -> yellow (low) gradient, matching the original Leaflet overlay."""
    if vmax == vmin:
        return "#78909C"
    t = min(1.0, max(0.0, (value - vmin) / (vmax - vmin)))
    r = round(25 + t * 230)
    g = round(118 + t * 122)
    b = round(210 - t * 180)
    return f"rgb({r},{g},{b})"
