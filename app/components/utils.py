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
# version capped the drawn count) undermines that the moment someone notices the count
# doesn't match. Drawn as real ground geometry (folium.Circle, radius in meters --
# see map_view._add_partial_dot), not a fixed pixel size: a pixel-sized marker either
# looks right at one zoom and wrong at every other one, or (worse) has no relationship
# to how big the underlying geography actually is on screen. Real geometry sidesteps
# both problems at once -- it scales with zoom exactly like the tract polygon itself
# does, automatically, and its size is derived from that specific tract's own area
# rather than a guessed constant.
#
# How much bigger the cluster's overall footprint is allowed to be than the literal
# sum of its own dots' areas -- small headroom so n dots can spread out and stay
# individually legible, without letting the *cluster itself* balloon past what the
# house count actually represents. A pure packing-density constant (spread ~
# diameter*sqrt(n)) doesn't cap this: it grows the encompassing circle faster than the
# dots' own total area does, so by ~10 houses the whole cluster was already reading as
# visibly bigger than 10 houses' real share of the tract, worse for any more than that.
PARTIAL_DOT_CLUSTER_OVERHEAD = 1.4
PARTIAL_DOT_OPACITY_FLOOR = 0.3
PARTIAL_DOT_OPACITY_FULL = 0.85

# Zoom the app auto-deepens to for a sub-tract (fractional) result. TRACT_MIN_ZOOM only
# guarantees tract *boundaries* are visible -- nowhere near close enough to make a
# handful of individual, real-scale house dots (a tiny fraction of the tract's area, see
# per_house_area_m2 below) legible. 17 -- confirmed working well in the intro tour's
# median/block steps (components/intro.py's STEP_ZOOM), which share this exact value
# and this exact dot-sizing code but never had the main map's remount/rerun bug (the
# intro's own st_folium call uses returned_objects=[], no live view-tracking at all) --
# is kept as-is here. That comparison is the strongest evidence available that the
# *value* was never the problem; see app.py's st_folium() call for the actual fix
# (the map was remounting from scratch on every zoom/pan, discarding manual navigation
# and, under rapid changes, falling behind and rendering stale intermediate states).
PARTIAL_MATCH_ZOOM = 17


def partial_fill_opacity(fraction: float) -> float:
    """Fill opacity for the partial-match geography, scaled by how much of its total
    value the target represents (target_value / geography_value)."""
    t = max(0.0, min(1.0, fraction))
    return PARTIAL_FILL_OPACITY_FLOOR + (PARTIAL_FILL_OPACITY_CAP - PARTIAL_FILL_OPACITY_FLOOR) * t


def per_house_area_m2(geo_area_m2: float, fraction: float, houses: float) -> float:
    """One house's average real-world footprint (m^2) within a specific geography, given
    that geography's own ground area, and the target's fraction/houses (see
    map_view._add_partial_dot). fraction (target_value / geo_value) equals
    houses / geo's total housing units by construction -- total value is
    housing_units * median_home_value nationwide (scripts/prepare_data.py) -- so
    fraction / houses is exactly 1 / total housing units, independent of the target
    amount itself. This is what makes "10 houses" a small, honestly-sized fraction of
    a dense tract's area and a comparatively larger one of a sparse tract's -- it's
    driven by that specific geography's own real density, not an assumed constant.
    """
    if houses <= 0:
        return 0.0
    return geo_area_m2 * fraction / houses


def partial_dot_cluster_radius(n: int, dot_radius: float) -> float:
    """Radius of the smallest circle guaranteed to contain n dots of the given radius,
    with PARTIAL_DOT_CLUSTER_OVERHEAD headroom for spacing -- i.e. the whole cluster's
    footprint is capped at PARTIAL_DOT_CLUSTER_OVERHEAD x what n dots' worth of area
    literally is, not however much room a spiral happens to spread them across. Unit-
    agnostic (pixels, meters, ...) -- matches whatever unit dot_radius is given in.
    """
    return math.sqrt(n * dot_radius**2 * PARTIAL_DOT_CLUSTER_OVERHEAD)


def sunflower_positions(n: int, dot_radius: float) -> list[tuple[float, float]]:
    """Evenly-packed (dx, dy) offsets, in whatever unit dot_radius is given in (pixels,
    meters, ...), for n same-size circles of that radius -- a sunflower/Vogel spiral
    (even density, no preferred direction), spread out to just reach
    partial_dot_cluster_radius(n, dot_radius) at the outermost dot's outer edge. A
    single circle (n <= 1) sits exactly at the origin.
    """
    if n <= 1:
        return [(0.0, 0.0)]
    golden_angle = math.pi * (3 - math.sqrt(5))
    pack_radius = max(0.0, partial_dot_cluster_radius(n, dot_radius) - dot_radius)
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
