"""
Download Census cartographic boundary files and Planning Database (PDB),
join real PDB values to boundaries, and produce GeoJSON files for ResVal.

Uses 2023 PDB (ACS 2017-2021 vintage) tract-level data.
Aggregates tracts to county and state levels.
"""

import json
import os
import zipfile
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import requests

DATA_DIR = Path(__file__).parent.parent / "data"
RAW_DIR = DATA_DIR / "raw"

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
    "GIDTR": "GEOID",                                # tract GEOID
    "State": "STATEFP",                              # state FIPS
    "County": "COUNTYFP",                            # county FIPS
    "Tot_Housing_Units_ACS_17_21": "housing_units",  # total housing units
    "Med_House_Value_ACS_17_21": "median_home_value", # median house value
    "Med_HHD_Inc_ACS_17_21": "median_income",        # median household income
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
    # Only read the columns we need to save memory
    pdb_cols_to_read = list(PDB_COLUMNS.keys())
    df = pd.read_csv(pdb_path, usecols=pdb_cols_to_read, dtype=str, low_memory=False)

    # Rename columns
    df = df.rename(columns=PDB_COLUMNS)

    # Convert numeric columns (strip $, commas, and whitespace)
    for col in ["housing_units", "median_home_value", "median_income"]:
        df[col] = df[col].str.replace(r'[$,\s]', '', regex=True)
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    # Ensure GEOID is string and zero-padded to 11 chars
    df["GEOID"] = df["GEOID"].str.strip().str.zfill(11)
    df["STATEFP"] = df["GEOID"].str[:2]
    df["COUNTYFP_FULL"] = df["GEOID"].str[:5]  # state+county FIPS

    # Filter to continental US
    df = df[df["STATEFP"].isin(CONTINENTAL_FIPS)].copy()

    # Compute total residential value
    df["total_value"] = df["housing_units"] * df["median_home_value"]

    print(f"  PDB: loaded {len(df)} tracts, "
          f"total value ${df['total_value'].sum() / 1e12:.1f}T")

    return df


def aggregate_pdb_to_county(pdb: pd.DataFrame) -> pd.DataFrame:
    """Aggregate tract-level PDB to county level."""
    agg = pdb.groupby("COUNTYFP_FULL").agg(
        housing_units=("housing_units", "sum"),
        total_value=("total_value", "sum"),
        # Weighted averages for median values
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


def load_boundary(name: str) -> gpd.GeoDataFrame:
    """Load a boundary shapefile and prepare it."""
    extract_dir = download_and_extract_shp(BOUNDARY_URLS[name], name)

    shp_files = list(extract_dir.glob("*.shp"))
    if not shp_files:
        raise FileNotFoundError(f"No .shp file found in {extract_dir}")

    gdf = gpd.read_file(shp_files[0])

    # Filter to continental US
    gdf = gdf[gdf["STATEFP"].isin(CONTINENTAL_FIPS)].copy()

    # Normalize GEOID
    if name == "state":
        gdf["GEOID"] = gdf["STATEFP"]
    elif name == "county":
        if "GEOID" not in gdf.columns:
            gdf["GEOID"] = gdf["STATEFP"] + gdf["COUNTYFP"]

    # Ensure WGS84
    gdf = gdf.to_crs(epsg=4326)
    return gdf


def join_and_save(name: str, gdf: gpd.GeoDataFrame, pdb_agg: pd.DataFrame) -> None:
    """Join PDB values to boundaries and save.

    Tract is saved as FlatGeobuf (.fgb) with pre-applied simplification to keep
    the file small and fast to load. State and county are saved as GeoJSON.
    """
    # Tract uses FlatGeobuf (excluded from git, regenerated by this script).
    # State/county use GeoJSON (small enough to keep in git).
    if name == "tract":
        output_path = DATA_DIR / f"{name}.fgb"
        driver = "FlatGeobuf"
        simplify_tolerance = 0.005  # degrees, ~500m — matches runtime tolerance from data_loader
    else:
        output_path = DATA_DIR / f"{name}.geojson"
        driver = "GeoJSON"
        simplify_tolerance = 0.0

    print(f"  {name}: joining PDB data to {len(gdf)} boundaries...")

    # Merge on GEOID
    merged = gdf.merge(pdb_agg, on="GEOID", how="left", suffixes=("_shp", "_pdb"))

    # Use PDB NAME if available, fallback to shapefile NAME
    if "NAME_pdb" in merged.columns and "NAME_shp" in merged.columns:
        merged["NAME"] = merged["NAME_pdb"].fillna(merged["NAME_shp"])
        merged = merged.drop(columns=["NAME_pdb", "NAME_shp"])
    elif "NAME_pdb" in merged.columns:
        merged["NAME"] = merged["NAME_pdb"]
        merged = merged.drop(columns=["NAME_pdb"])

    # Fill missing values
    for col in ["housing_units", "median_home_value", "median_income", "total_value"]:
        if col in merged.columns:
            merged[col] = merged[col].fillna(0)

    # Keep needed columns
    keep_cols = ["GEOID", "NAME", "STATEFP", "geometry",
                 "housing_units", "median_home_value", "median_income", "total_value"]
    # For tracts, keep state/county names for display
    if name == "tract":
        if "state_name" in merged.columns:
            keep_cols.append("state_name")
        if "county_name" in merged.columns:
            keep_cols.append("county_name")
    keep_cols = [c for c in keep_cols if c in merged.columns]
    merged = merged[keep_cols]

    # Drop STATEFP if not needed at state level (it IS the GEOID)
    if name == "state" and "STATEFP" in merged.columns:
        merged = merged.drop(columns=["STATEFP"])

    if simplify_tolerance > 0:
        print(f"  {name}: simplifying geometry (tolerance={simplify_tolerance})...")
        merged["geometry"] = merged.geometry.simplify(simplify_tolerance, preserve_topology=True)

    fmt_label = "FlatGeobuf" if driver == "FlatGeobuf" else "GeoJSON"
    print(f"  {name}: saving {fmt_label} ({len(merged)} features) → {output_path.name}...")
    merged.to_file(output_path, driver=driver)
    size_mb = output_path.stat().st_size / 1024 / 1024
    total_val = merged["total_value"].sum()
    print(f"  {name}: done ({size_mb:.1f} MB, total value ${total_val / 1e12:.2f}T)")


def main():
    print("=" * 60)
    print("ResVal Data Preparation")
    print("=" * 60)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    # Check if outputs already exist
    all_exist = (
        all((DATA_DIR / f"{name}.geojson").exists() for name in ["state", "county"]) and
        (DATA_DIR / "tract.fgb").exists()
    )
    if all_exist:
        print("\nAll GeoJSON files already exist. Delete them to regenerate.")
        print("Files:")
        for f in sorted(DATA_DIR.glob("*.geojson")):
            print(f"  {f.name} ({f.stat().st_size / 1024 / 1024:.1f} MB)")
        return

    # Step 1: Download and load PDB
    print("\n--- Step 1: Loading Census Planning Database ---")
    pdb = load_pdb()

    # Step 2: Aggregate PDB to county and state levels
    print("\n--- Step 2: Aggregating PDB data ---")
    pdb_county = aggregate_pdb_to_county(pdb)
    print(f"  County: {len(pdb_county)} counties, total ${pdb_county['total_value'].sum() / 1e12:.2f}T")
    pdb_state = aggregate_pdb_to_state(pdb)
    print(f"  State: {len(pdb_state)} states, total ${pdb_state['total_value'].sum() / 1e12:.2f}T")

    # Step 3: Download boundaries and join with PDB
    print("\n--- Step 3: Processing boundaries ---")

    # States
    print("\nProcessing state boundaries...")
    state_gdf = load_boundary("state")
    join_and_save("state", state_gdf, pdb_state)

    # Counties
    print("\nProcessing county boundaries...")
    county_gdf = load_boundary("county")
    join_and_save("county", county_gdf, pdb_county)

    # Tracts
    print("\nProcessing tract boundaries...")
    tract_gdf = load_boundary("tract")
    # For tracts, PDB data is at the same level — just use it directly
    pdb_tract = pdb[["GEOID", "housing_units", "median_home_value",
                      "median_income", "total_value", "state_name", "county_name"]].copy()
    pdb_tract["NAME"] = pdb_tract["GEOID"]  # tracts don't have friendly names
    join_and_save("tract", tract_gdf, pdb_tract)

    print("\n" + "=" * 60)
    print("Data preparation complete!")
    print("=" * 60)
    print(f"\nFiles in {DATA_DIR}:")
    for f in sorted(list(DATA_DIR.glob("*.geojson")) + list(DATA_DIR.glob("*.fgb"))):
        print(f"  {f.name} ({f.stat().st_size / 1024 / 1024:.1f} MB)")


if __name__ == "__main__":
    main()
