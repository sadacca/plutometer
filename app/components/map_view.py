"""Folium map builder for plutometer -- basemap, gradient overlay, and selection highlight."""

import geopandas as gpd
import folium

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
) -> folium.Map:
    """Build the map for the current render pass. render_gdf is already resolved by the
    caller to the right slice for the active level (full state/county gdf, or the current
    tract viewport) -- this module only draws it."""
    m = folium.Map(location=list(center), zoom_start=zoom, tiles=None)
    folium.TileLayer(tiles=BASEMAP_URL, attr=BASEMAP_ATTR, name="basemap", max_zoom=18).add_to(m)

    if render_gdf is not None and len(render_gdf) > 0:
        _add_gradient_layer(m, render_gdf, overlay_mode)
        if selected_geoids:
            _add_highlight_layer(m, render_gdf, selected_geoids)
        _add_legend(m, overlay_mode)

    if marker_latlon is not None:
        folium.Marker(location=list(marker_latlon)).add_to(m)

    return m


def _add_gradient_layer(m: folium.Map, gdf: gpd.GeoDataFrame, overlay_mode: str) -> None:
    if overlay_mode == "none":

        def style_function(_feature):
            return {"color": "#999", "weight": 0.5, "fillOpacity": 0}

    else:
        field = _OVERLAY_FIELD[overlay_mode]
        vals = [v for v in gdf.get(field, []) if v and v > 0]
        vmin, vmax = (min(vals), max(vals)) if vals else (0.0, 0.0)

        def style_function(feature, field=field, vmin=vmin, vmax=vmax):
            v = feature["properties"].get(field) or 0
            fill = price_color(v, vmin, vmax) if v > 0 else "#f0f0f0"
            return {"color": "#aaa", "weight": 0.3, "fillColor": fill, "fillOpacity": 0.5}

    tooltip_fields = [f for f in ["NAME", "total_value", "median_home_value", "median_income"] if f in gdf.columns]
    tooltip_aliases = {
        "NAME": "Name:",
        "total_value": "Total value:",
        "median_home_value": "Median home:",
        "median_income": "Median income:",
    }
    cols = [c for c in ["GEOID", "NAME", "total_value", "median_home_value", "median_income", "geometry"] if c in gdf.columns]

    folium.GeoJson(
        gdf[cols],
        name="gradient",
        style_function=style_function,
        tooltip=folium.GeoJsonTooltip(
            fields=tooltip_fields,
            aliases=[tooltip_aliases[f] for f in tooltip_fields],
            sticky=True,
        ) if tooltip_fields else None,
    ).add_to(m)


def _add_highlight_layer(m: folium.Map, gdf: gpd.GeoDataFrame, selected_geoids: set[str]) -> None:
    sub = gdf[gdf["GEOID"].isin(selected_geoids)]
    if len(sub) == 0:
        return

    def style_function(_feature):
        return {"color": HIGHLIGHT_BORDER, "weight": 2, "fillColor": HIGHLIGHT_FILL, "fillOpacity": 0.55}

    folium.GeoJson(sub[["GEOID", "geometry"]], name="highlight", style_function=style_function).add_to(m)


def _add_legend(m: folium.Map, overlay_mode: str) -> None:
    if overlay_mode == "none":
        return
    label = _OVERLAY_LABEL[overlay_mode]
    html = f"""
    <div style="position: fixed; bottom: 20px; left: 20px; z-index: 9999;
                background: white; border-radius: 6px; padding: 8px 10px;
                box-shadow: 0 1px 5px rgba(0,0,0,0.25); font-size: 11px; line-height: 1.4;">
      <div style="font-weight:600;margin-bottom:2px;">{label}</div>
      <div style="width:120px;height:12px;border-radius:2px;margin:4px 0;
                  background:linear-gradient(to right, rgb(255,240,30), rgb(25,118,210));"></div>
      <div style="display:flex;justify-content:space-between;color:#666;width:120px;">
        <span>Low</span><span>High</span>
      </div>
    </div>
    """
    m.get_root().html.add_child(folium.Element(html))
