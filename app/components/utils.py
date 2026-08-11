"""Formatting, parsing, and color helpers for plutometer's Streamlit UI."""

import math
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

# Partial-match map indicator (num_selected == 0, i.e. the target undercuts even the
# nearest whole geography). Below FEW_HOUSES_MAX houses, a growing dot at the marker
# carries the magnitude -- a fixed-size shape can use its full visual range regardless
# of how big the underlying geography is, which a fill opacity can't at these tiny
# fractions (see PARTIAL_FILL_OPACITY_FLOOR). At/above FEW_HOUSES_MAX, the dot hands
# off to filling the actual nearest geography, since a house count in that range is
# large enough that "how much of this real shape" becomes the more honest answer than
# an arbitrarily-sized circle floating over it.
# Kept below the whole-selection fill opacity (0.55, see map_view._add_highlight_layer)
# so a partial match is never visually confusable with "you got the whole thing."
PARTIAL_FILL_OPACITY_FLOOR = 0.2
PARTIAL_FILL_OPACITY_CAP = 0.45
# Dashed, not solid -- the border style itself (not just a lighter fill) is what marks
# a partial-match layer as "approximate," so it stays visually distinct from a whole
# selection even in overlay modes/zoom levels where the opacity difference is subtle.
PARTIAL_DASH_ARRAY = "6, 4"

# One dot per house, always, no cap -- literal individual units read as more concrete
# than an abstract growing circle, and "one dot might stand for 2+ houses" (an earlier
# version capped the drawn count and let the ring alone keep growing past it) undermines
# that the moment someone notices the count doesn't match. Sized to just ring the click
# marker itself (radius 7px, see map_view._add_marker), not dwarf it. All sizes below
# are a baseline tuned for PARTIAL_DOT_REF_ZOOM -- see partial_dot_zoom_scale for why
# they can't just be fixed pixel constants the way the click marker's own halo is.
PARTIAL_DOT_DIAMETER_PX = 14
# Packing radius (in dot-diameters) for n dots arranged in the sunflower/Vogel spiral
# partial_dot_positions builds -- tuned so same-size dots tile without overlapping,
# however many there are.
PARTIAL_DOT_PACK_FACTOR = 0.62
PARTIAL_DOT_OPACITY_FLOOR = 0.3
PARTIAL_DOT_OPACITY_FULL = 0.85

# A fixed pixel size looks right at one zoom and wrong at every other one -- the actual
# geography around it (the tract outline, the gradient fill) shrinks on screen as you
# zoom out, so a constant-size dot cluster increasingly overshoots it and reads as
# oversized. TRACT_MIN_ZOOM is what the app auto-lands on for a fractional tract result
# (see app.py's auto-cascade), so it's the zoom the sizes above are tuned for; scaling
# by 2x per zoom level away from it matches how Web Mercator itself halves
# degrees-per-pixel per +1 zoom, so the cluster tracks the geography's own on-screen
# size instead of staying fixed. Deliberately *not* floored on the low end -- a floor
# reintroduces the exact "looks huge once zoomed out past it" bug this exists to fix,
# just at whatever zoom the floor kicks in instead of at PARTIAL_DOT_REF_ZOOM. Only
# capped on the high end, to keep zooming in from blowing the cluster up indefinitely.
PARTIAL_DOT_REF_ZOOM = TRACT_MIN_ZOOM
PARTIAL_DOT_MAX_SCALE = 2.5


def partial_fill_opacity(fraction: float) -> float:
    """Fill opacity for the partial-match geography, scaled by how much of its total
    value the target represents (target_value / geography_value)."""
    t = max(0.0, min(1.0, fraction))
    return PARTIAL_FILL_OPACITY_FLOOR + (PARTIAL_FILL_OPACITY_CAP - PARTIAL_FILL_OPACITY_FLOOR) * t


def partial_dot_zoom_scale(zoom: int) -> float:
    """Screen-size multiplier for the partial-match dot cluster at the given zoom,
    relative to its PARTIAL_DOT_REF_ZOOM-tuned baseline size -- see that constant's
    comment for why this needs to exist, and why it's unclamped below PARTIAL_DOT_REF_ZOOM.
    """
    return min(PARTIAL_DOT_MAX_SCALE, 2 ** (zoom - PARTIAL_DOT_REF_ZOOM))


def partial_dot_positions(houses: float) -> list[tuple[float, float]]:
    """Baseline (pre zoom-scale) pixel (dx, dy) offsets for exactly round(houses) dots
    (capped only by FEW_HOUSES_MAX, the tier boundary this is never called past -- see
    map_view.build_map), one per house. A single house sits exactly on the click point;
    for more than one, dots are packed via a sunflower/Vogel spiral (even density, no
    overlap, no preferred direction) whose radius grows with sqrt(n) -- the same
    relationship a real evenly-packed cluster of n same-size items has, so the *whole*
    cluster's footprint scales legibly with house count instead of freezing once some
    fixed dot-count cap is hit.
    """
    n = max(1, min(round(houses), FEW_HOUSES_MAX))
    if n == 1:
        return [(0.0, 0.0)]
    golden_angle = math.pi * (3 - math.sqrt(5))
    pack_radius = PARTIAL_DOT_PACK_FACTOR * PARTIAL_DOT_DIAMETER_PX * math.sqrt(n)
    positions = []
    for i in range(n):
        r = pack_radius * math.sqrt((i + 0.5) / n)
        theta = i * golden_angle
        positions.append((r * math.cos(theta), r * math.sin(theta)))
    return positions


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


def house_icon_row(houses: float, max_icons: int = 6) -> str:
    """Small HTML row of house glyphs standing in for a house count -- one icon per whole
    house, a faded icon for a fractional remainder, capped at max_icons with a "+N more"
    label past that so a six-figure house count doesn't render six figures of icons.
    Kept to a low icon cap, smaller glyph size, and an explicit nowrap flex row so the
    "+N more" tail never wraps onto its own line regardless of card width -- a low cap
    reads just as well as a high one here (the point is "several houses", not a precise
    count) and avoids the wasted line a wider row risked at mobile widths.
    """
    whole = int(houses)
    frac = houses - whole
    shown_whole = min(whole, max_icons)
    icons = "\U0001F3E0" * shown_whole
    if frac > 0.05 and shown_whole < max_icons:
        icons += f'<span style="opacity:{0.25 + 0.75 * frac:.2f}">\U0001F3E0</span>'
    remainder = whole - shown_whole
    extra = (
        f'<span style="opacity:0.7;font-size:0.85rem;margin-left:4px;">+{fmt_num(remainder)} more</span>'
        if remainder > 0
        else ""
    )
    return (
        '<span style="display:inline-flex;align-items:center;white-space:nowrap;">'
        f'<span style="font-size:1.35rem;letter-spacing:1px;">{icons}</span>{extra}</span>'
    )


def price_color(value: float, vmin: float, vmax: float) -> str:
    """Blue (high) -> yellow (low) gradient, matching the original Leaflet overlay."""
    if vmax == vmin:
        return "#78909C"
    t = min(1.0, max(0.0, (value - vmin) / (vmax - vmin)))
    r = round(25 + t * 230)
    g = round(118 + t * 122)
    b = round(210 - t * 180)
    return f"rgb({r},{g},{b})"
