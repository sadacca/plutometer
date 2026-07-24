# Open Questions — Iteration 3

All UX/design questions resolved. Remaining items are implementation/deployment observations and edge cases discovered during integration testing.

---

## RESOLVED

- **Empty selection:** Auto-switch to next finer geography level when target < starting geography value.
- **Tract auto-zoom:** Auto-zoom to level 8 when tract is selected, with a brief banner.
- **Gradient overlay:** Blue-to-yellow, Leaflet map controls + legend, toggleable independently of selection state.
- **Custom input:** Support shorthand (K/M/B/T) and auto-format with commas.
- **Highlight color:** Orange (#F57C00) for selected geographies.
- **Overlay + selection:** Gradient stays visible behind selection highlight, configurable via toggle.

---

## REMAINING (implementation/deployment observations)

### 1. Tract Viewport Flickering
Debounce the viewport reload (300ms after movement stops) and keep old layer visible until new data loads. **Implemented in frontend — verify during manual testing.**

### 2. Tract Viewport Payload Size
Dense urban viewports return hundreds of features (e.g., NYC returns 539 tracts). Monitor browser performance; may need canvas rendering in a future iteration.

### 3. Startup Memory Profile
Profile RSS for cloud deployment (tract GeoDataFrame + adjacency in memory). Deferred until cloud deployment.

### 4. PDB Data Freshness
Current data is ACS 2017-2021 (2023 PDB). Display vintage in UI footer. Check for newer PDB releases at deployment time.

### 5. County Join Gap
~$490B gap between state and county totals due to FIPS formatting mismatch. Low priority, investigate if time permits.

---

## EDGE CASES (discovered during integration testing)

### 6. Very Small Wealth Values Produce Empty Results at All Levels
Median US Household Net Worth ($192,900) returns 0 tracts because every census tract's total residential value exceeds this amount. This is mathematically correct behavior — a single tract contains many homes. Consider:
- Adding a UX message: "This amount is less than the total home value of even the smallest neighborhood."
- Or: showing partial results with an explanatory note about the scale.

### 7. Auto-Level Cascade in Expensive Areas
Bezos net worth ($211B) returns 0 states near Boston because Massachusetts alone ($466B) exceeds this. The frontend auto-level switch cascades state → county → tract correctly, but the user may experience a brief delay during the cascade. Verify UX during manual testing.

### 8. Very Large Values and State Coverage
US National Debt ($34T) covers 40 states ($32.71T) but cannot include the 41st state without exceeding the target. The $1.29T remaining budget is larger than many states — this is inherent to the greedy algorithm's contiguous constraint. Acceptable behavior for a teaching tool.
