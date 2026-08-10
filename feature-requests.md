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

### Proposed narrative arc (revised 2026-08-10 -- see discussion below)

**The reframe.** Presenting a household's *net worth* as if it were
spendable overstates what most people at, say, the 90th percentile
($1.9M) actually experience -- that figure is dominated by home equity and
retirement accounts, not liquid cash. Net worth-to-real-estate is exactly
the hypothetical the rest of the app already runs on for the wealthy
comparisons (turn a dollar figure entirely into contiguous property), so
the intro should introduce that hypothetical explicitly rather than
implying the median household could or would liquidate everything into
housing. Proposed framing, as a beat *before* the four wealth-tier steps:

- **Outcome A -- how housing spending actually works.** A common
  budgeting rule of thumb (~30% of income) going to rent or a mortgage
  payment -- a normal, small slice of one home. This is the "sane"
  baseline.
- **Outcome B -- the premise the rest of the tool runs on.** Pose the
  hypothetical directly: "what if, instead, every dollar someone had went
  into real estate?" Apply that to the median household's *full net
  worth* first (still sub-one-house or a small fraction of one, depending
  on local prices) to establish the rule cleanly before scaling it up
  across the wealth tiers below. This is also the moment to be explicit
  that net worth isn't sitting in a checking account -- the hypothetical
  is a deliberate exaggeration used for comparison, not a claim about how
  people actually live.

Then the four wealth-tier steps, each widening the footprint and applying
the same "100% into real estate" premise:

1. **Median household** ($192,084, SCF 2022) -- Outcome A/B beat above.
2. **Richest on the block** -- anchored to a national percentile as a
   round, sourced number (90th percentile = $1,920,758, SCF 2022) framed
   as "a comfortably wealthy neighbor," not literally computed as the
   single richest resident of any specific block. (See "Percentile
   research" below -- a literal order-statistic reading of "richest of
   ~50-300 households" actually lands far higher, $6M-$25M, but a clean
   percentile is more legible and leaves more visual room before the
   final jump.)
3. **Richest in the county** -- recommend 99.9th percentile (~$46.4M)
   over 99th (~$13.7M) -- still a clean sourced number, but closer to
   what a real county's actual richest resident looks like, and it
   preserves a visible step before the final jump.
4. **Richest in the country** -- the residential real estate of multiple
   *whole states*, contiguous, on the map -- the same visual the app
   produces today for a reference value like Elon Musk's net worth.

Each wealth-tier step should animate the map's highlighted area growing
(ideally reusing `components/map_view.build_map()`'s highlight layer / the
existing choropleth, not a separate rendering path) rather than just
swapping static screenshots, so the *scale jump* is felt, not just read.

#### Percentile research (baseline, done 2026-08-10)

SCF 2022 net worth by percentile: 50th $192,084 -- 75th $658,340 -- 90th
$1,920,758 -- 95th $3,779,600 -- 99th ~$11.1M-$13.7M (SCF-survey vs. Fed
Distributional Financial Accounts estimates differ slightly) -- 99.9th
~$46.4M. A literal "richest person in a group of N households" is an
order statistic, not a fixed percentile -- with wealth's fat right tail
(Pareto tail exponent ~1.47, per the literature), the *expected* richest
of N households scales roughly as N^0.68. Extrapolating from the sourced
percentiles above: richest-of-~10 households ~ 90th pct ($1.9M),
richest-of-~100 ~ 99th pct (~$13.7M), richest-of-1,500 (a census tract)
~ $60M, richest-of-10,000 (a median county) ~ $220M, richest of a large
urban county (e.g. LA, ~3.5M households) ~ $12B, richest-of-131M (the
whole US) ~ $100B-$1T (matches actual order of magnitude for the current
wealthiest American). Conclusion: round SCF percentiles (90th / 99.9th
recommended above) understate a literal reading, especially at the county
step, but are the right pedagogical choice over exact order-of-magnitude
figures -- those compress "block" and "county" into the same tens-of-millions
range and dump the entire dramatic jump into the last step alone.

### Visual treatment for the sub-house steps

The median-household step (and arguably "richest on the block," in cheap
markets) resolves to a fraction of one home or a small handful of houses --
too small to register as a shape on a choropleth map at any zoom level, so
the map-highlight treatment that works for steps 3-4 doesn't work here.
Needs either a dedicated graphic (e.g. a house icon, partially filled or in
a small icon grid, to show "0.08 of a house" / "2 houses" concretely) or a
strong text-first treatment for these steps, with the map only becoming the
primary visual once the footprint is large enough to show. The app already
has `components/utils.fractional_headline()` producing exactly this
"part of a house" / "a few houses" phrasing for the main result card --
the intro's early-step language should reuse it rather than inventing new
copy, and the graphic (if built) should be driven by the same house-count
math already used there.

### Starting location & replay

Requested: the intro should open on a concrete, named place rather than a
blank map -- Pittsburgh, PA suggested as a default (a legible, mid-size,
non-coastal metro, which also keeps the "national median" framing from
reading oddly against one of the most expensive markets). Replay for a
different place is wanted too, with two options raised for how to pick one:

- **A curated list** (e.g. top 25 metros) -- bounded, simple `st.selectbox`,
  no new data needed if the list is hand-maintained similarly to
  `data/reference_values.csv`.
- **Free-text city/county autocomplete** -- richer, but the app has no
  city-name-to-location index today (confirmed: nothing in `app/` does
  geocoding or name lookup; `data_loader` is GEOID-keyed, not name-keyed).
  County-level free text is cheap by comparison, since `state.geojson` /
  `county.geojson` already carry human-readable `NAME` fields (per the
  Iteration 2 fix noted in `context-archive.md`) -- but full city-level
  search would need a new dataset (e.g. the Census Gazetteer places file)
  and a name → lat/lon → containing-geography lookup that doesn't exist
  in the pipeline yet. Recommend starting with the curated-list or
  county-name-dropdown option and treating full city autocomplete as a
  later increment if it's wanted.

### Bypass requirement

Must be skippable at any point (a visible "Skip intro" / "Explore the map"
control from step 1 onward), and should not force a returning user through
it every session -- needs a decision on whether that's a one-time
`st.session_state` flag (resets on browser refresh, since Streamlit has no
durable per-visitor storage) or persistent (e.g. via `st.query_params` /
localStorage through a small custom component).

### Open questions for review (not yet decided)

- **Mechanism -- DECIDED (2026-08-10): start with the carousel.** A
  step-indexed "Next" carousel (`st.session_state.intro_step`, re-render at
  each step) -- simplest, fully native, reuses existing map code. It's
  click-driven rather than fully hands-off, which is a conscious downgrade
  from "animating... without needing much interaction" in the original
  ask, but it's the cheapest way to validate the content/arc before
  investing in a timed auto-advance or a custom HTML/JS component (both
  still open as later increments if the carousel proves the concept but
  feels too manual).
- **Anchor values -- informed by research above, not fully decided.**
  Median ($192,084), block (90th pct, $1.92M), county (recommend 99.9th
  pct, $46.4M over 99th's $13.7M -- see percentile research above),
  country (actual current top individual net worth, already handled by
  `data/reference_values.csv`). Still open: whether "richest on the
  block" needs its own small dataset or stays a flat national-percentile
  number reused everywhere (simpler, but less local -- doesn't vary with
  the replay location below).
- **Where it lives / first-load behavior.** Should the intro run
  automatically on first load (before controls render at all), live behind
  an explicit "Play intro" button in the sidebar, or both (auto-play once
  per session, replayable on demand)? First-load auto-play risks conflicting
  with the "map is the first thing seen on mobile" goal from CLAUDE.md's App
  Structure section.
- **Mobile performance.** CLAUDE.md already notes tract-level panning is
  "less snappy" under Streamlit's full-script-rerun model in dense
  viewports; even a click-driven carousel adds a rerun per step, which is
  fine, but a future auto-advance timer needs a performance check on the
  free-tier Streamlit Cloud host before committing to that mechanism.
- **Outcome A/B beat as a real step or framing copy only?** Does "how
  housing spending actually works" (30%-of-income baseline) need its own
  carousel step with a visual, or can it be a sentence of framing copy
  that precedes the median-household step? A full step is more
  deliberate pacing; folding it into copy is less to build.
- **Per-location recompute cost.** Steps 2-4 (or just 3-4, depending on
  the answer to "anchor values" above) will need target values and
  contiguous-expansion results computed for whichever place the carousel
  opens on -- cheap for state/county (already fully in memory per
  `data_loader.py`), more work for a tract-level highlight if any step
  wants tract-scale detail, per the tract-viewport-read design in
  `data_loader.py`.

### TODO (once the above is resolved)

- [ ] Build the carousel mechanism (`st.session_state.intro_step`,
      Next/Back/Skip controls), reusing `map_view.build_map()`'s highlight
      layer for steps that have a map-scale footprint.
- [ ] Write the Outcome A/B framing beat (30%-of-income baseline vs. "every
      dollar into real estate" premise) and decide whether it's a
      standalone step or lead-in copy.
- [ ] Build the sub-house visual (house icon / icon grid) for the
      median-household and (in cheap markets) block steps, driven by the
      same house-count math as `components/utils.fractional_headline()` --
      reuse that function's phrasing rather than duplicating it.
- [ ] Finalize the block/county anchor values (90th / 99.9th percentile
      recommended above, or a decision to source them differently) and add
      them wherever `reference_values.csv`-style constants live.
- [ ] Implement the default starting location (Pittsburgh, PA) and the
      replay picker -- start with a curated metro list (`st.selectbox`,
      hand-maintained like `reference_values.csv`) rather than free-text
      city autocomplete, which needs a new geocoding dataset not in the
      pipeline today (see "Starting location & replay" above). County-name
      dropdown is a cheap middle ground since `county.geojson` already has
      `NAME` fields.
- [ ] Implement the skip/bypass control, visible from step 1.
- [ ] Decide session persistence for "seen the intro" (session-only vs.
      durable) and implement.
- [ ] Wire completion/skip to hand off cleanly into the existing
      click-to-explore state (no stale `session_state` left over from intro
      steps), landing on whichever location the intro used.
- [ ] Manual test on a mobile viewport for layout and rerun responsiveness.
- [ ] Add/update tests if any new non-Streamlit-framework logic is
      extracted (e.g. a pure function computing the step target values, or
      the housing-spend-vs-net-worth calculation for the Outcome A/B beat).
