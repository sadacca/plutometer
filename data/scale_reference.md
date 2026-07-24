# What Does a Dollar Amount Actually Buy?

A dollar figure by itself doesn't mean much — is \$10 million a house or a
neighborhood? Depends entirely on where. Here's a rough translation: for
each order of magnitude, how much *residential real estate* does that
amount of money represent, expressed as a scale of geography instead of a
raw house count or a fraction with six zeroes in it.

**This whole page is order-of-magnitude, not precision** — see Assumptions
below for exactly where the soft spots are.

## The method

Home prices vary a lot by market, so each amount below is given as a
**range**, bounded by the national 25th and 75th percentile home value¹
(household-weighted across all ~83,500 U.S. Census tracts, ACS 2017–2021 —
the same data the map itself uses):

- **25th percentile ≈ \$148,000** (cheaper markets) sets the *upper* bound
  on how much a given amount buys.
- **75th percentile ≈ \$372,000** (pricier markets) sets the *lower* bound.

So "\$1M buys 3 to 7 homes" means: in the priciest quarter of the country
that's closer to 3, in the cheapest quarter closer to 7.

Above the scale of a handful of houses, house counts stop being legible,
so larger amounts are expressed in geography-sized units instead — a
**block** (~10-20 homes)², a **neighborhood** (~1,000 households)², and a
**metro area** (~75,000 households)³.

## The scale

- **\$100K** — roughly a **quarter to two-thirds of a single home**.
- **\$1M** — about **3 to 7 homes**, a handful.
- **\$10M** — about **27 to 68 homes**, roughly one to four city blocks.
- **\$100M** — roughly a **quarter to two-thirds of one neighborhood**
  (~270-680 homes).
- **\$1B** — about **3 to 7 neighborhoods**, a handful.
- **\$10B** — dozens of neighborhoods (~27-68) — roughly a **third to
  nearly all of one metro area**.
- **\$100B** — about **4 to 9 metro areas**.
- **\$1T** — about **36 to 90 metro areas**, several dozen.

Notice the pattern repeats at every scale: \$100K is a fraction of a home,
and \$100M — a thousand times more — is that same fraction of a
*neighborhood*. The map above lets you see exactly which neighborhood, for
any amount you pick.

## Assumptions & limits

1. **Percentile bounds are ACS estimates, not appraisals — and they lag
   current prices by more than a rounding error.** The \$148,000 /
   \$372,000 figures come from this app's own tract-level data — Census
   *American Community Survey* 5-year estimates, which carry margins of
   error (especially at the tract level) and are pegged to the 2017-2021
   survey window (effectively ~2019 price levels). Zillow's national
   typical home value (ZHVI) is running **~\$368,000-\$370,000 as of
   2026** — right around where this app's *75th-percentile, priciest-market*
   bound sits, not its median. National residential real estate's total
   value has followed the same path: Zillow put it at a record \$55.1
   trillion in September 2025, versus the \$41.5 trillion implied by
   summing this app's ACS-vintage tract data. In other words, prices
   nationally have risen roughly 40-60% since this data's vintage, so
   every home-count figure above is probably **overstated by a similar
   margin relative to today's market** — "\$1M buys 3 to 7 homes" is
   closer to "2 to 5 homes" at 2026 prices. Real local prices can also
   fall well outside this 25th-75th range regardless of vintage.
2. **"Block" and "neighborhood" are informal, round-number conventions**
   picked for this tool, not official Census geography. A real block or
   neighborhood varies enormously in size by city and density.
3. **The "~75,000 households per metro area" figure is a rough,
   unverified estimate**, not a sourced Census statistic — this
   environment couldn't reach live Census metro-population data to pin
   down an actual median. There are roughly 390 U.S. metro areas and the
   size distribution is heavily skewed by a few giants (metro New York is
   ~100x the size of a small one), so treat this as an anchor for scale,
   not a precise number.
