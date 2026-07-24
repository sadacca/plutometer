"""
plutometer -- "How rich are the rich, really?"

Streamlit entrypoint. Click a spot on the map, pick a dollar amount, and see
the largest contiguous set of geographies (states / counties / neighborhoods)
whose combined residential real-estate value doesn't exceed it.
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
    GEO_LABELS,
    LEVEL_LABELS,
    LEVEL_ORDER,
    TRACT_MIN_ZOOM,
    fmt_dollar,
    fmt_full,
    fmt_num,
    parse_value,
)

st.set_page_config(
    page_title="How rich are the rich, really?",
    page_icon="\U0001F3E0",
    layout="wide",
    initial_sidebar_state="expanded",
)

store = load_store()

_STATE_DEFAULTS = {
    "marker": None,
    "map_center": DEFAULT_CENTER,
    "map_zoom": DEFAULT_ZOOM,
    "map_bbox": None,
    "last_clicked_processed": None,
    "result": None,
    "result_level": None,
    "result_national_median": 0.0,
    "result_national_houses": 0.0,
    "status": "Click the map to get started.",
}
for _k, _v in _STATE_DEFAULTS.items():
    st.session_state.setdefault(_k, _v)

# Apply any level change requested by the auto-cascade logic *before* the
# selectbox below is instantiated -- Streamlit forbids mutating a widget's
# session_state key after that widget has already rendered this run.
_pending_level = st.session_state.pop("pending_geo_level", None)
if _pending_level is not None:
    st.session_state["geo_level"] = _pending_level


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
        f"{fmt_num(result.num_selected)} {GEO_LABELS.get(level, level).lower()} = {fmt_dollar(result.total_value)}"
        if result.num_selected > 0
        else "No geographies fit -- try a larger amount or zoom in."
    )


def _parse_bounds(map_data: dict) -> tuple[float, float, float, float] | None:
    bounds = map_data.get("bounds")
    if not bounds:
        return None
    try:
        sw, ne = bounds["_southWest"], bounds["_northEast"]
        return (sw["lng"], sw["lat"], ne["lng"], ne["lat"])
    except (KeyError, TypeError):
        return None


# ---------------------------------------------------------------- sidebar: controls --

with st.sidebar:
    st.title("How rich are the rich, really?")
    st.caption("See wealth mapped onto real neighborhoods")

    available_levels = [lvl for lvl in LEVEL_ORDER if store.get_level(lvl) is not None]
    if not available_levels:
        st.error("No geography data found. Run `python scripts/prepare_data.py` first.")
        st.stop()

    st.session_state.setdefault("geo_level", available_levels[0])
    geo_level = st.selectbox(
        "Geography Level",
        options=available_levels,
        format_func=lambda lvl: LEVEL_LABELS.get(lvl, lvl),
        key="geo_level",
    )

    ref_options = {f"{r['name']} ({fmt_dollar(r['value'])})": r["value"] for r in store.reference_values}
    ref_choice = st.selectbox("Total Wealth", options=["-- Select --", *ref_options.keys()])
    custom_raw = st.text_input("Custom amount", placeholder="e.g. 500B or 1.5T")
    st.caption("Supports K, M, B, T (e.g. 500B = $500 billion)")

    custom_parsed = parse_value(custom_raw)
    target_value = custom_parsed if custom_parsed else ref_options.get(ref_choice)

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

# ------------------------------------------------------------------ main: map --

geo_data = store.get_level(st.session_state.geo_level)

render_gdf = None
if geo_data is not None:
    if st.session_state.geo_level == "tract":
        if st.session_state.map_zoom < TRACT_MIN_ZOOM:
            st.info(f"Zoom in to level {TRACT_MIN_ZOOM}+ to see neighborhood boundaries.")
        elif st.session_state.map_bbox is not None:
            render_gdf = geo_data.viewport_gdf(st.session_state.map_bbox)
    else:
        render_gdf = geo_data.full_gdf

selected_geoids = None
if st.session_state.result is not None and st.session_state.result_level == st.session_state.geo_level:
    selected_geoids = set(st.session_state.result.selected_geoids)

fmap = build_map(
    render_gdf=render_gdf,
    overlay_mode=overlay_mode,
    selected_geoids=selected_geoids,
    marker_latlon=st.session_state.marker,
    center=st.session_state.map_center,
    zoom=st.session_state.map_zoom,
)

map_data = st_folium(
    fmap,
    height=700,
    use_container_width=True,
    returned_objects=["last_clicked", "zoom", "bounds", "center"],
    key="plutometer_map",
)

if map_data:
    if map_data.get("zoom") is not None:
        st.session_state.map_zoom = map_data["zoom"]
    center = map_data.get("center")
    if center:
        st.session_state.map_center = (center["lat"], center["lng"])
    bbox = _parse_bounds(map_data)
    if bbox is not None:
        st.session_state.map_bbox = bbox

    clicked = map_data.get("last_clicked")
    if clicked:
        click_key = (round(clicked["lat"], 6), round(clicked["lng"], 6), target_value, st.session_state.geo_level)
        if click_key != st.session_state.last_clicked_processed:
            st.session_state.last_clicked_processed = click_key
            if not target_value:
                st.session_state.status = "Select or enter a total wealth amount."
            elif st.session_state.geo_level == "tract" and st.session_state.map_zoom < TRACT_MIN_ZOOM:
                st.session_state.status = f"Zoom in to level {TRACT_MIN_ZOOM}+ to use neighborhood mode."
            else:
                _run_computation(clicked["lat"], clicked["lng"], target_value, st.session_state.geo_level)
                st.rerun()

# ---------------------------------------------------------------- sidebar: results --

with st.sidebar:
    result = st.session_state.result
    if result is not None and result.num_selected > 0:
        st.markdown("#### How many houses could you buy?")
        st.metric("At local median price", f"{fmt_num(result.median_houses_to_target)} homes")
        st.caption(
            f"At national median price: {fmt_num(st.session_state.result_national_houses)} homes "
            f"({fmt_dollar(st.session_state.result_national_median)} ea.)"
        )
        geo_label = GEO_LABELS.get(st.session_state.result_level, "Geographies")
        st.markdown(f"**{geo_label}:** {fmt_num(result.num_selected)}")

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

    st.caption(st.session_state.status)
