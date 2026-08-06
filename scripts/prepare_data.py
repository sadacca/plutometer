"""
Data pipeline for plutometer.

Downloads Census cartographic boundary files and Planning Database (PDB),
joins real PDB values to boundaries, builds adjacency graphs, and writes the
processed files the Streamlit app reads from `data/`.

Uses 2023 PDB (ACS 2017-2021 vintage) tract-level data.
Aggregates tracts to county and state levels.

Stages (run independently or all together):
    python scripts/prepare_data.py --stage boundaries   # state + county geojson
    python scripts/prepare_data.py --stage tract         # tract.fgb (geometry) + tract_values.parquet
    python scripts/prepare_data.py --stage adjacency     # data/cache/{level}_adjacency.pkl
    python scripts/prepare_data.py                       # all stages, in order

All outputs land in `data/` and are committed to git — the deployed Streamlit
app only ever reads these files, it never re-runs this pipeline itself.
"""

import argparse
import pickle
import zipfile
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import requests
from shapely.strtree import STRtree

DATA_DIR = Path(__file__).parent.parent / "data"
RAW_DIR = DATA_DIR / "raw"
CACHE_DIR = DATA_DIR / "cache"

# Census Bureau cartographic boundary files (2022 vintage)
BOUNDARY_URLS = {
    "state": "https://www2.census.gov/geo/tiger/GENZ2022/shp/cb_2022_us_state_20m.zip",
    "county": "https://www2.census.gov/geo/tiger/GENZ2022/shp/cb_2022_us_county_20m.zip",
    "tract": "https://www2.census.gov/geo/tiger/GENZ2022/shp/cb_2022_us_tract_500k.zip",
}

# Census Planning Database (2023 = ACS 2017-2021)
PDB_URL = "https://www2.census.gov/adrm/PDB/2023/pdb2023tr.csv"

# PDB columns we need
PDB_COLUMNS = {
    "GIDTR": "GEOID",                                 # tract GEOID
    "State": "STATEFP",                               # state FIPS
    "County": "COUNTYFP",                              # county FIPS
    "Tot_Housing_Units_ACS_17_21": "housing_units",   # total housing units
    "Med_House_Value_ACS_17_21": "median_home_value", # median house value
    "Med_HHD_Inc_ACS_17_21": "median_income",         # median household income
    "State_name": "state_name",
    "County_name": "county_name",
}

# Continental US state FIPS codes (exclude AK=02, HI=15, territories)
CONTINENTAL_FIPS = {
    "01", "04", "05", "06", "08", "09", "10", "11", "12", "13",
    "16", "17", "18", "19", "20", "21", "22", "23", "24", "25",
    "26", "27", "28", "29", "30", "31", "32", "33", "34", "35",
    "36", "37", "38", "39", "40", "41", "42", "44", "45", "46",
    "47", "48", "49", "50", "51", "53", "54", "55", "56",
}

# Simplification tolerances (degrees) tried in order for the tract geometry
# file until the written FlatGeobuf is under TRACT_FGB_MAX_MB.
TRACT_SIMPLIFY_TOLERANCES = [0.005, 0.01, 0.02, 0.04]
TRACT_FGB_MAX_MB = 80

# NAD83 / Conus Albers Equal Area -- centroids are computed in this projected
# CRS (not directly on unprojected lon/lat geometry, which distorts centroids
# for large or non-convex shapes) and converted back to EPSG:4326 for storage.
CENTROID_CRS = 5070


def accurate_centroids(geometry: gpd.GeoSeries) -> gpd.GeoSeries:
    """Centroids computed in a projected CRS, returned as points in EPSG:4326."""
    projected = geometry.to_crs(CENTROID_CRS).centroid
    return projected.set_crs(CENTROID_CRS).to_crs(4326)


def download_file(url: str, dest: Path, description: str) -> Path:
    """Download a file if it doesn't already exist."""
    if dest.exists():
        print(f"  {description}: already downloaded, skipping")
        return dest

    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"  {description}: downloading from {url}")
    resp = requests.get(url, stream=True, timeout=300)
    resp.raise_for_status()

    total = int(resp.headers.get("content-length", 0))
    downloaded = 0
    with open(dest, "wb") as f:
        for chunk in resp.iter_content(chunk_size=65536):
            f.write(chunk)
            downloaded += len(chunk)
            if total > 0:
                pct = downloaded * 100 // total
                print(f"\r  {description}: {pct}% ({downloaded // 1024 // 1024}MB)", end="", flush=True)
    print()
    return dest


def download_and_extract_shp(url: str, name: str) -> Path:
    """Download a zip shapefile and extract it."""
    extract_dir = RAW_DIR / name

    if extract_dir.exists() and any(extract_dir.glob("*.shp")):
        print(f"  {name}: already downloaded, skipping")
        return extract_dir

    zip_path = RAW_DIR / f"{name}.zip"
    download_file(url, zip_path, name)

    print(f"  {name}: extracting")
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(extract_dir)

    zip_path.unlink()
    return extract_dir


def load_pdb() -> pd.DataFrame:
    """Download and load the Census Planning Database tract-level CSV."""
    pdb_path = RAW_DIR / "pdb2023tr.csv"
    download_file(PDB_URL, pdb_path, "PDB tract CSV")

    print("  PDB: reading CSV (this may take a moment)...")
    pdb_cols_to_read = list(PDB_COLUMNS.keys())
    df = pd.read_csv(pdb_path, usecols=pdb_cols_to_read, dtype=str, low_memory=False)

    df = df.rename(columns=PDB_COLUMNS)

    for col in ["housing_units", "median_home_value", "median_income"]:
        df[col] = df[col].str.replace(r'[$,\s]', '', regex=True)
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    df["GEOID"] = df["GEOID"].str.strip().str.zfill(11)
    df["STATEFP"] = df["GEOID"].str[:2]
    df["COUNTYFP_FULL"] = df["GEOID"].str[:5]

    df = df[df["STATEFP"].isin(CONTINENTAL_FIPS)].copy()

    df["total_value"] = df["housing_units"] * df["median_home_value"]

    print(f"  PDB: loaded {len(df)} tracts, "
          f"total value ${df['total_value'].sum() / 1e12:.1f}T")

    return df


def aggregate_pdb_to_county(pdb: pd.DataFrame) -> pd.DataFrame:
    """Aggregate tract-level PDB to county level."""
    agg = pdb.groupby("COUNTYFP_FULL").agg(
        housing_units=("housing_units", "sum"),
        total_value=("total_value", "sum"),
        _wt_home_value=("median_home_value", lambda x: np.average(x, weights=pdb.loc[x.index, "housing_units"].replace(0, 1))),
        _wt_income=("median_income", lambda x: np.average(x, weights=pdb.loc[x.index, "housing_units"].replace(0, 1))),
        state_name=("state_name", "first"),
        county_name=("county_name", "first"),
    ).reset_index()
    agg = agg.rename(columns={
        "COUNTYFP_FULL": "GEOID",
        "_wt_home_value": "median_home_value",
        "_wt_income": "median_income",
    })
    agg["STATEFP"] = agg["GEOID"].str[:2]
    agg["NAME"] = agg["county_name"] + ", " + agg["state_name"]
    return agg


def aggregate_pdb_to_state(pdb: pd.DataFrame) -> pd.DataFrame:
    """Aggregate tract-level PDB to state level."""
    agg = pdb.groupby("STATEFP").agg(
        housing_units=("housing_units", "sum"),
        total_value=("total_value", "sum"),
        _wt_home_value=("median_home_value", lambda x: np.average(x, weights=pdb.loc[x.index, "housing_units"].replace(0, 1))),
        _wt_income=("median_income", lambda x: np.average(x, weights=pdb.loc[x.index, "housing_units"].replace(0, 1))),
        state_name=("state_name", "first"),
    ).reset_index()
    agg = agg.rename(columns={
        "STATEFP": "GEOID",
        "_wt_home_value": "median_home_value",
        "_wt_income": "median_income",
    })
    agg["NAME"] = agg["state_name"]
    return agg


def _load_ct_tract_geoids() -> pd.Series:
    """New-scheme (2022-vintage) Connecticut tract GEOIDs, attribute-only read --
    used to build the CT GEOID crosswalk (see _fix_ct_geoids) when the caller
    doesn't otherwise need tract geometry (stage_boundaries only needs state
    + county boundaries, but still needs this to fix CT's county-level join).
    """
    extract_dir = download_and_extract_shp(BOUNDARY_URLS["tract"], "tract")
    shp_files = list(extract_dir.glob("*.shp"))
    if not shp_files:
        raise FileNotFoundError(f"No .shp file found in {extract_dir}")
    df = gpd.read_file(shp_files[0], ignore_geometry=True, columns=["GEOID", "STATEFP"])
    return df.loc[df["STATEFP"] == "09", "GEOID"]


def _ct_geoid_crosswalk(new_ct_geoids: pd.Series) -> dict[str, str]:
    """Old-GEOID-suffix -> new-GEOID lookup for Connecticut tracts.

    In June 2022 the Census Bureau retired CT's 8 counties (FIPS 09001-09015)
    in favor of 9 new planning-region county-equivalents (FIPS 09110-09190)
    for TIGER/cartographic products. PDB (ACS 2017-2021 vintage) predates the
    switch and still reports the old scheme, so a plain GEOID merge against
    the 2022-vintage boundary files matches zero CT rows -- every CT county
    and tract silently reads as $0 instead of erroring (see _fix_ct_geoids).

    Census confirms tract boundaries/numbers were *not* changed by the
    switch -- only the 3-digit county code embedded in the GEOID was -- so
    the boundary file's own tract GEOIDs give a crosswalk from PDB's old
    GEOID to the matching new GEOID, keyed on the (unchanged) 6-digit
    tract-number suffix. This needs no external crosswalk file, but tract
    numbers are only guaranteed unique *within* a county, not statewide, so
    a same-suffix collision across different new regions is possible -- if
    the warning below ever fires, verify against Census's official
    2020-to-2022 tract relationship file before trusting CT's numbers.
    """
    suffixes = new_ct_geoids.str[-6:]
    dupes = suffixes[suffixes.duplicated(keep=False)]
    if not dupes.empty:
        print(f"  WARNING: {dupes.nunique()} CT tract-number suffixes repeat across "
              "different planning regions -- the crosswalk may misassign PDB rows "
              "for those tracts.")
    return dict(zip(suffixes, new_ct_geoids))


def _fix_ct_geoids(pdb: pd.DataFrame, new_ct_geoids: pd.Series) -> pd.DataFrame:
    """Remap PDB's old-scheme Connecticut GEOIDs to the boundary files' new
    planning-region scheme (see _ct_geoid_crosswalk) so _merge_pdb's join
    doesn't silently zero out all of CT. Must run before any downstream use
    of GEOID/COUNTYFP_FULL (aggregation, NAME assignment, etc.).
    """
    is_ct = pdb["STATEFP"] == "09"
    if not is_ct.any():
        return pdb

    crosswalk = _ct_geoid_crosswalk(new_ct_geoids)
    old_suffix = pdb.loc[is_ct, "GEOID"].str[-6:]
    remapped = old_suffix.map(crosswalk)
    matched = remapped[remapped.notna()]

    n_ct = int(is_ct.sum())
    n_matched = len(matched)
    print(f"  CT GEOID crosswalk: {n_matched}/{n_ct} tracts remapped to the new "
          "planning-region GEOID scheme")
    if n_matched < n_ct:
        print(f"  WARNING: {n_ct - n_matched} CT tracts had no match by tract-number "
              "suffix -- their PDB rows will fail to join and read as $0. Inspect "
              "before trusting this run's CT data.")

    pdb = pdb.copy()
    pdb.loc[matched.index, "GEOID"] = matched.values
    pdb.loc[matched.index, "COUNTYFP_FULL"] = matched.str[:5].values
    if "county_name" in pdb.columns:
        # PDB's county_name is keyed to the old county scheme (e.g. "Hartford
        # County"), which no longer matches the remapped GEOID -- blank it so
        # aggregate_pdb_to_county's NAME comes out NaN and _merge_pdb's
        # NAME_pdb.fillna(NAME_shp) falls back to the boundary shapefile's
        # own correct planning-region name (e.g. "Capitol") instead of a
        # stale county name.
        pdb.loc[matched.index, "county_name"] = pd.NA
    return pdb


def load_boundary(name: str) -> gpd.GeoDataFrame:
    """Load a boundary shapefile and prepare it."""
    extract_dir = download_and_extract_shp(BOUNDARY_URLS[name], name)

    shp_files = list(extract_dir.glob("*.shp"))
    if not shp_files:
        raise FileNotFoundError(f"No .shp file found in {extract_dir}")

    gdf = gpd.read_file(shp_files[0])

    gdf = gdf[gdf["STATEFP"].isin(CONTINENTAL_FIPS)].copy()

    if name == "state":
        gdf["GEOID"] = gdf["STATEFP"]
    elif name == "county":
        if "GEOID" not in gdf.columns:
            gdf["GEOID"] = gdf["STATEFP"] + gdf["COUNTYFP"]

    gdf = gdf.to_crs(epsg=4326)
    return gdf


def _merge_pdb(gdf: gpd.GeoDataFrame, pdb_agg: pd.DataFrame) -> gpd.GeoDataFrame:
    merged = gdf.merge(pdb_agg, on="GEOID", how="left", suffixes=("_shp", "_pdb"))

    if "NAME_pdb" in merged.columns and "NAME_shp" in merged.columns:
        merged["NAME"] = merged["NAME_pdb"].fillna(merged["NAME_shp"])
        merged = merged.drop(columns=["NAME_pdb", "NAME_shp"])
    elif "NAME_pdb" in merged.columns:
        merged["NAME"] = merged["NAME_pdb"]
        merged = merged.drop(columns=["NAME_pdb"])

    for col in ["housing_units", "median_home_value", "median_income", "total_value"]:
        if col in merged.columns:
            merged[col] = merged[col].fillna(0)

    return merged


def stage_boundaries() -> None:
    """State + county: download, join PDB values, write small GeoJSON files."""
    print("\n--- Stage: boundaries (state + county) ---")
    pdb = load_pdb()
    pdb = _fix_ct_geoids(pdb, _load_ct_tract_geoids())

    pdb_county = aggregate_pdb_to_county(pdb)
    print(f"  County: {len(pdb_county)} counties, total ${pdb_county['total_value'].sum() / 1e12:.2f}T")
    pdb_state = aggregate_pdb_to_state(pdb)
    print(f"  State: {len(pdb_state)} states, total ${pdb_state['total_value'].sum() / 1e12:.2f}T")

    for name, pdb_agg in [("state", pdb_state), ("county", pdb_county)]:
        print(f"\n  Processing {name} boundaries...")
        gdf = load_boundary(name)
        merged = _merge_pdb(gdf, pdb_agg)

        keep_cols = ["GEOID", "NAME", "STATEFP", "geometry",
                     "housing_units", "median_home_value", "median_income", "total_value"]
        keep_cols = [c for c in keep_cols if c in merged.columns]
        merged = merged[keep_cols]
        if name == "state" and "STATEFP" in merged.columns:
            merged = merged.drop(columns=["STATEFP"])

        output_path = DATA_DIR / f"{name}.geojson"
        merged.to_file(output_path, driver="GeoJSON")
        size_mb = output_path.stat().st_size / 1024 / 1024
        total_val = merged["total_value"].sum()
        print(f"  {name}: saved {output_path.name} ({size_mb:.1f} MB, "
              f"{len(merged)} features, total value ${total_val / 1e12:.2f}T)")


def _write_fgb(gdf: gpd.GeoDataFrame, path: Path) -> None:
    """Write a GeoDataFrame as a single-file FlatGeobuf.

    GDAL's FlatGeobuf driver only writes a single flat file when the given
    path itself ends in ".fgb" -- any other extension (e.g. a ".tmp" scratch
    name) makes it treat the path as a *dataset directory* and write a
    per-layer file inside it instead, silently turning "tract.fgb" into a
    directory containing "tract.fgb/tract.fgb.fgb". Every intermediate name
    used here must keep the .fgb suffix to avoid that.
    """
    if path.exists():
        path.unlink()
    gdf.to_file(path, driver="FlatGeobuf")


def _write_tract_fgb(geom_gdf: gpd.GeoDataFrame) -> None:
    """Write geometry-only tract file, simplifying further if it's too large for git."""
    output_path = DATA_DIR / "tract.fgb"
    tmp_path = DATA_DIR / "tract.trial.fgb"
    for tolerance in TRACT_SIMPLIFY_TOLERANCES:
        g = geom_gdf.copy()
        g["geometry"] = g.geometry.simplify(tolerance, preserve_topology=True)

        _write_fgb(g, tmp_path)
        size_mb = tmp_path.stat().st_size / 1024 / 1024
        print(f"  tract.fgb: tolerance={tolerance} -> {size_mb:.1f} MB")

        if size_mb <= TRACT_FGB_MAX_MB:
            tmp_path.replace(output_path)
            print(f"  tract.fgb: within {TRACT_FGB_MAX_MB}MB cap, done.")
            return
        tmp_path.unlink()

    # Ran out of tolerances to try; use the coarsest simplification anyway
    # rather than fail the pipeline, but make the overage visible.
    print(f"  WARNING: tract.fgb still exceeds {TRACT_FGB_MAX_MB}MB cap after "
          f"max simplification (tolerance={TRACT_SIMPLIFY_TOLERANCES[-1]}); writing anyway.")
    g = geom_gdf.copy()
    g["geometry"] = g.geometry.simplify(TRACT_SIMPLIFY_TOLERANCES[-1], preserve_topology=True)
    _write_fgb(g, output_path)


def stage_tract() -> None:
    """Tract: download, join PDB values, split into geometry (fgb) + attributes (parquet)."""
    print("\n--- Stage: tract ---")
    pdb = load_pdb()
    tract_gdf = load_boundary("tract")
    pdb = _fix_ct_geoids(pdb, tract_gdf.loc[tract_gdf["GEOID"].str.startswith("09"), "GEOID"])

    pdb_tract = pdb[["GEOID", "housing_units", "median_home_value",
                      "median_income", "total_value", "state_name", "county_name"]].copy()
    pdb_tract["NAME"] = pdb_tract["GEOID"]  # tracts don't have friendly names

    merged = _merge_pdb(tract_gdf, pdb_tract)

    # Centroids computed from the un-simplified geometry, before it's split off.
    centroids = accurate_centroids(merged.geometry)
    merged["centroid_lon"] = centroids.x
    merged["centroid_lat"] = centroids.y

    value_cols = ["GEOID", "NAME", "state_name", "county_name",
                  "housing_units", "median_home_value", "median_income", "total_value",
                  "centroid_lon", "centroid_lat"]
    value_cols = [c for c in value_cols if c in merged.columns]
    values_df = pd.DataFrame(merged[value_cols])
    values_path = DATA_DIR / "tract_values.parquet"
    values_df.to_parquet(values_path, index=False)
    size_mb = values_path.stat().st_size / 1024 / 1024
    print(f"  tract_values.parquet: saved ({size_mb:.1f} MB, {len(values_df)} tracts, "
          f"total value ${values_df['total_value'].sum() / 1e12:.2f}T)")

    geom_gdf = merged[["GEOID", "geometry"]].copy()
    _write_tract_fgb(geom_gdf)


def _build_adjacency(gdf: gpd.GeoDataFrame) -> dict[str, set[str]]:
    """Queen contiguity (edges + corners) via pairwise STRtree intersects."""
    n = len(gdf)
    geoids = gdf["GEOID"].values
    geometries = gdf.geometry.values

    adjacency: dict[str, set[str]] = {g: set() for g in geoids}
    tree = STRtree(geometries)

    for i in range(n):
        geom = geometries[i]
        candidate_indices = tree.query(geom)
        for j in candidate_indices:
            if j <= i:
                continue
            if geom.intersects(geometries[j]):
                adjacency[geoids[i]].add(geoids[j])
                adjacency[geoids[j]].add(geoids[i])
        if (i + 1) % 10000 == 0:
            print(f"      {i + 1}/{n} processed...")

    return adjacency


def stage_adjacency() -> None:
    """Build + pickle adjacency graphs for all three levels. Requires boundaries + tract stages."""
    print("\n--- Stage: adjacency ---")
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    sources = {
        "state": DATA_DIR / "state.geojson",
        "county": DATA_DIR / "county.geojson",
        "tract": DATA_DIR / "tract.fgb",
    }
    for level, path in sources.items():
        if not path.exists():
            print(f"  {level}: {path.name} not found, skipping (run the boundaries/tract stage first)")
            continue

        print(f"  {level}: building adjacency from {path.name}...")
        gdf = gpd.read_file(path)
        adjacency = _build_adjacency(gdf)
        avg = sum(len(v) for v in adjacency.values()) / max(len(adjacency), 1)

        cache_path = CACHE_DIR / f"{level}_adjacency.pkl"
        with open(cache_path, "wb") as f:
            pickle.dump(adjacency, f)
        size_mb = cache_path.stat().st_size / 1024 / 1024
        print(f"  {level}: {len(adjacency)} geographies, avg {avg:.1f} neighbors, "
              f"cached to {cache_path.name} ({size_mb:.1f} MB)")


STAGES = {
    "boundaries": stage_boundaries,
    "tract": stage_tract,
    "adjacency": stage_adjacency,
}


def main() -> None:
    parser = argparse.ArgumentParser(description="plutometer data pipeline")
    parser.add_argument("--stage", choices=list(STAGES.keys()), default=None,
                         help="Run a single stage. Omit to run all stages in order.")
    args = parser.parse_args()

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("plutometer Data Preparation")
    print("=" * 60)

    if args.stage:
        STAGES[args.stage]()
    else:
        for stage_fn in STAGES.values():
            stage_fn()

    print("\n" + "=" * 60)
    print("Data preparation complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
