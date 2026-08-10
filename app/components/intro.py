"""
Skippable animated intro carousel -- "how rich are the rich, really?" walked
through as a fixed sequence instead of a cold click-to-explore map, for a
visitor who wouldn't otherwise know what to click. See feature-requests.md
for the design discussion this implements (mechanism, anchor values, and
the deferred items -- timed auto-advance, free-text location search -- this
first pass doesn't attempt).

The map stays mounted and in the same page position through every step
(place/visual continuity was an explicit requirement) rather than being
swapped out for a graphic on the sub-house steps -- those steps just don't
attach a highlight layer to it, and lean on a text+icon card instead.
"""

import streamlit as st
from streamlit_folium import st_folium

from algorithm import expand_contiguous
from components.map_view import build_map
from components.utils import fmt_dollar, fmt_houses, fmt_num, fractional_headline, geo_label, house_icon_row

# Anchored to data/reference_values.csv's own SCF-sourced percentile rows
# (single source of truth -- stays in sync with any future refresh of that
# file) rather than duplicating separate constants here. 99.9th, not 99th,
# is the county anchor -- see feature-requests.md's "Percentile research"
# section for the order-of-magnitude reasoning. Fallback literals are the
# SCF 2022 / Fed Distributional Financial Accounts figures used to pick
# those rows, in case the CSV is ever edited and a name below goes stale.
WEALTH_STEPS = [
    {"id": "median", "name": "The median household", "ref_name": "Median US Household Net Worth", "fallback": 192_084},
    {
        "id": "block",
        "name": "The richest household on the block",
        "ref_name": "90th Percentile Household Net Worth",
        "fallback": 1_920_758,
    },
    {
        "id": "county",
        "name": "The richest household in the county",
        "ref_name": "99.9th Percentile Household Net Worth",
        "fallback": 46_369_052,
    },
]

# These two steps run the real expand_contiguous algorithm (like a normal click on the
# main map) instead of just dividing by the local median home price -- their target
# values are large enough to actually claim contiguous geography, not just a handful
# of houses, so they get a real highlight layer rather than the icon-row treatment.
# "Billionaire" bridges the huge gap between a top-0.1%-household fortune (~$46M-$62M,
# doesn't clear a single census tract most places) and an actual mega-billionaire's
# (~$700B+, several whole states) -- without it, that jump was the single biggest and
# least-illustrated step in the whole carousel.
GEO_STEPS = [
    {
        "id": "billionaire",
        "name": "A local billionaire",
        "ref_name": "A $1 Billion Fortune ('just' a billionaire)",
        "fallback": 1_000_000_000,
        "level": "tract",
    },
    {"id": "country", "name": "The richest person in the country", "ref_name": None, "fallback": None, "level": "state"},
]

STEP_IDS = ["framing"] + [s["id"] for s in WEALTH_STEPS] + [s["id"] for s in GEO_STEPS]

# Zoom pulls back a notch each step -- house-level detail for the small figures, out to
# tract-cluster scale for the billionaire step, out again to a full national view once
# the country step needs to show multiple contiguous states.
STEP_ZOOM = {"framing": 12, "median": 15, "block": 14, "county": 12, "billionaire": 13, "country": 5}

# Curated replay list rather than free-text city search -- the app has no
# name-to-location index today (see feature-requests.md); this is the cheap
# version of "replay somewhere else." Pittsburgh is the default: a legible,
# mid-size, non-coastal metro that doesn't read oddly against a *national*
# median figure the way one of the most expensive markets would.
INTRO_LOCATIONS = {
    "Pittsburgh, PA": (40.4406, -79.9959),
    "Cleveland, OH": (41.4993, -81.6944),
    "Kansas City, MO": (39.0997, -94.5786),
    "Columbus, OH": (39.9612, -82.9988),
    "Atlanta, GA": (33.7490, -84.3880),
    "Denver, CO": (39.7392, -104.9903),
    "Austin, TX": (30.2672, -97.7431),
    "Seattle, WA": (47.6062, -122.3321),
    "Boston, MA": (42.3601, -71.0589),
    "San Francisco, CA": (37.7749, -122.4194),
    "New York, NY": (40.7128, -74.0060),
    "Los Angeles, CA": (34.0522, -118.2437),
    "Miami, FL": (25.7617, -80.1918),
}
DEFAULT_INTRO_LOCATION = "Pittsburgh, PA"


def should_show_intro() -> bool:
    """True on a visitor's first script run this session, or after they hit Replay --
    session-only (Streamlit has no durable per-visitor storage), so a page refresh
    shows it again. That's an accepted trade-off, not a bug -- see feature-requests.md.
    """
    st.session_state.setdefault("intro_seen", False)
    st.session_state.setdefault("intro_active", not st.session_state.intro_seen)
    return st.session_state.intro_active


def start_intro() -> None:
    st.session_state.intro_active = True
    st.session_state.intro_step = 0


def _end_intro() -> None:
    st.session_state.intro_active = False
    st.session_state.intro_seen = True


def _card_html(headline: str, caption: str, extra: str = "") -> str:
    extra_html = f'<div style="margin-top:8px;">{extra}</div>' if extra else ""
    return (
        f'<div class="pm-stat-card"><div class="pm-stat-headline">{headline}</div>'
        f'<div class="pm-stat-caption">{caption}</div>{extra_html}</div>'
    )


def _local_median_home_value(store, lat: float, lon: float) -> float:
    """Finest-available local median home price at this point -- tract if loaded
    (most locally accurate), county otherwise, national median as a last resort.
    """
    for level in ("tract", "county"):
        geo_data = store.get_level(level)
        if geo_data is not None and geo_data.centroids:
            geoid = geo_data.nearest_geoid(lat, lon)
            mhv = geo_data.enrichment.get(geoid, {}).get("median_home_value", 0)
            if mhv > 0:
                return mhv
    return store.national_median_home_value


def _ref_value(store, ref_name: str, fallback: float) -> float:
    """A named row's value from reference_values.csv, or fallback if that row is missing
    (e.g. the CSV was edited and the name changed) -- keeps the intro's anchors in sync
    with the CSV's hand-maintained figures instead of duplicating separate constants.
    """
    for r in store.reference_values:
        if r.get("name") == ref_name:
            return r["value"]
    return fallback


def _pick_country_value(store) -> tuple[float, str]:
    """The richest-individual reference value to aim for in the final step -- the max
    of the "Super-Rich Individuals" category (falls back to the max of everything if
    that category is missing), so this tracks reference_values.csv's hand-maintained
    figures instead of hardcoding a net worth that goes stale the next time a
    billionaire's fortune moves. r["name"] already reads e.g. "Elon Musk Net Worth" --
    no " Net Worth" suffix added here, matching how app.py builds the same labels.
    """
    pool = [r for r in store.reference_values if r.get("category") == "Super-Rich Individuals"]
    pool = pool or store.reference_values
    if not pool:
        return 0.0, "the wealthiest person"
    best = max(pool, key=lambda r: r["value"])
    return best["value"], f"{best['name']} ({fmt_dollar(best['value'])})"


def _compute_geo_step(store, level: str, target_value: float, lat: float, lon: float):
    """Real expand_contiguous run at the given level -- same call app.py's own
    _run_computation makes for an actual map click. Used by the two steps whose
    target value is large enough to claim real contiguous geography (billionaire,
    country) rather than just a handful of houses.
    """
    geo_data = store.get_level(level)
    if geo_data is None or not geo_data.centroids:
        return None
    start_geoid = geo_data.nearest_geoid(lat, lon)
    return expand_contiguous(
        start_geoid=start_geoid,
        target_value=target_value,
        values=geo_data.values,
        adjacency=geo_data.adjacency,
        centroids=geo_data.centroids,
        mapspot_lon=lon,
        mapspot_lat=lat,
        enrichment=geo_data.enrichment,
    )


def _tract_render_bbox(tract_data, geoids, marker_latlon: tuple[float, float], pad: float = 0.08):
    """Bbox around the selected tracts' centroids (or just the marker, before any are
    selected), padded for context. A fixed-padding cousin of app.py's own
    _selection_bbox -- simplified because the intro uses one fixed zoom per step
    instead of tracking live pan/zoom.
    """
    lons: list[float] = []
    lats: list[float] = []
    for g in geoids or []:
        c = tract_data.centroids.get(g)
        if c:
            lons.append(c[0])
            lats.append(c[1])
    if not lons and marker_latlon:
        lat, lon = marker_latlon
        lons, lats = [lon], [lat]
    if not lons:
        return None
    return (min(lons) - pad, min(lats) - pad, max(lons) + pad, max(lats) + pad)


def _render_framing_step() -> None:
    st.markdown(
        _card_html(
            "What if you spent every dollar on a house?",
            "<strong>The normal rule:</strong> about 30% of your income goes to rent or a "
            "mortgage. Sensible. Forgettable."
            "<br><br>"
            "<strong>The question this tool actually asks:</strong> what if every dollar "
            "you had -- not just your paycheck, <em>everything</em> -- went into real "
            "estate instead? No savings, no retirement account, just houses. Let's see how "
            "far that gets you.",
        ),
        unsafe_allow_html=True,
    )


def _render_fractional_step(step: dict, value: float, houses: float, local_median: float) -> None:
    headline = f"{step['name']} ({fmt_dollar(value)}): {fractional_headline('tract', houses)}"
    caption = (
        f"Every dollar of net worth into real estate here ≈ <strong>{fmt_houses(houses)}</strong> "
        f"homes at this location's median price ({fmt_dollar(local_median)})."
    )
    st.markdown(_card_html(headline, caption, extra=house_icon_row(houses)), unsafe_allow_html=True)


def _render_geo_result(target_label: str, level: str, result, national_median: float) -> bool:
    """Renders the real-highlight result card. Returns False (renders nothing) when the
    starting geography alone already exceeds the target -- the caller falls back to the
    fractional/icon-row card in that case, same as the smaller tiers use.
    """
    if result is None or result.num_selected == 0:
        return False
    label = geo_label(level, result.num_selected)
    headline = f"{target_label} ≈ {fmt_num(result.num_selected)} {label}"
    national_houses = result.target_value / national_median if national_median > 0 else 0.0
    caption = (
        f"≈ <strong>{fmt_houses(result.median_houses_to_target)}</strong> homes at local median price"
        f" · <strong>{fmt_houses(national_houses)}</strong> at national median ({fmt_dollar(national_median)})"
    )
    st.markdown(_card_html(headline, caption), unsafe_allow_html=True)
    return True


def _render_controls() -> None:
    total = len(STEP_IDS)
    step_idx = st.session_state.intro_step
    is_last = step_idx == total - 1

    b1, b2, b3 = st.columns([1, 2, 1])
    with b1:
        if st.button("← Back", disabled=step_idx == 0, use_container_width=True, key="intro_back"):
            st.session_state.intro_step -= 1
            st.rerun()
    with b2:
        st.selectbox(
            "Replay somewhere else",
            options=list(INTRO_LOCATIONS.keys()),
            key="intro_location",
            label_visibility="collapsed",
        )
    with b3:
        label = "Explore the map →" if is_last else "Next →"
        if st.button(label, use_container_width=True, key="intro_next", type="primary"):
            if is_last:
                _end_intro()
            else:
                st.session_state.intro_step += 1
            st.rerun()


def render_intro(store) -> None:
    st.session_state.setdefault("intro_step", 0)
    st.session_state.setdefault("intro_location", DEFAULT_INTRO_LOCATION)

    step_idx = st.session_state.intro_step
    step_id = STEP_IDS[step_idx]
    lat, lon = INTRO_LOCATIONS[st.session_state.intro_location]

    st.markdown("##### \U0001F3E0 How rich are the rich, really?")

    top_l, top_r = st.columns([3, 1])
    with top_l:
        st.caption(f"Intro · step {step_idx + 1} of {len(STEP_IDS)} · \U0001F4CD {st.session_state.intro_location}")
    with top_r:
        if st.button("Skip intro →", use_container_width=True, key="intro_skip"):
            _end_intro()
            st.rerun()

    render_gdf = None
    selected_geoids = None
    national_median = store.national_median_home_value

    if step_id == "framing":
        _render_framing_step()

    elif step_id == "billionaire":
        step = next(s for s in GEO_STEPS if s["id"] == "billionaire")
        value = _ref_value(store, step["ref_name"], step["fallback"])
        target_label = f"{step['name']} ({fmt_dollar(value)})"
        result = _compute_geo_step(store, "tract", value, lat, lon)
        tract_data = store.get_level("tract")
        shown = False
        if result is not None and result.num_selected > 0 and tract_data is not None:
            bbox = _tract_render_bbox(tract_data, result.selected_geoids, (lat, lon))
            if bbox is not None:
                render_gdf = tract_data.viewport_gdf(bbox)
                selected_geoids = set(result.selected_geoids)
                shown = _render_geo_result(target_label, "tract", result, national_median)
        if not shown:
            # Even a billionaire's fortune doesn't clear a single census tract in the
            # priciest markets -- that's still a real, worthwhile result, so fall back
            # to the same fractional/icon-row treatment the smaller tiers use rather
            # than a dead end.
            local_median = _local_median_home_value(store, lat, lon)
            houses = value / local_median if local_median > 0 else 0.0
            _render_fractional_step(step, value, houses, local_median)

    elif step_id == "country":
        value, target_label = _pick_country_value(store)
        result = _compute_geo_step(store, "state", value, lat, lon)
        if result is not None and result.num_selected > 0:
            state_data = store.get_level("state")
            render_gdf = state_data.full_gdf
            selected_geoids = set(result.selected_geoids)
            _render_geo_result(target_label, "state", result, national_median)
        else:
            st.markdown(
                _card_html(target_label, "Couldn't compute a result for this location."), unsafe_allow_html=True
            )

    else:
        step = next(s for s in WEALTH_STEPS if s["id"] == step_id)
        value = _ref_value(store, step["ref_name"], step["fallback"])
        local_median = _local_median_home_value(store, lat, lon)
        houses = value / local_median if local_median > 0 else 0.0
        _render_fractional_step(step, value, houses, local_median)

    fmap = build_map(
        render_gdf=render_gdf,
        overlay_mode="none",
        selected_geoids=selected_geoids,
        marker_latlon=(lat, lon),
        center=(lat, lon),
        zoom=STEP_ZOOM[step_id],
        render_key=("intro", step_id, st.session_state.intro_location),
    )
    st_folium(fmap, height=420, use_container_width=True, returned_objects=[], key="plutometer_intro_map")

    _render_controls()
