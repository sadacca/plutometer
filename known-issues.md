# Known Issues — Active, Needs a Live Browser

> **Status: unresolved, blocked on tooling.** Everything below was diagnosed and
> attempted in a sandboxed session with no live-browser access (outbound network
> policy blocks `cdn.jsdelivr.net`, which is where Leaflet's own JS loads from --
> `st_folium`'s iframe never initializes there). Every fix in this file was reasoned
> from source (Python + the compiled `streamlit_folium` frontend bundle) and verified
> only via unit-level Python checks, never by actually clicking around a running app.
> Two of the four rounds below made things measurably worse in real use. **Don't
> attempt another blind fix here** -- get this in front of a session with a real
> browser (Playwright with working network access, or a human tester) before touching
> it again.

## The problem

On the main map (not the intro tour, which has no live pan/zoom to preserve), manual
zoom and pan don't behave the way a normal map does:

- A zoom or pan action doesn't reliably "stick" -- the view can appear to revert
  toward wherever it was before, especially under rapid successive actions.
- Zooming out from a close-in (tract-level) view back toward a nationwide view is
  disproportionately hard -- multiple zoom-out actions in quick succession collapse
  down to only about one level of real progress.

## Why (root cause, high confidence)

`streamlit_folium` keys its `st_folium()` component instance off a hash of the
*rendered map's own JS* (`generate_js_hash` in `streamlit_folium/__init__.py`), not a
stable widget id. `app.py`'s `build_map()` call bakes `st.session_state.map_center`/
`map_zoom` directly into `folium.Map(location=..., zoom_start=...)`, and those values
change on every zoom tick or pan. So **every** such action changes the hash, which
Streamlit's custom-component protocol treats as an entirely different component --
full unmount, fresh Leaflet instance, no memory of what the user just did.

Compounding this: within a single Streamlit rerun, `build_map()` (which needs a zoom
value) necessarily runs *before* `st_folium()` returns this rerun's own freshly
reported zoom -- there's no way to use "the zoom that just triggered this rerun" to
build the map *in that same rerun*. So every remount is built from whatever zoom
Python captured one render behind. Under rapid input, each remount can partially
overwrite the user's further progress, which is the mechanism behind "2-3 zoom-outs
only net ~1 level."

Separately: the app deliberately does not track live pan/bounds at all (see the
`st_folium()` call's own comment in `app.py`) -- an explicit, already-diagnosed
decision from earlier development, because watching "center"/"bounds" as a
`returned_objects` trigger caused a real infinite-rerun loop (remounting reports
slightly different bounds each time from container-size timing / projection
rounding, which reads as a new pan, triggering another remount, forever). That
constraint is real and shouldn't be relaxed without a way to test for the loop
actually recurring.

## What's been tried, in order

1. **Capture zoom from `map_data`, force an extra `st.rerun()` on mismatch** (so the
   *next* rerun starts with the corrected value already in session state). Result:
   zoom read as "stuck too deep," and rapid zoom-out clicks caused visible
   snap-to-intermediate-state lag. Diagnosis: doubles the number of reruns needed to
   settle per zoom tick (the natural auto-rerun from watching `"zoom"`, *plus* this
   forced one), which falls behind under rapid input.

2. **Fixed `folium.Map()` view (constant `DEFAULT_CENTER`/`DEFAULT_ZOOM`) + asserting
   the live position separately via `st_folium(fig, zoom=..., center=...)`** --
   documented by the library as a non-reloading `setView()` rather than a remount.
   Theoretically the correct fix per the library's own docs and compiled frontend
   source (`window.map.setView(new_center, new_zoom)` when the passed props differ
   from `window.__GLOBAL_DATA__.last_zoom/last_center`). **Result in practice: the
   worst regression of the four rounds** -- zoom overshooting several levels past
   intended, occasional resets to the full nationwide default view, the map going
   unresponsive, and (at county level, zooming in) resets to a wrong centroid. Reverted
   immediately. Leading suspect: some feedback loop between the asserted props and
   Leaflet's own view-change reporting (animation easing or zoom-snap rounding during
   `setView()` causing the reported zoom to never cleanly settle, triggering repeated
   reassertion) -- **never confirmed, would need browser devtools on the actual JS
   execution to diagnose properly.**

3. **Revert to the simple baseline**: `build_map()` takes `center`/`zoom` straight
   from session state, baked into `folium.Map()` every render; no forced rerun, no
   `st_folium` `zoom=`/`center=` assertion. Stable (no crashes), but has the original
   "trapped while zooming out" symptom described above -- this is the current state
   of the code.

4. **Bucket the zoom used for rendering** (`_render_zoom()`, grouping zoom into
   3-level chunks so nearby zoom levels reuse the same render, cutting remount
   frequency ~3x) while leaving threshold checks (`TRACT_MIN_ZOOM`,
   `MAIN_MAP_PARTIAL_MATCH_ZOOM`, `COUNTY_FULL_ZOOM_MAX`) on the precise zoom.
   Deliberately didn't touch the live-view mechanism at all, to avoid round 2's
   failure mode. **Result: new problems** -- the map now starts more zoomed out than
   intended (the bucket floor can land below `TRACT_MIN_ZOOM` even when the precise
   zoom is above it), and zooming in from there could overshoot back out past the
   tract-render threshold instead of settling. Reverted.

**Current state of the code: back to attempt 3's baseline.** The "trapped zooming
out" issue is a known, unresolved limitation, not silently fixed.

## Where to pick this up

- `app/app.py`: `build_map()` call inside `with st.container(key="pm-map"):`, the
  `st_folium()` call right after it (long comment there explains the
  center/bounds-watching constraint), and the `if map_data:` block below the controls
  section (zoom capture).
- `/usr/local/lib/python3.11/dist-packages/streamlit_folium/frontend/build/static/js/main.*.js`
  (or wherever it's installed) has the actual `setView`/`last_zoom`/`last_center`
  logic referenced above -- worth stepping through with real devtools, not just
  `grep`.
- Concrete next steps that need a live browser:
  1. Reproduce round 2's crash directly, with devtools open, to see what
     `window.__GLOBAL_DATA__` and `window.map.getZoom()` actually do across a rapid
     zoom sequence -- confirm or rule out the animation/rounding feedback-loop theory.
  2. If confirmed, try `st_folium`'s `zoom=`/`center=` assertion again but only
     passing a value when this session has an *intentional* reason to force a jump
     (new click, an auto-zoom bump) -- `None` otherwise -- rather than asserting the
     live-tracked value unconditionally on every render, which is what round 2 did.
  3. Consider whether pinning/upgrading `streamlit-folium` changes this behavior --
     current version at time of writing is 0.27.4.
  4. As a fallback if none of the above pans out safely: a small custom Leaflet
     component built specifically for this app's needs (pan/zoom persisted entirely
     client-side, syncing back to Python only on click) would sidestep the whole
     remount-on-every-interaction problem, at the cost of maintaining custom
     frontend code this repo doesn't currently have any of.
