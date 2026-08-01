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
**range**, bounded by Zillow's national home-value tiers¹ — the typical
value of homes in the bottom third versus the top third of each local
market's own price distribution, tracked home-by-home and then aggregated
nationally:

- **Bottom-tier typical value ≈ \$200,000** (homes in the 5th-35th
  percentile of their local market) sets the *upper* bound on how much a
  given amount buys.
- **Top-tier typical value ≈ \$700,000** (homes in the 65th-95th
  percentile of their local market) sets the *lower* bound.

So "\$1M buys 1 to 5 homes" means: among the priciest homes nationally
that's barely more than one house, among the more modest ones, several.

Above the scale of a handful of houses, house counts stop being legible,
so larger amounts are expressed in geography-sized units instead — a
**block** (~10-20 homes)², a **neighborhood** (~1,000 households)², and a
**metro area** (~75,000 households)³.

## The scale

- **\$100K** — roughly a **seventh to half of a single home**.
- **\$1M** — about **1 to 5 homes** — in the priciest markets that's
  barely one house; in the more modest ones, a small handful.
- **\$10M** — about **14 to 50 homes**, roughly one to several city
  blocks.
- **\$100M** — roughly a **seventh to half of one neighborhood**
  (~143-500 homes).
- **\$1B** — about **1 to 5 neighborhoods**.
- **\$10B** — dozens of neighborhoods (~14-50) — roughly a **fifth to
  two-thirds of one metro area**.
- **\$100B** — about **2 to 7 metro areas**.
- **\$1T** — about **19 to 67 metro areas**, several dozen.

Notice the pattern repeats at every scale: \$100K is a fraction of a home,
and \$100M — a thousand times more — is that same fraction of a
*neighborhood*. The map above lets you see exactly which neighborhood, for
any amount you pick.

## Assumptions & limits

1. **These bounds now come from Zillow's home-value tiers, not this app's
   own tract data — and here's why that swap matters.** Earlier versions
   of this page bounded the range with the national 25th/75th percentile
   of this app's own tract-level *median* home values (~83,500 Census
   tracts, ACS 2017-2021). That's the wrong statistic for this job: a
   census tract's median nets out all the internal variation among the
   houses inside it, so the spread *between* tract medians is a
   compressed shadow of the true, much wider spread between individual
   homes nationally. Two houses in the same tract routinely differ by
   3-5x in value; a tract-median interquartile range never sees that.
   Zillow's bottom-tier and top-tier Home Value Index (ZHVI) figures fix
   this because they're built from individual homes' estimated values,
   ranked within their own local market, and *then* aggregated — a
   percentile band over houses, not over geographies. Current figures
   (mid-2026): bottom tier (5th-35th percentile) ≈ **\$200,000**, typical
   "all homes" ZHVI (35th-65th percentile, the market's overall midpoint)
   ≈ **\$370,000**, top tier (65th-95th percentile) ≈ **\$700,000** — this
   last figure is this page's softest input: no separately-published
   current top-tier dollar figure could be retrieved while updating this
   page, so it's estimated by applying Zillow's own recently-reported
   bottom-to-top tier ratio (roughly 3.2-3.8x across recent years) to the
   current bottom-tier value. Two residual caveats even with this better
   source: (a) each tier is a *within-region* percentile — a population-
   weighted blend of every market's own cheapest/priciest third, not a
   literal percentile of all ~86 million U.S. homes pooled together — so
   the true national spread is likely wider still; (b) prices move
   quickly and these figures will drift out of date the same way the old
   ACS-based ones did. Treat every count on this page as good to a factor
   of ~2, not a factor of ~1.2.
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
