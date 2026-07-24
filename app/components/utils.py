"""Formatting, parsing, and color helpers for plutometer's Streamlit UI."""

import re

SUFFIX_MULTIPLIERS = {"K": 1e3, "M": 1e6, "B": 1e9, "T": 1e12}
_VALUE_RE = re.compile(r"^([0-9]*\.?[0-9]+)\s*([KkMmBbTt]?)$")

GEO_LABELS = {"state": "Whole States", "county": "Whole Counties", "tract": "Whole Neighborhoods"}
_GEO_LABELS_SINGULAR = {"state": "whole state", "county": "whole county", "tract": "whole neighborhood"}
LEVEL_LABELS = {"state": "State", "county": "County", "tract": "Neighborhood (tract)"}
LEVEL_ORDER = ["state", "county", "tract"]

HIGHLIGHT_FILL = "#F57C00"
HIGHLIGHT_BORDER = "#E65100"
TRACT_MIN_ZOOM = 8


def geo_label(level: str, count: float) -> str:
    """Singular/plural geography label, e.g. geo_label('state', 1) -> 'whole state',
    geo_label('county', 3) -> 'whole counties'."""
    if round(count) == 1:
        return _GEO_LABELS_SINGULAR.get(level, level)
    return GEO_LABELS.get(level, level).lower()


def parse_value(raw: str) -> float | None:
    """Parse a dollar amount with optional K/M/B/T shorthand (e.g. '500B', '1.5T')."""
    if not raw:
        return None
    s = raw.strip().replace("$", "").replace(",", "").strip()
    match = _VALUE_RE.match(s)
    if not match:
        return None
    n = float(match.group(1))
    suffix = match.group(2).upper()
    n *= SUFFIX_MULTIPLIERS.get(suffix, 1)
    return n if n > 0 else None


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


def price_color(value: float, vmin: float, vmax: float) -> str:
    """Blue (high) -> yellow (low) gradient, matching the original Leaflet overlay."""
    if vmax == vmin:
        return "#78909C"
    t = min(1.0, max(0.0, (value - vmin) / (vmax - vmin)))
    r = round(25 + t * 230)
    g = round(118 + t * 122)
    b = round(210 - t * 180)
    return f"rgb({r},{g},{b})"
