"""
Data loader for ResVal.

Loads GeoJSON boundary files, builds adjacency graphs (with disk caching),
pre-computes centroids, and manages geography data in memory.
"""

import json
import pickle
import time
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.strtree import STRtree


DATA_DIR = Path(__file__).parent.parent / "data"
CACHE_DIR = DATA_DIR / "cache"

# Geometry simplification tolerance by level (degrees, ~0.01 ~ 1km).
# Tract is pre-simplified at prepare time (tract.fgb), so no runtime simplification needed.
SIMPLIFY_TOLERANCE = {
    "state": 0.0,
    "county": 0.0,
    "tract": 0.0,
}


class GeographyData:
    """Holds all data for a single geography level."""

    def __init__(self, level: str, gdf: gpd.GeoDataFrame):
        self.level = level
        self.gdf = gdf
        self.geoids: list[str] = gdf["GEOID"].tolist()

        # Values: GEOID -> total residential value
        self.values: dict[str, float] = dict(
            zip(gdf["GEOID"], gdf["total_value"])
        )

        # Enrichment data: GEOID -> {housing_units, median_home_value, median_income}
        self.enrichment: dict[str, dict] = {}
        for _, row in gdf.iterrows():
            self.enrichment[row["GEOID"]] = {
                "housing_units": float(row.get("housing_units", 0)),
                "median_home_value": float(row.get("median_home_value", 0)),
                "median_income": float(row.get("median_income", 0)),
            }

        # Names: GEOID -> display name
        self.names: dict[str, str] = {}
        for _, row in gdf.iterrows():
            self.names[row["GEOID"]] = row.get("NAME", row["GEOID"])

        # Centroids: GEOID -> (lon, lat)
        centroids_series = gdf.geometry.centroid
        self.centroids: dict[str, tuple[float, float]] = {}
        for idx, geoid in enumerate(gdf["GEOID"]):
            c = centroids_series.iloc[idx]
            self.centroids[geoid] = (c.x, c.y)

        # Adjacency: GEOID -> set of neighboring GEOIDs
        self.adjacency: dict[str, set[str]] = {}

        # Cached GeoJSON strings
        self._geojson_cache: str | None = None

    def build_adjacency(self) -> None:
        """Build adjacency graph, using disk cache if available."""
        cache_path = CACHE_DIR / f"{self.level}_adjacency.pkl"

        if cache_path.exists():
            print(f"    Loading cached adjacency for {self.level}...")
            with open(cache_path, "rb") as f:
                self.adjacency = pickle.load(f)
            avg = sum(len(v) for v in self.adjacency.values()) / max(len(self.adjacency), 1)
            print(f"    Loaded from cache (avg {avg:.1f} neighbors)")
            return

        n = len(self.gdf)
        print(f"    Building adjacency for {self.level} ({n} features)...")
        start = time.time()

        geoids = self.gdf["GEOID"].values
        geometries = self.gdf.geometry.values

        for geoid in geoids:
            self.adjacency[geoid] = set()

        tree = STRtree(geometries)

        for i in range(n):
            geom = geometries[i]
            candidate_indices = tree.query(geom)
            for j in candidate_indices:
                if j <= i:
                    continue
                if geom.intersects(geometries[j]):
                    self.adjacency[geoids[i]].add(geoids[j])
                    self.adjacency[geoids[j]].add(geoids[i])

            if (i + 1) % 10000 == 0:
                print(f"      {i + 1}/{n} processed...")

        elapsed = time.time() - start
        avg = sum(len(v) for v in self.adjacency.values()) / max(len(self.adjacency), 1)
        print(f"    Adjacency built in {elapsed:.1f}s (avg {avg:.1f} neighbors)")

        # Cache to disk
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        with open(cache_path, "wb") as f:
            pickle.dump(self.adjacency, f)
        print(f"    Cached to {cache_path}")

    def get_geojson_str(self) -> str:
        """Return simplified GeoJSON string for client delivery."""
        if self._geojson_cache is not None:
            return self._geojson_cache

        gdf = self.gdf.copy()

        tolerance = SIMPLIFY_TOLERANCE.get(self.level, 0)
        if tolerance > 0:
            gdf["geometry"] = gdf.geometry.simplify(tolerance, preserve_topology=True)

        keep_cols = ["GEOID", "NAME", "total_value", "housing_units",
                     "median_home_value", "median_income", "geometry"]
        gdf = gdf[[c for c in keep_cols if c in gdf.columns]]

        self._geojson_cache = gdf.to_json()
        return self._geojson_cache

    def get_viewport_geojson(self, bbox: tuple[float, float, float, float]) -> str:
        """Return GeoJSON clipped to a bounding box (for tract-level viewport delivery)."""
        minx, miny, maxx, maxy = bbox
        from shapely.geometry import box
        viewport = box(minx, miny, maxx, maxy)

        mask = self.gdf.geometry.intersects(viewport)
        subset = self.gdf[mask].copy()

        tolerance = SIMPLIFY_TOLERANCE.get(self.level, 0)
        if tolerance > 0:
            subset["geometry"] = subset.geometry.simplify(tolerance, preserve_topology=True)

        keep_cols = ["GEOID", "NAME", "total_value", "housing_units",
                     "median_home_value", "median_income", "geometry"]
        subset = subset[[c for c in keep_cols if c in subset.columns]]

        return subset.to_json()


class DataStore:
    """Central data store for all geography levels."""

    def __init__(self):
        self.levels: dict[str, GeographyData] = {}
        self.reference_values: list[dict] = []
        self.educational_content: str = ""
        self.national_median_home_value: float = 0.0

    def load_all(self) -> None:
        """Load all available geography levels and reference values."""
        print("Loading ResVal data...")

        # Load reference values
        ref_path = DATA_DIR / "reference_values.csv"
        if ref_path.exists():
            df = pd.read_csv(ref_path)
            self.reference_values = df.to_dict(orient="records")
            print(f"  Loaded {len(self.reference_values)} reference values")

        # Load educational content
        edu_path = DATA_DIR / "educational_content.md"
        if edu_path.exists():
            self.educational_content = edu_path.read_text()
            print("  Loaded educational content")

        # Load geography levels
        for level in ["state", "county", "tract"]:
            fgb_path = DATA_DIR / f"{level}.fgb"
            geojson_path = DATA_DIR / f"{level}.geojson"
            if fgb_path.exists():
                path = fgb_path
            elif geojson_path.exists():
                path = geojson_path
            else:
                print(f"  WARNING: no boundary file for {level} (tried .fgb and .geojson), skipping")
                continue
            print(f"  Loading {level} boundaries from {path.name}...")
            gdf = gpd.read_file(path)
            geo_data = GeographyData(level, gdf)
            geo_data.build_adjacency()
            self.levels[level] = geo_data
            print(f"  {level}: {len(gdf)} features loaded")

        # Compute national median home value (weighted by housing units from tract data)
        if "tract" in self.levels:
            tract = self.levels["tract"]
            total_units = sum(e["housing_units"] for e in tract.enrichment.values())
            if total_units > 0:
                weighted_sum = sum(
                    e["median_home_value"] * e["housing_units"]
                    for e in tract.enrichment.values()
                )
                self.national_median_home_value = weighted_sum / total_units
            print(f"  National weighted median home value: ${self.national_median_home_value:,.0f}")

        print("Data loading complete!")

    def get_level(self, level: str) -> GeographyData | None:
        return self.levels.get(level)

    def get_geojson_str(self, level: str) -> str | None:
        geo_data = self.get_level(level)
        if geo_data is None:
            return None
        return geo_data.get_geojson_str()
