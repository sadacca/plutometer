"""
Data-integrity checks for the committed data/ files (data/state.geojson,
data/county.geojson, data/tract_values.parquet).

Catches the class of bug where an entire state's geographies silently read
as $0 -- e.g. Connecticut's 2022 county-equivalent GEOID scheme change broke
the PDB join in scripts/prepare_data.py (see _fix_ct_geoids there) and every
CT county/tract rendered as blank white space on the map instead of erroring
loudly. A state-wide $0 wipeout is not ordinary sparse/suppressed Census
data -- isolated low-population outliers (e.g. Loving County, TX) leave the
rest of their state intact, so "every geography in a state reads $0" is a
reliable signal of a systematic GEOID join failure, not real missing data.

Runs against the actual committed data (data/ is committed to git except
data/raw/, so this needs no network and no pipeline run) -- skips cleanly if
a file isn't present (e.g. a fresh checkout before scripts/prepare_data.py
has been run).
"""

from pathlib import Path

import geopandas as gpd
import pandas as pd
import pytest

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _load_value_columns(filename: str, value_col: str) -> pd.DataFrame:
    path = DATA_DIR / filename
    if not path.exists():
        pytest.skip(f"{filename} not present -- run scripts/prepare_data.py first")
    if filename.endswith(".parquet"):
        return pd.read_parquet(path, columns=["GEOID", value_col])
    gdf = gpd.read_file(path)
    return pd.DataFrame(gdf[["GEOID", value_col]])


@pytest.mark.parametrize("filename", ["state.geojson", "county.geojson", "tract_values.parquet"])
@pytest.mark.parametrize("value_col", ["total_value", "median_home_value"])
def test_no_state_is_entirely_zero_value(filename, value_col):
    """Every state (grouped by the GEOID's leading 2-digit state FIPS) should
    have at least one geography with a nonzero value at each level.
    """
    df = _load_value_columns(filename, value_col)
    df["state_fips"] = df["GEOID"].astype(str).str[:2]

    has_nonzero = df.groupby("state_fips")[value_col].apply(lambda s: (s > 0).any())
    all_zero_states = sorted(has_nonzero[~has_nonzero].index)

    assert not all_zero_states, (
        f"{filename}: state FIPS {all_zero_states} have every {value_col} == 0. "
        "This is the signature of a systematic GEOID join failure in the data "
        "pipeline (see _fix_ct_geoids in scripts/prepare_data.py for a prior "
        "example), not real missing data -- isolated sparse geographies don't "
        "zero out a whole state at once."
    )
