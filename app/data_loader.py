"""
Data loader for plutometer.

Loads processed boundary/value files and precomputed adjacency caches -- all
produced ahead of time by scripts/prepare_data.py and committed to git -- and
exposes them to the Streamlit app. Nothing here re-fetches or rebuilds data
at runtime; it only reads what the pipeline already produced.

State and county are small enough to hold fully in memory, geometry included.
Tract (~85k features nationwide) never does: only its attributes (values,
enrichment, centroids, names) and precomputed adjacency graph are held in
memory. Tract geometry is read on demand, per map viewport, straight off
disk from data/tract.fgb via a spatially-indexed bbox read -- this is what
keeps the app's memory footprint bounded on Streamlit Community Cloud's free
tier regardless of how many tracts exist nationwide.
"""

import math
import pickle
from pathlib import Path

import geopandas as gpd
import pandas as pd
import streamlit as st
from shapely.geometry import box

DATA_DIR = Path(__file__).parent.parent / "data"
CACHE_DIR = DATA_DIR / "cache"

# NAD83 / Conus Albers Equal Area -- centroids are computed in this projected
# CRS (not directly on unprojected lon/lat geometry, which distorts centroids
# for large or non-convex shapes like states) and converted back to EPSG:4326.
_CENTROID_CRS = 5070


class GeographyData:
    """Values/enrichment/centroids/adjacency/names for one geography level, plus geometry access."""

    def __init__(
        self,
        level: str,
        attrs_df: pd.DataFrame,
        adjacency: dict[str, set[str]],
        full_gdf: gpd.GeoDataFrame | None = None,
        fgb_path: Path | None = None,
    ):
        self.level = level
        self.adjacency = adjacency
        self.full_gdf = full_gdf  # state/county: populated. tract: None (see fgb_path).
        self.fgb_path = fgb_path  # tract only: geometry read on demand from here.
        self._attrs_df = attrs_df

        self.geoids: list[str] = attrs_df["GEOID"].tolist()
        self.values: dict[str, float] = dict(
            zip(attrs_df["GEOID"], attrs_df["total_value"].fillna(0))
        )
        self.names: dict[str, str] = dict(
            zip(attrs_df["GEOID"], attrs_df["NAME"].fillna(attrs_df["GEOID"]))
        )
        self.enrichment: dict[str, dict] = {
            row["GEOID"]: {
                "housing_units": float(row.get("housing_units", 0) or 0),
                "median_home_value": float(row.get("median_home_value", 0) or 0),
                "median_income": float(row.get("median_income", 0) or 0),
            }
            for _, row in attrs_df.iterrows()
        }

        if "centroid_lon" in attrs_df.columns:
            self.centroids: dict[str, tuple[float, float]] = {
                row["GEOID"]: (row["centroid_lon"], row["centroid_lat"])
                for _, row in attrs_df.iterrows()
            }
        elif full_gdf is not None:
            c = full_gdf.geometry.to_crs(_CENTROID_CRS).centroid.set_crs(_CENTROID_CRS).to_crs(4326)
            self.centroids = {geoid: (pt.x, pt.y) for geoid, pt in zip(full_gdf["GEOID"], c)}
        else:
            self.centroids = {}

    def viewport_gdf(self, bbox: tuple[float, float, float, float]) -> gpd.GeoDataFrame:
        """Geometry for the current map viewport, joined with attributes for styling/tooltips."""
        if self.full_gdf is not None:
            minx, miny, maxx, maxy = bbox
            mask = self.full_gdf.geometry.intersects(box(minx, miny, maxx, maxy))
            return self.full_gdf[mask]
        if self.fgb_path is None:
            return gpd.GeoDataFrame()
        geom = _read_tract_viewport(str(self.fgb_path), _round_bbox_out(bbox))
        return geom.merge(self._attrs_df, on="GEOID", how="left")


def _round_bbox_out(bbox: tuple[float, float, float, float], precision: int = 3):
    """Round a bbox outward to a coarse grid so nearby viewports share a cache key."""
    minx, miny, maxx, maxy = bbox
    factor = 10**precision
    return (
        math.floor(minx * factor) / factor,
        math.floor(miny * factor) / factor,
        math.ceil(maxx * factor) / factor,
        math.ceil(maxy * factor) / factor,
    )


@st.cache_data(show_spinner=False)
def _read_tract_viewport(fgb_path: str, bbox: tuple[float, float, float, float]) -> gpd.GeoDataFrame:
    """Spatially-indexed partial read of the tract geometry file -- never loads the whole thing."""
    return gpd.read_file(fgb_path, bbox=bbox, engine="pyogrio")


def _load_adjacency(level: str) -> dict[str, set[str]]:
    path = CACHE_DIR / f"{level}_adjacency.pkl"
    if not path.exists():
        return {}
    with open(path, "rb") as f:
        return pickle.load(f)


class DataStore:
    """Central data store for all geography levels, reference values, and educational content."""

    def __init__(self):
        self.levels: dict[str, GeographyData] = {}
        self.reference_values: list[dict] = []
        self.educational_content: str = ""
        self.scale_reference_content: str = ""
        self.national_median_home_value: float = 0.0

    def get_level(self, level: str) -> GeographyData | None:
        return self.levels.get(level)


@st.cache_resource(show_spinner="Loading plutometer data...")
def load_store() -> DataStore:
    """Load everything once per app process; shared across all sessions/reruns."""
    store = DataStore()

    ref_path = DATA_DIR / "reference_values.csv"
    if ref_path.exists():
        store.reference_values = pd.read_csv(ref_path).to_dict(orient="records")

    edu_path = DATA_DIR / "educational_content.md"
    if edu_path.exists():
        store.educational_content = edu_path.read_text()

    scale_path = DATA_DIR / "scale_reference.md"
    if scale_path.exists():
        store.scale_reference_content = scale_path.read_text()

    # State + county: small enough to hold the full GeoDataFrame in memory.
    for level in ["state", "county"]:
        path = DATA_DIR / f"{level}.geojson"
        if not path.exists():
            continue
        gdf = gpd.read_file(path)
        attrs_df = pd.DataFrame(gdf.drop(columns="geometry"))
        adjacency = _load_adjacency(level)
        store.levels[level] = GeographyData(level, attrs_df, adjacency, full_gdf=gdf)

    # Tract: lean load. Attributes + adjacency in memory; geometry stays on disk.
    values_path = DATA_DIR / "tract_values.parquet"
    fgb_path = DATA_DIR / "tract.fgb"
    if values_path.exists() and fgb_path.exists():
        attrs_df = pd.read_parquet(values_path)
        adjacency = _load_adjacency("tract")
        store.levels["tract"] = GeographyData("tract", attrs_df, adjacency, fgb_path=fgb_path)

    if "tract" in store.levels:
        tract = store.levels["tract"]
        total_units = sum(e["housing_units"] for e in tract.enrichment.values())
        if total_units > 0:
            weighted_sum = sum(
                e["median_home_value"] * e["housing_units"] for e in tract.enrichment.values()
            )
            store.national_median_home_value = weighted_sum / total_units

    return store
