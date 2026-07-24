# Requirements Sketch: Residential Value Choropleth Application

## Overview

A Python web application displaying an interactive choropleth map of the continental US. Users select a point on the map and a target dollar value (from a reference list). The system identifies the largest contiguous set of geographies, expanding outward from the mapspot, whose cumulative residential real estate value does not exceed the target, then colors those geographies on the map.

---

## Data Sources

### Census Planning Database (PDB)
- Format: XLS/CSV from the US Census PDB (ACS 2017-2021 vintage)
- **Required columns for core value:**
  - `tot_housing_units_acs_17_21` — total housing units per geography
  - `Med_house_value_acs_17_21` — median house value per geography
- **Derived value:** total residential value per geography = `tot_housing_units_acs_17_21` × `Med_house_value_acs_17_21`
- **Additional PDB columns for enrichment:**
  - `Med_hhd_inc_acs_17_21` — median household income (for selected area statistics)
  - `Med_house_value_acs_17_21` — also used as proxy for home price in area statistics
- Geography levels: state, county, tract (blocks deferred)
- Must be downloaded and pre-processed during data preparation (no synthetic values)
- Geographies with null/zero values should be included with a value of 0

### Reference CSV
- A simple two-column file: **name** (label) and **dollar value**
- Populates the target value selector in the UI
- Example row: `"Metro Chicago Equivalent", 485000000000`
- **Must include household net worth benchmarks (from Federal Reserve SCF 2022):**
  - Median US household net worth (~$192,900)
  - 90th percentile household net worth (~$1,880,000)
  - 95th percentile household net worth (~$3,790,000)
  - 99th percentile household net worth (~$13,680,000)
  - 99.5th percentile household net worth (~$30,220,000)
  - 99.9th percentile household net worth (~$118,410,000)
- Additional comparison values (billionaire net worths, budgets, etc.)
- **Exclude GDP-based values** from the reference CSV (removed per feedback)

### Geographic Boundaries
- TIGER/Line shapefiles or Census cartographic boundary files for all four levels
- Must be pre-tiled or served as vector tiles for performant rendering at each zoom level

---

## Core Algorithm

**Constraint: Always undershoot.** The selected set must never exceed the target value. The goal is the maximum contiguous set of geographies that sums to just under the target.

**Constraint: Contiguity.** All selected geographies must form a single connected region — each geography shares a boundary with at least one other geography in the set (queen contiguity — edges and corners).

1. User clicks a point on the map ("mapspot") and selects a target value from the reference list
2. Start with the geography containing (or nearest to) the mapspot
3. Maintain a frontier of candidate geographies: all geographies adjacent to the current selected set but not yet included
4. From the frontier, greedily add the nearest geography (by centroid distance to mapspot) whose value would not cause the running sum to exceed the target
5. Repeat until no frontier geography can be added without exceeding the target
6. Return the set of selected GEOIDs and their cumulative value
7. Color the selected geographies on the choropleth; optionally shade by distance band or contribution weight

**Note:** This is a greedy heuristic. Because a nearer geography with a large value may be skipped while a farther one with a smaller value is added, the frontier must track all adjacent candidates, not just the single nearest. Skipped geographies remain in the frontier and may be reconsidered as long as they stay adjacent to the selected set.

---

## Functional Requirements

### Map Display
- Zoomable, pannable map of the continental US (exclude AK, HI, territories or make them optional)
- Base layer (OpenStreetMap, CartoDB, or Mapbox tiles)
- Vector choropleth overlay drawn from geographic boundaries

### Geography Level Selector
- Toggle between: **States**, **Counties**, **Census Tracts**
- Census Blocks deferred to a future iteration
- Switching levels clears current selection and re-runs the algorithm if a mapspot and target are active

### Mapspot Placement
- Click-to-place a single marker on the map
- Display coordinates of the placed point
- Allow repositioning by clicking a new location (clears and re-runs)

### Target Value Selector
- Dropdown or searchable list populated from the reference CSV
- Display both the name and formatted dollar value
- Selecting a value triggers the algorithm if a mapspot is already placed
- **Custom value input:** allow the user to type in an arbitrary dollar amount as an alternative to the dropdown

### Result Display — Panel Layout (top to bottom)
1. **"How many houses could you buy?"** (primary section, at top of results):
   - Number of median-priced local homes that equal the total wealth (target ÷ local weighted median home value)
   - Number of median-priced national homes that equal the total wealth
   - Geographies selected count — labeled dynamically by level: "Whole States" / "Whole Counties" / "Whole Neighborhoods"
2. **Selection details** (below primary, can be collapsed or at bottom):
   - Total value, total wealth (renamed from "target value"), remaining budget, furthest distance
3. **Area statistics** (at bottom of panel):
   - Median household income for the selected area
   - Median home value for the selected area
   - Total housing units
- **Terminology:** throughout the UI, use "total wealth" instead of "target value"
- **Geography naming:** display state and county names (not FIPS codes) in results and tooltips

### Sidebar / UI Layout
- The sidebar must be **fully collapsible** via a hamburger menu icon, revealing the full map underneath
- An additional **collapsible educational content area** — pithier/shorter tone, not too wordy
- Educational content loaded from a markdown file (`data/educational_content.md`) for easy editing without code changes
- **Tool title:** "How rich are the rich, really?" (replaces "ResVal / Residential Value Choropleth Explorer")

### Choropleth Overlays
- Background color gradient overlay, toggled via a Leaflet map control widget:
  - Toggle between: **median house price** (blue-to-yellow gradient, high-to-low), **total residential value**, or **no fill**
  - Default: median house price gradient
  - Include a color legend on the map
- Overlay is **configurable via toggle** — user can show/hide the gradient independently of selection state
- When geographies **are selected**, the selected set is highlighted in **orange (#F57C00)** on top of the overlay
- **Auto-level switching:** when target value is less than the clicked geography's value, automatically switch to the next finer geography level and re-run

### Tract Behavior
- When "Tract" is selected at a low zoom level, **auto-zoom to level 8** and show a brief banner explaining why
- Debounce viewport reloading to reduce flickering during pan/zoom

### Custom Value Input
- Support **shorthand notation**: K (thousands), M (millions), B (billions), T (trillions)
- Also **auto-format with commas** for display readability

### Tract-Level Performance
Tract-level rendering (83,507 features) must be optimized. Three required approaches:
1. **Zoom-gated display:** only allow/render tract-level boundaries when the map is zoomed to an appropriate level
2. **Viewport clipping:** only send/render tracts visible in the current map viewport
3. **Geometry simplification:** serve simplified tract geometries to the client, reducing payload size

---

## Non-Functional Requirements

### Performance
- State and county levels: results in under 2 seconds
- Tract level: results in under 5 seconds for typical targets
- Block level: requires spatial indexing (R-tree / KD-tree); may need server-side viewport clipping and async computation with a loading indicator
- Pre-compute centroids for all geographies; store in a spatial index

### Deployment Model
- Develop and prototype locally for fast iteration
- Deploy to low-cost or free-tier cloud infrastructure (e.g., Fly.io, Railway, Render, Vercel + serverless backend)
- No authentication — public-facing URL for broad sharing as a teaching tool
- Must scale horizontally if adoption grows (stateless backend, pre-computed data, static assets on CDN)

### Data Storage
- **Option A**: PostGIS database with pre-loaded boundaries and PDB values (recommended for block-level scale)
- **Option B**: GeoParquet or GeoPackage files with in-memory spatial index (viable for tract level and above)
- **Option C**: Pre-computed static files (GeoJSON, PMTiles) served from a CDN with computation done client-side or via serverless functions — best fit for low-cost/no-cost deployment

### Scalability Concerns
- ~50 states, ~3,200 counties, ~85,000 tracts (MVP); ~11,000,000 blocks (future)
- At tract level, consider vector tiles or viewport-limited GeoJSON to manage payload size

---

## Suggested Technology Stack

| Layer | Technology |
|---|---|
| Backend framework | FastAPI or Flask |
| Spatial operations | GeoPandas, Shapely, scipy.spatial.KDTree |
| Database | PostgreSQL + PostGIS |
| Tile serving | Martin, pg_tileserv, or pre-generated .mbtiles |
| Frontend map | Leaflet or MapLibre GL JS |
| Choropleth rendering | GeoJSON overlay (small levels) / vector tiles (block level) |
| Data ingest | pandas (XLS + CSV parsing), ogr2ogr (shapefiles to PostGIS) |

---

## Data Pipeline (ETL)

1. **Ingest PDB XLS** — parse with pandas, extract GEOID + residential value columns per geography level
2. **Ingest TIGER/Line shapefiles** — load into PostGIS via ogr2ogr, indexed on GEOID
3. **Join** — associate PDB values with boundary geometries by GEOID
4. **Pre-compute centroids** — store lat/lon centroid per geography for distance calculations
5. **Build spatial index** — KD-tree or PostGIS GIST index on centroids
6. **Ingest reference CSV** — load into application config or a simple database table
7. **Generate vector tiles** — for block and tract levels, pre-generate .mbtiles or serve dynamically

---

## API Endpoints (sketch)

```
GET  /api/reference-values          → list of {name, value} from CSV
POST /api/compute-selection         → {lat, lon, target_value, geo_level} → {geoids[], total_value, count, radius_km}
GET  /api/boundaries/{geo_level}    → GeoJSON (state/county only; tracts+ via tile server)
GET  /tiles/{geo_level}/{z}/{x}/{y} → vector tiles for tract/block levels
```

---

## Open Questions / Decisions Needed

1. ~~**Tolerance band**~~ — **RESOLVED:** Always undershoot. The sum must never exceed the target value.
2. ~~**Tie-breaking**~~ — **RESOLVED:** Stop short. Never include a geography that would push the sum past the target.
3. ~~**Contiguity**~~ — **RESOLVED:** Selected geographies must form a single contiguous region expanding outward from the mapspot.
4. ~~**Block-level feasibility**~~ — **RESOLVED:** MVP includes states, counties, and tracts only. Census blocks deferred to a future iteration.
5. ~~**PDB field mapping**~~ — **RESOLVED:** Use `tot_housing_units_acs_17_21` × `Med_house_value_acs_17_21`. Enrichment: `Med_hhd_inc_acs_17_21` for income; `Med_house_value` doubles as home price proxy.
6. ~~**Reference CSV format**~~ — **RESOLVED:** Simple two-column CSV (name, dollar value), comma-delimited, stored locally and manually updated. Stretch goal: programmatic updates to this file.
7. ~~**Authentication/multiuser**~~ — **RESOLVED:** No authentication. Public-facing teaching tool. Develop locally for prototyping, deploy to low/no-cost cloud resources (e.g., Fly.io, Railway, Render, or a static frontend + serverless API). Must be shareable via URL and scalable quickly if adoption grows.
8. ~~**Contiguity type**~~ — **RESOLVED:** Queen contiguity (edges + corners). Current `intersects()` approach is fine.
9. ~~**Algorithm optimization**~~ — **RESOLVED:** Greedy nearest-first is acceptable for the teaching tool.
10. ~~**Geographic CRS**~~ — **RESOLVED:** Lat/lon is acceptable. Minor distortion is fine.
11. ~~**Adjacency caching**~~ — **RESOLVED:** Pre-compute and cache adjacency graphs to disk. Load from cache on subsequent startups.
12. ~~**Color scheme**~~ — **RESOLVED:** Neutral (light gray) unselected geographies. Selected geographies highlighted with distinct color.
13. ~~**Mobile responsiveness**~~ — **RESOLVED:** Full mobile support required — bottom sheet layout, touch-friendly controls, responsive breakpoints.
14. ~~**Educational content**~~ — **RESOLVED:** Load from markdown file (`data/educational_content.md`). Brief explanation of tool purpose and wealth comparisons.
15. ~~**Cloud platform**~~ — **RESOLVED (deferred):** Decide at deployment time.
