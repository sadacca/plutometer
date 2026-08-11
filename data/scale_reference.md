# What Does a Dollar Amount Actually Buy?

A dollar figure by itself doesn't mean much -  is \$10 million a house or a
neighborhood? Depends entirely on where. Here's a rough translation: for
each order of magnitude, how much *residential real estate* does that
amount of money represent, expressed as a scale of geography instead of a
raw house count or a fraction with six zeroes in it. 

**This whole page is order-of-magnitude, not precision** see Assumptions
below for exactly where the soft spots are.

## The method

Home prices vary a lot by market, with so each amount below is given as a
**range**, bounded by the national 25th and 75th percentile of *individual*
home values¹, not geography-level medians, but where a single house
actually sits among all ~86.6 million owner-occupied homes nationally
(Census ACS 2024) - this clearly ignores the largest most expensive homes 
that might be appealing with a fortune (e.g. a $100M home) but allows a more 
consistent scale:

- **25th percentile ≈ \$209,000** (cheaper individual homes) sets the
  *upper* bound on how much a given amount buys.
- **75th percentile ≈ \$604,000** (pricier individual homes) sets the
  *lower* bound.

So "\$1M buys 2 to 5 homes" means: among pricier individual homes that's
closer to 2, among more modest ones, closer to 5.

Above the scale of a handful of houses, house counts stop being legible,
so larger amounts are expressed in geography-sized units instead: a
**block** (~10-20 homes)², a **neighborhood** (~1,000 households)², and a
**metro area** (~75,000 households)³.

## The scale

- **\$100K**: roughly a **sixth to half of a single home**.
- **\$1M**: about **2 to 5 homes**, a small handful.
- **\$10M**: about **17 to 48 homes**, roughly one to several city
  blocks.
- **\$100M**: roughly a **sixth to half of one neighborhood**
  (~166-478 homes).
- **\$1B**: about **2 to 5 whole neighborhoods**.
- **\$10B**: dozens of neighborhoods (~17-48), roughloy a **fifth to
  two-thirds of one whole metro area**.
- **\$100B**: about **2 to 6 whole metro areas**.
- **\$1T**: **dozens of metro areas or several whole states**.

Notice the pattern repeats at every scale: \$100K is a fraction of a home,
and \$100M, a thousand times more, is that same fraction of a whole
*neighborhood*. The map display lets you see exactly which neighborhood, for
any amount you pick.

## Assumptions & limits

1. **These bounds come from a real national histogram of individual homes,
   not a percentile of geography-level medians or market tiers — and it's
   worth being honest about how that changed the numbers.** The original
   version of this page used the 25th/75th percentile of this app's own
   tract-level *median* home values (~83,500 Census tracts) — the wrong
   statistic, since a tract median nets out the variation among the houses
   inside it. A later version switched to Zillow's within-market home-value
   tiers (bottom/top third of each local market, aggregated nationally),
   which fixed the "median of medians" problem but is still a percentile
   *within each market*, not a literal percentile of all homes pooled
   together nationally. This version uses Census ACS Table B25075
   ("Value"), which reports, for the nation as a whole, how many
   owner-occupied homes fall into each of 26 value bins from "less than
   \$10,000" up to "\$2,000,000 or more" — a genuine nationally-pooled
   histogram of ~86.6 million individual homes. Percentiles are
   interpolated linearly within bins: **5th ≈ \$50,000, 10th ≈ \$98,000,
   25th ≈ \$209,000, median ≈ \$361,000, 75th ≈ \$604,000, 90th ≈
   \$934,000, 95th ≈ \$1,351,000** (2024 1-year estimates, the most recent
   available; the 99th percentile can't be pinned down because the top bin
   is open-ended at "\$2,000,000 or more," which holds about 2.2% of all
   owner-occupied homes). Two things worth flagging plainly: **the
   resulting 25th-75th band ($209K-$604K) is actually a bit *narrower*
   than the Zillow-tier band this page used previously ($202K-$718K)**,
   not wider — Zillow's "top-third typical value" is the median of the
   top third of each market, which behaves more like the *83rd*
   percentile of the whole distribution than the 75th, so the two
   figures were never quite measuring the same thing. This version's
   number is the more literally correct answer to "25th/75th percentile
   of individual homes," even though it happens to be the narrower one.
   And **the true full spread is far wider than any quartile band shows**
   — the 10th-90th percentile alone runs \$98,000 to \$934,000, nearly a
   10x span, and ACS home values are owner-*reported* estimates rather
   than appraisals or sale prices, which tend to run high at the cheap end
   and low at the expensive end relative to true market value, likely
   compressing this distribution somewhat versus reality. Every count on
   this page should be read as illustrative of a plausible middle range,
   not as bounding the extremes.
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
