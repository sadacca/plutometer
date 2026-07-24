"""Folium map builder for plutometer -- basemap, gradient overlay, and selection highlight."""

import json

import geopandas as gpd
import folium
import streamlit as st

from components.utils import HIGHLIGHT_BORDER, HIGHLIGHT_FILL, price_color

BASEMAP_URL = "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png"
BASEMAP_ATTR = "&copy; OpenStreetMap &copy; CARTO"
DEFAULT_CENTER = (39.8, -98.5)
DEFAULT_ZOOM = 4

_OVERLAY_FIELD = {"median_price": "median_home_value", "total_value": "total_value"}
_OVERLAY_LABEL = {"median_price": "Median Home Price", "total_value": "Total Residential Value"}


def build_map(
    render_gdf: gpd.GeoDataFrame | None,
    overlay_mode: str,
    selected_geoids: set[str] | None,
    marker_latlon: tuple[float, float] | None,
    center: tuple[float, float] = DEFAULT_CENTER,
    zoom: int = DEFAULT_ZOOM,
    render_key: tuple = (),
) -> folium.Map:
    """Build the map for the current render pass. render_gdf is already resolved by the
    caller to the right slice for the active level (full state/county gdf, or the current
    tract/county viewport) -- this module only draws it.

    render_key should uniquely identify render_gdf's content (e.g. (level, bbox)) so that
    reruns which don't change the map view (typing in a text box, toggling an unrelated
    control) can reuse the already-serialized/styled GeoJSON instead of re-walking every
    feature -- see _styled_geojson.
    """
    m = folium.Map(location=list(center), zoom_start=zoom, tiles=None)
    folium.TileLayer(tiles=BASEMAP_URL, attr=BASEMAP_ATTR, name="basemap", max_zoom=18).add_to(m)

    if render_gdf is not None and len(render_gdf) > 0:
        _add_gradient_layer(m, render_gdf, overlay_mode, render_key)
        if selected_geoids:
            _add_highlight_layer(m, render_gdf, selected_geoids)
        _add_legend(m, overlay_mode, has_selection=bool(selected_geoids))

    if marker_latlon is not None:
        # A plain folium.Marker() uses Leaflet's default raster pin icon,
        # whose image path often doesn't resolve inside the sandboxed iframe
        # streamlit-folium renders into -- it shows up as a broken-image
        # glyph instead of a pin. CircleMarker is pure SVG, no external image
        # asset at all, so it can't fail to load.
        folium.CircleMarker(
            location=list(marker_latlon),
            radius=7,
            color="#1A1A1A",
            weight=2,
            fill=True,
            fill_color="#FFFFFF",
            fill_opacity=1.0,
        ).add_to(m)

    return m


_RENDER_COLS = ["GEOID", "NAME", "total_value", "median_home_value", "median_income", "geometry"]


@st.cache_data(show_spinner=False, max_entries=64)
def _styled_geojson(_gdf: gpd.GeoDataFrame, overlay_mode: str, render_key: tuple) -> dict:
    """GeoJSON with each feature's fill style precomputed and stashed in its properties.

    Keyed on render_key (e.g. (level, bbox)) rather than on _gdf itself (leading underscore
    excludes it from Streamlit's cache hash -- GeoDataFrames aren't cheaply hashable). Reruns
    that don't change the map view -- typing in the amount box, toggling the geo-level
    selectbox before it's actually changed, etc. -- hit this cache and skip re-serializing
    geometry to GeoJSON and recomputing colors for every feature, which is the expensive part
    of a map rebuild for county/tract-sized feature counts.
    """
    cols = [c for c in _RENDER_COLS if c in _gdf.columns]
    geojson = json.loads(_gdf[cols].to_json())

    if overlay_mode == "none":
        for feat in geojson["features"]:
            feat["properties"]["_style"] = {"color": "#9AA5B1", "weight": 0.6, "fillOpacity": 0}
        return geojson

    field = _OVERLAY_FIELD[overlay_mode]
    vals = [f["properties"].get(field) for f in geojson["features"]]
    vals = [v for v in vals if v and v > 0]
    vmin, vmax = (min(vals), max(vals)) if vals else (0.0, 0.0)
    for feat in geojson["features"]:
        v = feat["properties"].get(field) or 0
        fill = price_color(v, vmin, vmax) if v > 0 else "#f0f0f0"
        # Thin, near-invisible borders so filled regions read as a smooth
        # choropleth instead of a grid of outlined boxes -- the fill color
        # differences alone carry the shape boundaries.
        feat["properties"]["_style"] = {
            "color": "#ffffff", "weight": 0.4, "opacity": 0.5, "fillColor": fill, "fillOpacity": 0.6,
        }
    return geojson


def _add_gradient_layer(m: folium.Map, gdf: gpd.GeoDataFrame, overlay_mode: str, render_key: tuple) -> None:
    geojson = _styled_geojson(gdf, overlay_mode, render_key)

    # No hover tooltip: on touch devices a tap first triggers hover/tooltip
    # rather than the click handler, so every selection would need a double
    # tap. Full detail is already available in the results panel after a
    # click -- a hover-only affordance isn't worth that mobile friction.
    folium.GeoJson(
        geojson,
        name="gradient",
        style_function=lambda feature: feature["properties"]["_style"],
    ).add_to(m)


def _add_highlight_layer(m: folium.Map, gdf: gpd.GeoDataFrame, selected_geoids: set[str]) -> None:
    sub = gdf[gdf["GEOID"].isin(selected_geoids)]
    if len(sub) == 0:
        return

    def style_function(_feature):
        return {"color": HIGHLIGHT_BORDER, "weight": 2, "fillColor": HIGHLIGHT_FILL, "fillOpacity": 0.55}

    folium.GeoJson(sub[["GEOID", "geometry"]], name="highlight", style_function=style_function).add_to(m)


def _add_legend(m: folium.Map, overlay_mode: str, has_selection: bool) -> None:
    """Price-gradient key, a "your selection" color key, or both -- whichever apply. Skips
    entirely if there's nothing to explain (no fill and no selection), rather than always
    reserving map space for an empty box.
    """
    sections: list[str] = []
    if overlay_mode != "none":
        label = _OVERLAY_LABEL[overlay_mode]
        sections.append(f"""
          <div style="font-weight:600;margin-bottom:2px;">{label}</div>
          <div style="width:120px;height:12px;border-radius:2px;margin:4px 0;
                      background:linear-gradient(to right, rgb(255,240,30), rgb(25,118,210));"></div>
          <div style="display:flex;justify-content:space-between;color:#666;width:120px;">
            <span>Low</span><span>High</span>
          </div>
        """)
    if has_selection:
        margin_top = "6px" if sections else "0"
        sections.append(f"""
          <div style="display:flex;align-items:center;gap:6px;margin-top:{margin_top};">
            <span style="width:12px;height:12px;border-radius:2px;display:inline-block;
                        background:{HIGHLIGHT_FILL};border:1.5px solid {HIGHLIGHT_BORDER};"></span>
            <span>Your selection</span>
          </div>
        """)
    if not sections:
        return
    html = f"""
    <div style="position: fixed; bottom: 20px; left: 20px; z-index: 9999;
                background: white; border-radius: 6px; padding: 8px 10px;
                box-shadow: 0 1px 5px rgba(0,0,0,0.25); font-size: 11px; line-height: 1.4;">
      {''.join(sections)}
    </div>
    """
    m.get_root().html.add_child(folium.Element(html))
