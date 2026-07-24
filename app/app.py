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
from components.map_view import DEFAULT_ZOOM, build_map
from components.utils import (
    LEVEL_LABELS,
    LEVEL_ORDER,
    TRACT_MIN_ZOOM,
    fmt_dollar,
    fmt_full,
    fmt_houses,
    fmt_num,
    geo_label,
    parse_value,
)

st.set_page_config(
    page_title="How rich are the rich, really?",
    page_icon="\U0001F3E0",
    layout="wide",
    initial_sidebar_state="collapsed",
)

store = load_store()

_STATE_DEFAULTS = {
    "marker": None,
    "map_zoom": DEFAULT_ZOOM,
    "last_clicked_processed": None,
    "result": None,
    "result_level": None,
    "result_national_median": 0.0,
    "result_national_houses": 0.0,
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


def _run_computation(lat: float, lon: float, target_value: float, level: str, depth: int = 0) -> None:
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
            _run_computation(lat, lon, target_value, next_level, depth=depth + 1)
            return

    national_median = store.national_median_home_value
    national_houses = target_value / national_median if national_median > 0 else 0.0

    st.session_state.result = result
    st.session_state.result_level = level
    st.session_state.result_national_median = national_median
    st.session_state.result_national_houses = national_houses
    st.session_state.marker = (lat, lon)
    st.session_state.status = (
        f"{fmt_num(result.num_selected)} {geo_label(level, result.num_selected)} = {fmt_dollar(result.total_value)}"
        if result.num_selected > 0
        else "No geographies fit -- try a larger amount or zoom in."
    )


TRACT_BBOX_PAD = 0.08  # degrees -- tight, neighborhood-scale context
COUNTY_BBOX_PAD = 1.5  # degrees -- wider, so nearby counties stay visible for context


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
        st.session_state.result = None
        st.session_state.last_clicked_processed = None
        st.session_state.status = "Selection cleared."
        st.rerun()

    result = st.session_state.result
    if result is not None and result.num_selected > 0:
        with st.expander("Selection details"):
            st.write(f"Total value of area: {fmt_full(result.total_value)}")
            st.write(f"Total wealth compared: {fmt_full(result.target_value)}")
            st.write(f"Remaining: {fmt_full(result.remaining_budget)}")
            st.write(f"Furthest distance: {result.furthest_distance_km:.1f} km")

        with st.expander("Area statistics"):
            st.write(f"Median household income: {fmt_full(result.area_median_income)}")
            st.write(f"Median home value: {fmt_full(result.area_median_home_value)}")
            st.write(f"Total housing units: {fmt_num(result.area_total_housing_units)}")

    with st.expander("About this tool"):
        st.markdown(store.educational_content or "_No educational content found._")

# ------------------------------------------------------------------ main: header + map --
# Informative text (title + result) stays compact above the map; interactive
# controls live below it. The result, when present, is the actual payoff of
# the tool, so it gets two lines -- a bold headline equation sized above the
# app title, then a caption with the "how many houses" context below it --
# rather than one dense run-on line that buries the numbers.

st.markdown("##### \U0001F3E0 How rich are the rich, really?")

result = st.session_state.result
if result is not None and result.num_selected > 0:
    label = geo_label(st.session_state.result_level, result.num_selected)
    st.markdown(f"#### {fmt_num(result.num_selected)} {label} = {fmt_dollar(result.total_value)}")
    st.caption(
        f"≈ **{fmt_houses(result.median_houses_to_target)}** homes at local median price"
        f" · **{fmt_houses(st.session_state.result_national_houses)}** at national median"
        f" ({fmt_dollar(st.session_state.result_national_median)})"
    )
elif result is not None and result.area_median_home_value > 0:
    # Target undercuts even the single smallest geography at the finest level
    # reached (num_selected == 0) -- expand_contiguous still returns that
    # geography's own median home value in this case (see its start_val >
    # target_value short-circuit), so "how many houses could this buy" still
    # has a real, if fractional, answer instead of a dead-end message.
    label = geo_label(st.session_state.result_level, 1)
    st.markdown(f"#### Smaller than a single {label} here")
    st.caption(
        f"≈ **{fmt_houses(result.median_houses_to_target)}** homes at local median price"
        f" ({fmt_dollar(result.area_median_home_value)})"
        f" · **{fmt_houses(st.session_state.result_national_houses)}** at national median"
        f" ({fmt_dollar(st.session_state.result_national_median)})"
    )
else:
    st.caption(st.session_state.status)

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
            render_bbox = _selection_bbox(geo_data, selected_geoids, st.session_state.marker, pad=TRACT_BBOX_PAD)
            if render_bbox is not None:
                render_gdf = geo_data.viewport_gdf(render_bbox)
            else:
                st.caption("Tap the map to load neighborhood boundaries there.")
    elif st.session_state.geo_level == "county":
        render_bbox = _selection_bbox(geo_data, selected_geoids, st.session_state.marker, pad=COUNTY_BBOX_PAD)
        render_gdf = geo_data.viewport_gdf(render_bbox) if render_bbox is not None else geo_data.full_gdf
    else:
        render_gdf = geo_data.full_gdf

fmap = build_map(
    render_gdf=render_gdf,
    overlay_mode=overlay_mode,
    selected_geoids=selected_geoids,
    marker_latlon=st.session_state.marker,
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
    )
with c2:
    ref_options = {f"{r['name']} ({fmt_dollar(r['value'])})": r["value"] for r in store.reference_values}
    ref_labels = ["-- Select --", *ref_options.keys()]
    # Default to Elon Musk's net worth so there's always a result to look at
    # on first load, instead of a blank "-- Select --" state.
    default_label = next((label for label in ref_labels if label.startswith("Elon Musk")), ref_labels[0])
    ref_choice = st.selectbox("Total Wealth", options=ref_labels, index=ref_labels.index(default_label))
with c3:
    custom_raw = st.text_input("Custom amount", placeholder="e.g. 500B or 1.5T")

custom_parsed = parse_value(custom_raw)
target_value = custom_parsed if custom_parsed else ref_options.get(ref_choice)

if map_data:
    if map_data.get("zoom") is not None:
        st.session_state.map_zoom = map_data["zoom"]

    clicked = map_data.get("last_clicked")
    if clicked:
        click_key = (round(clicked["lat"], 6), round(clicked["lng"], 6), target_value, st.session_state.geo_level)
        if click_key != st.session_state.last_clicked_processed:
            st.session_state.last_clicked_processed = click_key
            if not target_value:
                st.session_state.status = "Select or enter a total wealth amount below."
            elif st.session_state.geo_level == "tract" and st.session_state.map_zoom < TRACT_MIN_ZOOM:
                st.session_state.status = f"Zoom in to level {TRACT_MIN_ZOOM}+ to use neighborhood mode."
            else:
                _run_computation(clicked["lat"], clicked["lng"], target_value, st.session_state.geo_level)
                st.rerun()
