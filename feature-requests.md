# Feature Requests — Pending Review

> **Status: OPEN.** Unlike `requirements.md`, `issues-and-new-requirements.md`,
> and `open-questions.md` (all historical/resolved -- see `CLAUDE.md`), this
> file tracks requests that have been raised but not yet designed or
> scheduled. Move an item's write-up into `context-archive.md` once it ships
> or is explicitly rejected, per the existing convention.

---

## 1. Animated / Scrollable Intro (Skippable)

**Raised:** 2026-08-10

### The ask

The app's core interaction (click a spot, pick a dollar amount, see the
result) assumes a user who's comfortable exploring on their own. Plutometer's
whole point is making a categorical gap legible -- renting or carrying a
mortgage as the median household, vs. owning one or two houses as the
"locally rich," vs. owning all the residential real estate across whole
*states* as the very wealthiest -- and that gap is exactly the kind of thing
a guided sequence communicates better than a cold map. Requested: an intro
that plays automatically and steps through that scale jump before handing
control to the normal click-to-explore map, for a user who wouldn't
otherwise know what to click. It must be skippable/bypassable for anyone who
just wants the tool.

### Proposed narrative arc

Four steps, each widening the footprint on the map and stating what's being
compared, roughly:

1. **Median household** -- rents or holds a mortgage on a fraction of one
   home. (Anchor: existing median-home-value data, e.g. `data/scale_reference.md`'s
   home-price figures.)
2. **Richest on the block** -- owns a house or two outright, locally. Still
   legible in "houses" terms, not yet map-scale.
3. **Richest in the county** -- footprint jumps to owning a meaningful slice
   of county-wide residential value.
4. **Richest in the country** -- footprint jumps again to owning the
   residential real estate of multiple *whole states*, contiguous, on the
   map -- the same visual the app produces today for a reference value like
   Elon Musk's net worth.

Each step should animate the map's highlighted area growing (ideally reusing
`components/map_view.build_map()`'s highlight layer / the existing choropleth,
not a separate rendering path) rather than just swapping static screenshots,
so the *scale jump* is felt, not just read.

### Bypass requirement

Must be skippable at any point (a visible "Skip intro" / "Explore the map"
control from step 1 onward), and should not force a returning user through
it every session -- needs a decision on whether that's a one-time
`st.session_state` flag (resets on browser refresh, since Streamlit has no
durable per-visitor storage) or persistent (e.g. via `st.query_params` /
localStorage through a small custom component).

### Open questions for review (not yet decided)

- **Mechanism.** Streamlit has no native scrollytelling primitive. Candidates:
  - A step-indexed "Next" carousel (`st.session_state.intro_step`, re-render
    the map at each step) -- simplest, fully native, but is click-driven
    rather than "animating... without needing much interaction" as
    requested.
  - An auto-advancing sequence (timed `st.rerun()` loop or
    `st_autorefresh`-style component) -- closer to the ask, but needs care
    to stay interruptible (skip / pause) and not fight `st_folium`'s own
    rerun cadence.
  - A self-contained HTML/CSS/JS animation via `st.components.v1.html`
    (e.g. an embedded Leaflet or Canvas sequence, or even a scroll-driven
    CSS animation) that owns its own timing independent of Streamlit
    reruns, handing off to the real `st_folium` map on completion or skip.
    Most faithful to "animated," most implementation work, and a departure
    from the "no Streamlit-internal APIs beyond `data-testid`" restraint
    the app has held to so far (see CLAUDE.md's mobile-whitespace note).
  - Recommendation for review: prototype the auto-advancing carousel first
    (cheapest, reuses existing map code) before investing in a custom HTML
    component.
- **Data for "richest on the block."** Reference points 3 and 4 (county,
  country) map directly onto existing `data/reference_values.csv` /
  county-level aggregates. Point 2 ("richest on the block," owning a house
  or two) has no existing data source -- needs a concrete anchor (e.g. some
  multiple of local median home value) rather than a real named individual,
  since the app has no block-level wealth data.
- **Where it lives / first-load behavior.** Should the intro run
  automatically on first load (before controls render at all), live behind
  an explicit "Play intro" button in the sidebar, or both (auto-play once
  per session, replayable on demand)? First-load auto-play risks conflicting
  with the "map is the first thing seen on mobile" goal from CLAUDE.md's App
  Structure section.
- **Mobile performance.** CLAUDE.md already notes tract-level panning is
  "less snappy" under Streamlit's full-script-rerun model in dense
  viewports; an auto-advancing animation adds reruns on a timer, which
  needs a performance check on the free-tier Streamlit Cloud host before
  committing to that mechanism.

### TODO (once the above is resolved)

- [ ] Decide intro mechanism (carousel vs. timed auto-advance vs. custom
      HTML/JS component) -- see options above.
- [ ] Decide/define the "richest on the block" anchor value and where it's
      sourced from (new small dataset vs. derived multiple of local median).
- [ ] Design the four-step content (copy + which geography/highlight each
      step shows) and confirm it reuses `map_view.build_map()`'s highlight
      layer rather than a parallel rendering path.
- [ ] Implement the skip/bypass control, visible from step 1.
- [ ] Decide session persistence for "seen the intro" (session-only vs.
      durable) and implement.
- [ ] Wire completion/skip to hand off cleanly into the existing
      click-to-explore state (no stale `session_state` left over from intro
      steps).
- [ ] Manual test on a mobile viewport for both animation smoothness and the
      existing "map first" layout goal.
- [ ] Add/update tests if any new non-Streamlit-framework logic is extracted
      (e.g. a pure function computing the four steps' target values).
