"""
plutometer -- "How rich are the rich, really?"

Streamlit entrypoint. Click a spot on the map, pick a dollar amount, and see
the largest contiguous set of geographies (states / counties / neighborhoods)
whose combined residential real-estate value doesn't exceed it.

Mobile-first layout: the sidebar is collapsed by default and holds only
secondary settings (overlay mode, clear button, detail expanders). The
header, the map, the core controls (geography level, target value), and the
primary "how many houses" result all live in the main column, map first, so
the whole click-to-see-result loop never requires opening the sidebar.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import streamlit as st
from streamlit_folium import st_folium

from algorithm import expand_contiguous, find_nearest_geoid
from data_loader import load_store
from components.map_view import DEFAULT_CENTER, DEFAULT_ZOOM, build_map
from components.utils import (
    LEVEL_LABELS,
    LEVEL_ORDER,
    TRACT_MIN_ZOOM,
    fmt_dollar,
    fmt_full,
    fmt_houses,
    fmt_num,
    fractional_headline,
    geo_label,
    parse_value,
)

st.set_page_config(
    page_title="How rich are the rich, really?",
    page_icon="\U0001F3E0",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Translucent accent tints (not solid colors) so these read correctly against
# both Streamlit's light and dark palettes -- see the comment in
# .streamlit/config.toml on why backgroundColor/textColor are left unset.
# Text color is never set explicitly; it inherits Streamlit's own themed
# color. The map iframe is targeted by its component title attribute
# (stable across reruns -- streamlit-folium always names it this) rather
# than a generated class, since Streamlit doesn't expose a way to attach a
# custom class to a component's own wrapper.
st.markdown(
    """
    <style>
    @keyframes pm-fade-in {
      0%   { opacity: 0; transform: translateY(4px) scale(0.98); }
      100% { opacity: 1; transform: translateY(0) scale(1); }
    }
    .pm-stat-card {
      background: rgba(245, 124, 0, 0.08);
      border: 1px solid rgba(245, 124, 0, 0.35);
      border-radius: 10px;
      padding: 14px 18px;
      margin: 4px 0 10px 0;
      animation: pm-fade-in 0.35s ease-out;
    }
    .pm-stat-headline {
      font-size: 1.4rem;
      font-weight: 700;
      line-height: 1.3;
      margin: 0 0 4px 0;
    }
    .pm-stat-caption {
      font-size: 0.85rem;
      opacity: 0.75;
      line-height: 1.4;
    }
    .pm-empty-banner {
      background: rgba(245, 124, 0, 0.05);
      border: 1.5px dashed rgba(245, 124, 0, 0.4);
      border-radius: 10px;
      padding: 10px 16px;
      margin: 4px 0 10px 0;
      font-size: 0.92rem;
      opacity: 0.85;
    }
    iframe[title="streamlit_folium.st_folium"] {
      border-radius: 12px;
      overflow: hidden;
      box-shadow: 0 2px 14px rgba(0, 0, 0, 0.14);
      border: 1px solid rgba(0, 0, 0, 0.06);
      /* streamlit-folium sets the iframe's real height itself once its JS
         finishes mounting -- this floor just stops the bordered/shadowed
         frame rendering as a broken sliver during that brief window. */
      min-height: 200px;
    }
    /* Streamlit's default top padding (~6rem) leaves ~36px of dead space beyond
       what's needed to clear its own fixed toolbar (measured ~60px tall) -- on
       a single mobile screen whose whole point is showing the map *and* the
       controls below it without scrolling, that's space worth reclaiming.
       Scoped to the main column (not the sidebar) so its own spacing is
       untouched. 4.5rem keeps a small buffer under the toolbar. */
    [data-testid="stMainBlockContainer"] {
      padding-top: 4.5rem;
    }
    [data-testid="stMainBlockContainer"] [data-testid="stVerticalBlock"] {
      gap: 0.5rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

store = load_store()

_STATE_DEFAULTS = {
    "marker": None,
    "map_zoom": DEFAULT_ZOOM,
    "map_center": DEFAULT_CENTER,
    "last_clicked_processed": None,
    "result": None,
    "result_level": None,
    "result_national_median": 0.0,
    "result_national_houses": 0.0,
    "result_target_label": "",
    "status": "Tap the map to get started.",
}
for _k, _v in _STATE_DEFAULTS.items():
    st.session_state.setdefault(_k, _v)

# Apply any level change requested by the auto-cascade logic *before* the
# selectbox below is instantiated -- Streamlit forbids mutating a widget's
# session_state key after that widget has already rendered this run.
_pending_level = st.session_state.pop("pending_geo_level", None)
if _pending_level is not None:
    st.session_state["geo_level"] = _pending_level

available_levels = [lvl for lvl in LEVEL_ORDER if store.get_level(lvl) is not None]
if not available_levels:
    st.error("No geography data found. Run `python scripts/prepare_data.py` first.")
    st.stop()
st.session_state.setdefault("geo_level", available_levels[0])


def _stat_card_html(headline: str, caption: str) -> str:
    """The primary result, styled as a standalone card (see the injected .pm-stat-card
    CSS above) instead of a plain markdown header -- the actual payoff of the tool
    deserves more visual weight than the surrounding text. caption may contain simple
    <strong> tags; both args are always built from this module's own formatted numbers/
    labels, never raw user input, so interpolating them directly is safe here.
    """
    return f'<div class="pm-stat-card"><div class="pm-stat-headline">{headline}</div><div class="pm-stat-caption">{caption}</div></div>'


def _run_computation(
    lat: float, lon: float, target_value: float, level: str, target_label: str, depth: int = 0
) -> None:
    geo_data = store.get_level(level)
    if geo_data is None or not geo_data.centroids:
        st.session_state.status = f"No data loaded for {LEVEL_LABELS.get(level, level)} yet."
        return

    start_geoid = find_nearest_geoid(lat, lon, geo_data.centroids)
    result = expand_contiguous(
        start_geoid=start_geoid,
        target_value=target_value,
        values=geo_data.values,
        adjacency=geo_data.adjacency,
        centroids=geo_data.centroids,
        mapspot_lon=lon,
        mapspot_lat=lat,
        enrichment=geo_data.enrichment,
    )
    start_value = geo_data.values.get(start_geoid, 0)

    # Auto-level switch: the clicked geography alone already exceeds the target,
    # and a finer level with data is available -- cascade down to it.
    if result.num_selected == 0 and start_value > target_value and depth < len(LEVEL_ORDER):
        next_idx = LEVEL_ORDER.index(level) + 1
        next_level = LEVEL_ORDER[next_idx] if next_idx < len(LEVEL_ORDER) else None
        if next_level is not None and store.get_level(next_level) is not None:
            st.toast(
                f"That single {LEVEL_LABELS.get(level, level).lower()} exceeds "
                f"{fmt_dollar(target_value)}. Switching to {LEVEL_LABELS.get(next_level, next_level).lower()}s..."
            )
            st.session_state.pending_geo_level = next_level
            if next_level == "tract" and st.session_state.map_zoom < TRACT_MIN_ZOOM:
                st.session_state.map_zoom = TRACT_MIN_ZOOM
                st.toast("Zooming in to show neighborhood boundaries...")
            _run_computation(lat, lon, target_value, next_level, target_label, depth=depth + 1)
            return

    national_median = store.national_median_home_value
    national_houses = target_value / national_median if national_median > 0 else 0.0

    st.session_state.result = result
    st.session_state.result_level = level
    st.session_state.result_national_median = national_median
    st.session_state.result_national_houses = national_houses
    st.session_state.result_target_label = target_label
    st.session_state.marker = (lat, lon)
    st.session_state.status = (
        f"{fmt_num(result.num_selected)} {geo_label(level, result.num_selected)} = {fmt_dollar(result.total_value)}"
        if result.num_selected > 0
        else "No geographies fit -- try a larger amount or zoom in."
    )


TRACT_BBOX_FLOOR_PAD = 0.08  # degrees -- floor once zoomed in close (neighborhood-scale)
TRACT_BBOX_BASE_PAD = 1.0  # degrees -- pad right at TRACT_MIN_ZOOM, so the first tract
                            # view covers a decent-sized region instead of a tiny sliver
COUNTY_BBOX_FLOOR_PAD = 0.15  # degrees -- floor once zoomed in close
COUNTY_BBOX_BASE_PAD = 1.5  # degrees -- pad just past COUNTY_FULL_ZOOM_MAX
COUNTY_FULL_ZOOM_MAX = 6  # at/below this zoom, county is already fully in memory and
                           # cheap to render whole -- no need to clip to a bbox at all


def _zoom_scaled_pad(zoom: int, ref_zoom: int, ref_pad: float, floor_pad: float) -> float:
    """Bbox padding (degrees) that halves for each zoom level above ref_zoom and doubles
    for each below it, floored at floor_pad. Web Mercator halves degrees-per-pixel for
    every +1 zoom level, so this makes the render bbox roughly track what's actually
    visible on screen instead of a fixed constant -- too tight once zoomed out (missing
    context that's genuinely on screen) and unnecessarily wide once zoomed in (bloating
    the GeoJSON sent to the browser for no visible gain).
    """
    return max(floor_pad, ref_pad * (2 ** (ref_zoom - zoom)))


def _selection_bbox(geo_data, geoids, marker, pad: float) -> tuple[float, float, float, float] | None:
    """Bounding box covering the given geoids' centroids (padded for context),
    or a small box around the marker if there's no selection yet. Deliberately
    *not* derived from the map's live pan/zoom bounds -- watching those as an
    st_folium returned_object caused an endless rerun loop: each rerun rebuilds
    the folium.Map from scratch, and re-mounting it can report slightly
    different bounds than before (container-size timing, projection rounding),
    which registers as a real pan and triggers another rerun, which remounts
    again... a cascade that never settles. A bbox computed from data we already
    trust (selection centroids, or the click point) has no such feedback path.

    Used to clip both tract and county rendering to the area around the current
    selection -- tract because its geometry isn't held in memory at all, county
    because sending its 2MB+ nationwide GeoJSON on every rerun (typing in the
    amount box, toggling the overlay radio, not just panning) is unnecessary
    once a selection narrows down where on the map actually matters. Before any
    selection exists, callers fall back to the level's full/national extent.
    """
    lons: list[float] = []
    lats: list[float] = []
    for g in geoids or []:
        c = geo_data.centroids.get(g)
        if c:
            lons.append(c[0])
            lats.append(c[1])
    if not lons and marker:
        lat, lon = marker
        lons, lats = [lon], [lat]
    if not lons:
        return None
    return (min(lons) - pad, min(lats) - pad, max(lons) + pad, max(lats) + pad)


# ---------------------------------------------------------------- sidebar: secondary --
# Collapsed by default (see set_page_config). The core loop -- header, map,
# level/amount controls, and the primary result -- all lives in the main
# column below, so the sidebar is only needed for the overlay toggle or to
# dig into secondary detail.

with st.sidebar:
    st.markdown("##### ⚙️ More options")

    overlay_mode = st.radio(
        "Map overlay",
        options=["median_price", "total_value", "none"],
        format_func=lambda m: {"median_price": "Median Home Price", "total_value": "Total Value", "none": "No Fill"}[m],
        key="overlay_mode",
    )

    if st.button("Clear Selection", disabled=st.session_state.marker is None, use_container_width=True):
        st.session_state.marker = None
        st.session_state.map_center = DEFAULT_CENTER
        st.session_state.result = None
        st.session_state.last_clicked_processed = None
        st.session_state.status = "Selection cleared."
        st.rerun()

    result = st.session_state.result
    if result is not None and result.num_selected > 0:
        with st.expander("Selection details"):
            # Named places, not just a count -- grounds the abstract number in
            # the same real geographies the map is highlighting.
            result_geo_data = store.get_level(st.session_state.result_level)
            if result_geo_data is not None:
                names = [result_geo_data.names.get(g, g) for g in result.selected_geoids]
                shown = ", ".join(names[:10])
                if len(names) > 10:
                    shown += f", and {len(names) - 10} more"
                st.write(f"Includes: {shown}")
            st.write(f"Total value of area: {fmt_full(result.total_value)}")
            st.write(f"Total wealth compared: {fmt_full(result.target_value)}")
            st.write(f"Remaining: {fmt_full(result.remaining_budget)}")
            st.write(f"Furthest distance: {result.furthest_distance_km:.1f} km")

        with st.expander("Area statistics"):
            st.write(f"Median household income: {fmt_full(result.area_median_income)}")
            st.write(f"Median home value: {fmt_full(result.area_median_home_value)}")
            st.write(f"Total housing units: {fmt_num(result.area_total_housing_units)}")

    about_tab, scale_tab = st.tabs(["About this tool", "What does a dollar buy?"])
    with about_tab:
        st.markdown(store.educational_content or "_No educational content found._")
    with scale_tab:
        st.markdown(store.scale_reference_content or "_No content found._")

# ------------------------------------------------------------------ main: header + map --
# Informative text (title + result) stays compact above the map; interactive
# controls live below it. The result, when present, is the actual payoff of
# the tool, so it gets two lines -- a bold headline naming what's being
# compared (the target label + value picked below, e.g. "Elon Musk Net Worth
# ($1.1T)") against what it bought, then a caption with the "how many houses"
# context below it -- rather than one dense run-on line that buries the
# numbers, or a headline that shows the resulting area's value without ever
# saying what it was being measured against.

st.markdown("##### \U0001F3E0 How rich are the rich, really?")

result = st.session_state.result
target_label = st.session_state.result_target_label
if result is not None and result.num_selected > 0:
    label = geo_label(st.session_state.result_level, result.num_selected)
    headline = f"{target_label} ≈ {fmt_num(result.num_selected)} {label}"
    caption = (
        f"≈ <strong>{fmt_houses(result.median_houses_to_target)}</strong> homes at local median price"
        f" · <strong>{fmt_houses(st.session_state.result_national_houses)}</strong> at national median"
        f" ({fmt_dollar(st.session_state.result_national_median)})"
    )
    st.markdown(_stat_card_html(headline, caption), unsafe_allow_html=True)
elif result is not None and result.area_median_home_value > 0:
    # Target undercuts even the single smallest geography at the finest level
    # reached (num_selected == 0) -- expand_contiguous still returns that
    # geography's own median home value in this case (see its start_val >
    # target_value short-circuit), so "how many houses could this buy" still
    # has a real, if fractional, answer instead of a dead-end message.
    # fractional_headline tiers the wording by actual house count -- a flat
    # "smaller than a whole neighborhood" reads the same whether the money
    # buys 3 houses or 300, since a tract can hold hundreds to thousands.
    # Still led by target_label so this stays consistent with the
    # num_selected > 0 branch above -- the reader always sees what dollar
    # figure produced the result, not just what it bought.
    headline = f"{target_label}: {fractional_headline(st.session_state.result_level, result.median_houses_to_target)}"
    caption = (
        f"≈ <strong>{fmt_houses(result.median_houses_to_target)}</strong> homes at local median price"
        f" ({fmt_dollar(result.area_median_home_value)})"
        f" · <strong>{fmt_houses(st.session_state.result_national_houses)}</strong> at national median"
        f" ({fmt_dollar(st.session_state.result_national_median)})"
    )
    st.markdown(_stat_card_html(headline, caption), unsafe_allow_html=True)
else:
    st.markdown(f'<div class="pm-empty-banner">{st.session_state.status}</div>', unsafe_allow_html=True)

if st.session_state.marker is not None:
    # A one-line "where am I" anchor -- most useful at tract zoom, where the
    # visible map area is a tiny sliver with no broader context on screen.
    # County NAME already includes the state (e.g. "Alameda County,
    # California"), so a single nearest-county lookup is enough; this is
    # independent of the currently selected geo_level so it still works
    # while viewing state- or tract-level results.
    county_data = store.get_level("county")
    if county_data is not None and county_data.centroids:
        lat, lon = st.session_state.marker
        nearest_county = find_nearest_geoid(lat, lon, county_data.centroids)
        county_name = county_data.names.get(nearest_county)
        if county_name:
            st.caption(f"\U0001F4CD Viewing: {county_name}")

st.caption("Based on 2017–2021 Census estimates — order-of-magnitude, not exact.")

geo_data = store.get_level(st.session_state.geo_level)

selected_geoids = None
if st.session_state.result is not None and st.session_state.result_level == st.session_state.geo_level:
    selected_geoids = set(st.session_state.result.selected_geoids)

render_gdf = None
render_bbox = None
if geo_data is not None:
    if st.session_state.geo_level == "tract":
        if st.session_state.map_zoom < TRACT_MIN_ZOOM:
            st.info(f"Zoom in to level {TRACT_MIN_ZOOM}+ to see neighborhood boundaries.")
        else:
            pad = _zoom_scaled_pad(
                st.session_state.map_zoom, TRACT_MIN_ZOOM, TRACT_BBOX_BASE_PAD, TRACT_BBOX_FLOOR_PAD
            )
            render_bbox = _selection_bbox(geo_data, selected_geoids, st.session_state.marker, pad=pad)
            if render_bbox is not None:
                render_gdf = geo_data.viewport_gdf(render_bbox)
            else:
                st.caption("Tap the map to load neighborhood boundaries there.")
    elif st.session_state.geo_level == "county":
        if st.session_state.map_zoom <= COUNTY_FULL_ZOOM_MAX:
            # Zoomed out to (near) a national view -- county is already fully in memory
            # and cheap to render whole, so show every county instead of clipping to a
            # bbox that would cut off most of the country.
            render_gdf = geo_data.full_gdf
        else:
            pad = _zoom_scaled_pad(
                st.session_state.map_zoom, COUNTY_FULL_ZOOM_MAX + 1, COUNTY_BBOX_BASE_PAD, COUNTY_BBOX_FLOOR_PAD
            )
            render_bbox = _selection_bbox(geo_data, selected_geoids, st.session_state.marker, pad=pad)
            render_gdf = geo_data.viewport_gdf(render_bbox) if render_bbox is not None else geo_data.full_gdf
    else:
        render_gdf = geo_data.full_gdf

fmap = build_map(
    render_gdf=render_gdf,
    overlay_mode=overlay_mode,
    selected_geoids=selected_geoids,
    marker_latlon=st.session_state.marker,
    center=st.session_state.map_center,
    zoom=st.session_state.map_zoom,
    render_key=(st.session_state.geo_level, render_bbox),
)

# Only ever watch "last_clicked" and "zoom". Streamlit reruns the whole
# script whenever a watched value changes, and both "center" and "bounds"
# turned out to be unsafe to watch: rebuilding the folium.Map from scratch
# every rerun and re-mounting it can report a slightly different position/
# viewport than before (container-size timing, projection rounding), which
# registers as a real pan and triggers another rerun -- a cascade that never
# settles (see _tract_render_bbox for how tract geometry avoids needing
# "bounds" at all). zoom is a plain integer with no such jitter risk, and is
# needed for the tract auto-zoom banner regardless of the current level.
map_data = st_folium(
    fmap,
    height=560,
    use_container_width=True,
    returned_objects=["last_clicked", "zoom"],
    key="plutometer_map",
)

# ----------------------------------------------------------- main: controls --
# Interactive controls below the map (not above, not in the sidebar) so the
# map is the first thing seen on a vertical/mobile screen. One row, three
# columns -- auto-stacks to full width on narrow viewports -- to keep this
# section as short as the result line above the map.

c1, c2, c3 = st.columns(3)
with c1:
    geo_level = st.selectbox(
        "Geography Level",
        options=available_levels,
        format_func=lambda lvl: LEVEL_LABELS.get(lvl, lvl),
        key="geo_level",
        help=(
            "State and County cover the whole country at any zoom. "
            f"Neighborhood (Census tract) needs the map zoomed to level {TRACT_MIN_ZOOM}+ first."
        ),
    )
with c2:
    # Categories preserve reference_values.csv's row order (dict.fromkeys
    # dedupes while keeping first-seen order) rather than sorting
    # alphabetically, so related categories stay grouped the way the CSV
    # author intended (percentiles first, national-scale figures last).
    categories = list(dict.fromkeys(r["category"] for r in store.reference_values))
    default_category = "Super-Rich Individuals"
    category_index = categories.index(default_category) if default_category in categories else 0
    wealth_category = st.selectbox(
        "Wealth Category",
        options=categories,
        index=category_index,
        key="wealth_category",
        help="Pick a theme, then a specific amount within it below.",
    )

    filtered = [r for r in store.reference_values if r["category"] == wealth_category]
    ref_options = {f"{r['name']} ({fmt_dollar(r['value'])})": r["value"] for r in filtered}
    ref_labels = list(ref_options.keys())
    # Default to Elon Musk's net worth so there's always a result to look at
    # on first load, instead of a blank "-- Select --" state.
    default_label = next((label for label in ref_labels if label.startswith("Elon Musk")), ref_labels[0])
    # Keying on the category makes this a fresh widget whenever the category
    # changes, so its selection can't get stuck pointing at an index/value
    # that belonged to the previous category's option list.
    ref_choice = st.selectbox(
        "Amount", options=ref_labels, index=ref_labels.index(default_label), key=f"wealth_amount_{wealth_category}"
    )
with c3:
    custom_raw = st.text_input(
        "Custom amount",
        placeholder="e.g. 500B or 1.5T",
        help="Overrides the dropdown above. Accepts K/M/B/T shorthand, e.g. 500B or 1.5T.",
    )
    custom_parsed = parse_value(custom_raw)
    if custom_raw and custom_parsed is None:
        st.caption("Couldn't read that — try formats like 500B or 1.5T")

if custom_parsed:
    target_value = custom_parsed
    target_label = f"Custom amount ({fmt_dollar(target_value)})"
else:
    target_value = ref_options.get(ref_choice)
    target_label = ref_choice

if map_data:
    if map_data.get("zoom") is not None:
        st.session_state.map_zoom = map_data["zoom"]

    clicked = map_data.get("last_clicked")
    if clicked:
        click_key = (round(clicked["lat"], 6), round(clicked["lng"], 6), target_value, st.session_state.geo_level)
        if click_key != st.session_state.last_clicked_processed:
            st.session_state.last_clicked_processed = click_key
            # Recenter the *next* rebuilt map on the click itself, not just on a
            # successful computation's marker -- otherwise a click made before
            # the map is zoomed to TRACT_MIN_ZOOM (which can't run a computation
            # yet, see the tract-zoom branch below) leaves the map's location
            # pinned at DEFAULT_CENTER while the user tries to scroll-zoom in.
            # Since "zoom" is a watched returned_object, every zoom tick reruns
            # the script and rebuilds the folium.Map from scratch at whatever
            # center/zoom we hand it -- so without this, each zoom step snaps
            # the view back to the geographic center of the US instead of
            # staying put over the spot the user actually clicked.
            st.session_state.map_center = (clicked["lat"], clicked["lng"])
            if not target_value:
                st.session_state.status = "Select or enter a total wealth amount below."
            elif st.session_state.geo_level == "tract" and st.session_state.map_zoom < TRACT_MIN_ZOOM:
                st.session_state.status = f"Zoom in to level {TRACT_MIN_ZOOM}+ to use neighborhood mode."
            else:
                with st.spinner("Finding the largest area that fits..."):
                    _run_computation(
                        clicked["lat"], clicked["lng"], target_value, st.session_state.geo_level, target_label
                    )
                st.rerun()
