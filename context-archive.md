# Context Archive

All resolved open questions and issues from previous iterations, archived for reference.

---

## Issues Identified (from issues-and-new-requirements.md)

1. Data using synthetic values and therefore unrealistic — must download and use actual Census Planning Database.
   - PDB columns: `Med_house_value_acs_17_21`, `tot_housing_units_acs_17_21`
2. Plotting of tract-level data is extremely slow — implement 3 speedup approaches.

## New Requirements (from issues-and-new-requirements.md)

1. Allow input of a custom value as the comparison
2. Ensure sidebar with navigation information can be collapsible
3. Provide additional collapsible display for educational content
4. Calculate average income and average new home price for selected area (from PDB)
5. Add wealth percentile reference values (median, 90th, 95th, 99th, 99.5th, 99.9th)
6. Identify # of median houses that sum to the threshold for highlighted area (national median if no area)
7. Use standard state/county names, not FIPS codes

---

## Resolved Open Questions (from open-questions.md)

### 1. PDB Column Mapping
**RESOLVED:** Use `tot_housing_units_acs_17_21` x `Med_house_value_acs_17_21`.

### 2. PDB Geography Coverage
**RESOLVED:** Use tract-level PDB directly. Aggregate to county/state.

### 3. Tract-Level GeoJSON Size
**RESOLVED:** Three speedups: zoom-gated display, viewport clipping, geometry simplification.

### 4. PDB Income and New Home Price Columns
**RESOLVED:** Use `Med_hhd_inc_acs_17_21` for income. `Med_house_value_acs_17_21` as home price proxy.

### 5. Reference CSV — Wealth Percentile Values
**RESOLVED:** Household net worth from Federal Reserve SCF 2022.

### 6. Median Houses Calculation
**RESOLVED:** Weighted average of `Med_house_value` across selected geographies (weighted by housing units). National median if no area selected.

### 7. Contiguity Definition
**RESOLVED:** Queen contiguity (edges + corners) via `intersects()`.

### 8. Greedy vs. Optimal Selection
**RESOLVED:** Greedy nearest-first is acceptable.

### 9. Geographic CRS
**RESOLVED:** Lat/lon is acceptable for teaching tool.

### 10. Startup Time / Adjacency Caching
**RESOLVED:** Cache adjacency graphs to disk (JSON/pickle).

### 11. Memory Usage
**Deferred:** Profile when deploying to cloud.

### 12. Cloud Platform Selection
**Deferred:** Decide at deployment time.

### 13. Color Scheme
**RESOLVED:** Neutral unselected (light gray), distinct highlight for selected.

### 14. Mobile Responsiveness
**RESOLVED:** Full mobile support — bottom sheet, touch-friendly, responsive breakpoints.

### 15. Educational Content
**RESOLVED:** Load from `data/educational_content.md`. Brief explanation of tool and wealth comparisons.

---

## Original Resolved Decisions (from requirements.md)

1. **Tolerance band:** Always undershoot. Never exceed target value.
2. **Tie-breaking:** Stop short. Never include geography that pushes sum past target.
3. **Contiguity:** Single contiguous region expanding from mapspot.
4. **Block-level:** Deferred to future iteration. MVP = states, counties, tracts.
5. **Reference CSV format:** Simple two-column (name, value), locally stored.
6. **Authentication:** None. Public teaching tool, low-cost cloud deployment.

---

## Iteration 2 Issues (from issues-and-new-requirements.md, round 2)

1. Too much clutter on right panel — restructure results layout
   - "How many houses could you buy?" section moved to top
   - Geography count renamed dynamically (Whole Counties, Whole Neighborhoods, etc.)
   - Detailed stats moved to bottom
2. Collapsible panel doesn't fully collapse — use hamburger menu, ensure map shows underneath
3. Remove GDP-related values from reference CSV
4. Tool title needs to be pithier — changed to "How rich are the rich, really?"
5. "About this tool" text too wordy — needs pithier tone

## Iteration 2 New Requirements

1. Choropleth overlay modes when no selection: median house price gradient (blue-yellow), total value, or no fill

---

## Iteration 2 Resolved Open Questions

### 1. High-Value Geographies and Small Targets
Noted — needs UX messaging when target < starting geography value.

### 2. PDB GEOID Vintage Alignment
Noted — minor mismatch, ~269 tracts. Document in UI.

### 3. County Boundary Join Gap
Noted — ~$490B gap from FIPS formatting. Minor impact.

### 4-10. (carried forward or deferred)
See current open-questions.md for remaining items.

---

## Iteration 3 (from open-questions.md) -- all now resolved

### 1. Tract Viewport Flickering
**RESOLVED.** `data_loader._round_bbox_out` caches tract geometry reads by
a coarsened bbox grid, so small pan jitters reuse the cached read instead
of re-fetching; combined with a fix to stop the map recentering to
`DEFAULT_CENTER` on every rerun, viewport panning no longer flickers.

### 2. Tract Viewport Payload Size
**Accepted, not fixed via canvas rendering.** Dense urban viewports (e.g.
NYC, ~500+ tracts) are still noticeably less snappy per pan than the
original Leaflet app's incremental DOM updates, because each pan is a full
Streamlit script rerun. Documented as a deliberate, bounded trade-off in
`CLAUDE.md`'s "Known UX deltas" section -- never a memory blowup, worst
case a slower rerun.

### 3. Startup Memory Profile
**RESOLVED by design.** Tract geometry (the only level too big to hold
fully in memory) is never loaded wholesale -- only attributes/adjacency
are resident, geometry is read on demand per viewport via a spatially
indexed `pyogrio` bbox read. This keeps memory bounded regardless of
national tract count, specifically for Streamlit Community Cloud's ~1GB
free tier. See `CLAUDE.md`'s "Data Layer" section.

### 4. PDB Data Freshness
**RESOLVED.** The app footer now displays a permanent caption: "Based on
2017-2021 Census estimates -- order-of-magnitude, not exact."

### 5. County Join Gap
**Still open, low priority.** The ~$490B state/county total mismatch from
FIPS formatting hasn't been investigated further. Minor impact on a
teaching tool; not blocking.

### 6. Very Small Wealth Values Produce Empty Results
**RESOLVED.** The app now shows fractional homes instead of a dead end --
"{target label} is smaller than a single {geography} here" plus "≈ 0.29
homes at local median price" -- instead of a bare "nothing fits" message.

### 7. Auto-Level Cascade in Expensive Areas
**RESOLVED.** The cascade (state → county → tract) now surfaces via
`st.toast` messages ("That single state exceeds $X. Switching to
counties...") so the brief delay during cascade is explained rather than
silent.

### 8. Very Large Values and State Coverage
**Accepted as inherent, not a bug.** The greedy contiguous-expansion
algorithm can leave a large remaining budget unspent rather than break
contiguity or exceed the target -- expected behavior for a teaching tool,
unchanged since Iteration 1's algorithm decisions.
