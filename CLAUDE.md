# plutometer — Developer Context

## Mission

"How rich are the rich, really?" -- a teaching tool. Click a spot on the map,
pick a dollar amount, and see the largest contiguous set of geographies
(states / counties / Census tracts) whose combined residential real-estate
value doesn't exceed it. The point is to make abstract wealth figures
(a billionaire's net worth, the national debt, a household net-worth
percentile) tangible by mapping them onto real neighborhoods.

---

## Development Workflow

Work happens on short-lived feature branches (`claude/<slug>-<id>`), one per
task, each merged to `main` via its own PR -- there's no single long-lived
"active branch" name to keep in sync here (three have already come and
gone: `plutometer-streamlit-deploy-x00tqg`, `performance-responsiveness-
03picn`, `tract-display-zoom-yjs4w1`). Check your task instructions or the
repo's open PRs for whichever branch is current. The production app
auto-deploys from `main` on Streamlit Community Cloud on every merge (see
README.md for the one-time manual Streamlit Cloud connection step -- that
part isn't automatable via GitHub Actions).

---

## App Structure

Single-page Streamlit app, entrypoint `app/app.py`. Unlike a multi-tab
dashboard, plutometer is one screen: mobile-first, with the informative
header + result above the map, the map itself, and interactive controls
below it, so the whole click-to-see-result loop never requires opening the
sidebar. No `st.navigation` multipage split is needed.

- **Header + result (main column, above the map)**: a static "🏠 How rich
  are the rich, really?" title, then either the primary result as a styled
  `.pm-stat-card` or (before any click) a dashed empty-state banner. The
  result headline leads with *what's being compared* -- the picked
  reference name + value from `data/reference_values.csv`, or "Custom
  amount ($X)" -- followed by either "≈ N whole
  {states/counties/neighborhoods}" when at least one full geography fits
  (e.g. "Elon Musk Net Worth ($1.1T) ≈ 3 whole states"), or, when the
  target undercuts even the single smallest geography reached
  (`num_selected == 0`), `components/utils.fractional_headline()`'s
  house-count-tiered phrase ("Part of a house here" / "A few houses here"
  / "Part of a {state/county/neighborhood} here" for under 1 / up to
  `FEW_HOUSES_MAX` / more houses, respectively) -- a flat "smaller than a
  whole neighborhood" reads the same whether the money buys 3 houses or
  300, since a tract can hold hundreds to thousands of homes. This label is
  threaded through `_run_computation()` into
  `st.session_state.result_target_label` so it stays in sync with whichever
  click produced the result on screen, not whatever the controls happen to
  show this rerun. The caption line below gives the "how many houses"
  context at both local and national median price. A "📍 Viewing:
  {county}" caption and a data-vintage footer caption follow.
- **Map (main area)**: built by `components/map_view.build_map()` and
  rendered via `streamlit_folium.st_folium()`. A CARTO light basemap, a
  gradient choropleth layer, and (once a click has been processed) a
  highlight layer for the selected GEOIDs drawn on top.
- **Controls (main column, below the map)**: three columns -- geography
  level (`state` / `county` / `tract`); a wealth-category selectbox
  (grouped by `reference_values.csv`'s `category` column, default
  "Super-Rich Individuals") feeding a second selectbox for the specific
  amount within it, defaulting to Elon Musk's net worth so there's always a
  result to look at on first load; and a free-text custom-amount input
  (K/M/B/T shorthand via `components/utils.parse_value`), which overrides
  the dropdown when present. Controls live below the map (not above, not in
  the sidebar) so the map is the first thing seen on a mobile screen.
- **Sidebar (collapsed by default, secondary settings only)**: the map
  overlay-mode radio (median home price / total value / no fill), a Clear
  Selection button, `st.expander`s for selection details and area
  statistics (only once a result exists), and two `st.tabs`: "About this
  tool" (renders `data/educational_content.md`) and "What does a dollar
  buy?" (renders `data/scale_reference.md`, the order-of-magnitude
  home/neighborhood/metro scale reference).
- **Mobile whitespace**: custom CSS trims Streamlit's default
  block-container top padding (~6rem, only ~60px of which is needed to
  clear its fixed toolbar) and default 1rem inter-element gap, scoped to
  the main column via `[data-testid="stMainBlockContainer"]` so the
  sidebar's own spacing is untouched -- shifts the map and controls higher
  on a mobile viewport without needing Streamlit-internal APIs beyond that
  `data-testid` selector.
- **Click handling**: `st_folium`'s `last_clicked` is compared against
  `st.session_state.last_clicked_processed` each rerun; a genuinely new
  click triggers `_run_computation()` (calls `algorithm.expand_contiguous`
  in-process, no HTTP) followed by `st.rerun()` so the map redraws with the
  new highlight/marker. This one-rerun lag is inherent to `st_folium`: the
  map is sent to the browser before its own click event is known back in
  Python, so the highlight can only appear on the following rerun.
- **Auto-level cascade**: if the clicked geography's own value already
  exceeds the target, `_run_computation` recurses into the next finer level
  (state → county → tract) *only if that level's data is loaded*, staging
  the switch via `st.session_state.pending_geo_level` rather than mutating
  the `geo_level` selectbox's session-state key directly -- Streamlit
  forbids mutating a widget's key after that widget has rendered in the same
  run, so the pending value is applied at the top of the *next* script run,
  before the selectbox is instantiated.
- **Tract auto-zoom**: `TRACT_MIN_ZOOM = 8` (in `components/utils.py`). Below
  that zoom, tract boundaries aren't fetched at all (an `st.info` banner
  explains why); cascading into tract level bumps `st.session_state.map_zoom`
  to 8 directly (not widget-backed, safe to mutate any time).

### Algorithm (`app/algorithm.py`, unchanged from the original local app)

Greedy contiguous expansion from the clicked geography's nearest GEOID:
maintain a frontier of geographies adjacent to the current selection, and on
each pass try every frontier candidate (nearest-first by centroid distance
to the click point) until one fits without exceeding the target; repeat
until a full pass adds nothing. Two invariants, checked in
`tests/test_algorithm.py` against a synthetic 3x3 grid (no network,
no data files needed):
- **Always undershoot** -- the running total never exceeds the target.
- **Always contiguous** -- every selected geography connects back to the
  click point through other selected geographies.

This module is framework-agnostic (no Streamlit, no I/O) and unchanged from
the original FastAPI version -- `expand_contiguous` / `find_nearest_geoid`
just get called in-process now instead of over HTTP.

---

## Data Layer (`app/data_loader.py`)

State and county are small enough to hold fully in memory, geometry
included -- a `GeographyData` wrapping the whole `GeoDataFrame`. Tract
(~85k features nationwide) is deliberately **not** held fully in memory:
only its attributes (values, enrichment, centroids, names -- from
`tract_values.parquet`) and its precomputed adjacency graph
(`cache/tract_adjacency.pkl`) are loaded. Tract geometry is read on demand,
per current map viewport, straight off disk from `data/tract.fgb` via a
spatially-indexed `pyogrio` bbox read (`gpd.read_file(path, bbox=..., engine="pyogrio")`),
cached by a bbox rounded outward to a coarse grid
(`data_loader._round_bbox_out`) so small pan jitters don't re-hit disk. This
is what keeps the app's memory footprint bounded on Streamlit Community
Cloud's free tier (~1GB RAM) regardless of national tract count -- the
original local FastAPI version held all 85k tract polygons in memory
permanently, which is fine locally but risky on a memory-capped free host.

`load_store()` is `@st.cache_resource` (not `@st.cache_data`) -- it returns a
single heavy, non-serializable object (GeoDataFrames + adjacency dicts) that
should be built once per app process and shared across every session/rerun,
analogous to the old FastAPI `lifespan` startup load. This is an intentional
choice of the "load once, share across sessions" primitive over the
data-loader-returns-a-DataFrame pattern.

---

## Data Pipeline (`scripts/prepare_data.py`)

Three independently runnable stages (mirrors the sibling `balt311` repo's
`pipeline.py --stage` convention):

```bash
python scripts/prepare_data.py --stage boundaries   # state + county: data/state.geojson, data/county.geojson
python scripts/prepare_data.py --stage tract         # data/tract.fgb (geometry+GEOID only) + data/tract_values.parquet
python scripts/prepare_data.py --stage adjacency     # data/cache/{state,county,tract}_adjacency.pkl
python scripts/prepare_data.py                       # all three stages, in order
```

Data sources: Census cartographic boundary files (`cb_2022_us_{level}_*.zip`,
2022 vintage) and the Census Planning Database
(`pdb2023tr.csv`, ACS 2017-2021 vintage), both downloaded fresh into the
gitignored `data/raw/` on first run (subsequent runs reuse the cached
download). Total residential value per geography =
`tot_housing_units_acs_17_21 * med_house_value_acs_17_21`; county/state are
population-weighted aggregates of the tract-level PDB rows.

**Tract geometry/attribute split** is the key difference from the original
single-file `tract.fgb`: `data/tract.fgb` now holds geometry + GEOID *only*
(no attribute columns), and `data/tract_values.parquet` holds everything
else (values, enrichment, centroids, names). This is what makes tract data
committable to git at all -- the original all-in-one attributed tract file
was excluded from git as "too large." `_write_tract_fgb` also iteratively
re-simplifies (tolerances `[0.005, 0.01, 0.02, 0.04]` degrees) until the
written file is under `TRACT_FGB_MAX_MB = 80`, so nationwide tract geometry
stays within GitHub's file-size comfort zone regardless of how it grows.

**Adjacency** (queen contiguity -- edges + corners, via pairwise `STRtree`
intersects) is precomputed for all three levels by the `adjacency` stage and
pickled to `data/cache/*.pkl`, committed to git. The deployed app only ever
*loads* these caches; it never rebuilds an adjacency graph at runtime.

`data/reference_values.csv` (name, dollar value -- household net-worth
percentiles, billionaire net worths, national debt, etc.), sorted ascending
by value, and `data/educational_content.md` (the sidebar's "About this
tool" text) are hand-maintained, not pipeline-generated. Household
percentiles are Fed SCF 2022 (still the latest published survey; 2025 SCF
results aren't out until late 2026). Billionaire net worths, market caps,
and budget/debt figures were last refreshed July 2026 -- re-check these
periodically, they move fast (Elon Musk alone moved from ~$750B to ~$1.05T
within the same month after SpaceX's June 2026 IPO).

---

## GitHub Actions

- `.github/workflows/prepare_data.yml` -- `workflow_dispatch` only (no
  schedule: Census PDB/TIGER vintages change ~annually, not continuously).
  Runs the three stages in order, committing after each one so a later-stage
  failure still leaves earlier stages' output committed.
  `timeout-minutes: 120` to allow for the nationwide tract join + `STRtree`
  adjacency build.
- `.github/workflows/ci.yml` -- runs `tests/test_algorithm.py` and an
  import/syntax smoke check of the app modules on every push/PR. No network,
  no data files required. This is the "build" gate; actual deploy is
  Streamlit Community Cloud's auto-deploy from `main`, not a GitHub Action.

---

## Known UX deltas vs. the original local FastAPI + Leaflet app

Disclosed trade-offs from the Streamlit port, not regressions to "fix":

- The on-map Leaflet overlay-mode control became a sidebar `st.radio` --
  simpler and more robust in the Streamlit paradigm.
- The custom hamburger + mobile bottom-sheet panel became Streamlit's native
  sidebar collapse/responsive behavior -- not pixel-identical, but native and
  low-maintenance.
- The original's 300ms JS pan/zoom debounce became `st_folium`'s own
  discrete-interaction rerun granularity (it only fires on Leaflet's
  `moveend`/`zoomend`/click events, not continuous mousemove) -- broadly
  equivalent, not identical.
- Tract-level panning in dense viewports (e.g. NYC-scale, ~500+ tracts in
  view) is noticeably less snappy than the original's incremental Leaflet
  DOM updates, because each pan triggers a full Streamlit script rerun. This
  is bounded (never a memory blowup, worst case a slower rerun), not
  unbounded -- see the data-layer section above.

---

## Repository Layout

```
app/
  app.py                     # Streamlit entrypoint -- header/result, map, controls, click handling
  algorithm.py                # expand_contiguous, find_nearest_geoid -- framework-agnostic, unchanged
  data_loader.py               # DataStore / GeographyData -- st.cache_resource, lean tract loading
  requirements.txt            # (see repo root requirements.txt -- app has none of its own)
  components/
    map_view.py                # build_map() -- folium basemap + gradient + highlight + legend
    utils.py                   # fmt_dollar/fmt_full/fmt_num/parse_value, price_color, level/label constants

scripts/
  prepare_data.py              # Headless pipeline -- boundaries / tract / adjacency stages

tests/
  test_algorithm.py            # Synthetic-grid unit tests for expand_contiguous (no network)

.github/workflows/
  prepare_data.yml             # Census download + join + adjacency build, manual trigger, commits to data/
  ci.yml                       # Algorithm tests + app import smoke test on push/PR

.streamlit/
  config.toml                  # Orange accent theme (matches the map's selection highlight color)

data/                          # Committed except data/raw/ (gitignored, regenerated by prepare_data.py)
  state.geojson, county.geojson         # Full geometry + values, small
  tract.fgb                              # Geometry + GEOID only, simplified, size-capped
  tract_values.parquet                   # Tract attributes (values/enrichment/centroids/names)
  cache/{state,county,tract}_adjacency.pkl  # Precomputed adjacency graphs
  reference_values.csv                   # Target-value dropdown options, grouped by `category`
  educational_content.md                 # "About this tool" sidebar tab text
  scale_reference.md                     # "What does a dollar buy?" sidebar tab -- order-of-magnitude
                                          # home/neighborhood/metro scale reference

requirements.md                # Original pre-build requirements sketch (envisioned FastAPI/PostGIS/
                                # Leaflet+vector-tiles; shipped as Streamlit instead) -- historical
issues-and-new-requirements.md # Iteration 2 feedback -- historical, fully resolved
open-questions.md              # Iteration 3 open items -- historical, fully resolved
context-archive.md             # Resolved design decisions from all prior iterations (current source
                                # of truth for "why" on anything the three files above raised)
README.md                      # Architecture + local run + deploy instructions
```
