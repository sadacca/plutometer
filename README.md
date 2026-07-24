# plutometer -- "How rich are the rich, really?"

An interactive choropleth teaching tool. Click a spot on the map, pick a
dollar amount (a household net worth percentile, a billionaire's net worth,
the US national debt, ...), and see the largest contiguous set of states,
counties, or neighborhoods (Census tracts) whose combined residential
real-estate value doesn't exceed it -- without ever going over.

## Architecture

- **App**: Streamlit (`app/app.py`), map interaction via `streamlit-folium`.
  Deployed for free on **Streamlit Community Cloud**, which auto-deploys from
  `main` on every push -- there's no separate deploy step.
- **Data**: Census cartographic boundaries (TIGER/Line) + the Census Planning
  Database (ACS 2017-2021 vintage) are downloaded, joined, and committed to
  `data/` by a GitHub Actions workflow (`.github/workflows/prepare_data.yml`),
  **not** at app runtime -- Streamlit Cloud only serves a static repo
  checkout, it can't run a 20+ minute nationwide Census join at boot. See
  `CLAUDE.md` for the full file inventory and pipeline stages.
- **CI**: `.github/workflows/ci.yml` runs the algorithm's unit tests and an
  import smoke test on every push/PR -- the "build" gate before Streamlit
  Cloud's auto-deploy picks up a merge to `main`.

```
Census TIGER/PDB --> prepare_data.yml (GitHub Actions) --> data/*.geojson, tract.fgb,
                                                             tract_values.parquet, cache/*.pkl
                                                             (committed to git)
                                                                    |
                                                                    v
                                          Streamlit Community Cloud reads data/ from main
```

## Local development

```bash
pip install -r requirements.txt
streamlit run app/app.py
```

State and county boundaries are committed to `data/` already, so the app
runs out of the box at those two levels. Tract (neighborhood) level needs the
data pipeline to have been run at least once (see below) -- until then the
geography-level selector just won't offer "Neighborhood (tract)".

## Regenerating the data

```bash
python scripts/prepare_data.py --stage boundaries   # state + county
python scripts/prepare_data.py --stage tract         # tract geometry + values
python scripts/prepare_data.py --stage adjacency     # precomputed adjacency graphs (all 3 levels)
python scripts/prepare_data.py                       # all three stages, in order
```

In CI, `prepare_data.yml` (manual `workflow_dispatch` trigger) runs all three
stages and commits each stage's output to the repo as soon as it succeeds.
Run it once before the first deploy, and again whenever the Census publishes
a new PDB vintage.

## Deploying (one-time manual step)

Streamlit Community Cloud deploys are configured via its own UI, not a
GitHub Action:

1. Make sure `data/` has at least the state/county files committed on `main`
   (ideally tract too -- run `prepare_data.yml` first).
2. At [share.streamlit.io](https://share.streamlit.io), connect this
   repository and set the main file path to `app/app.py`.
3. No secrets are required -- the basemap tiles (CARTO/OpenStreetMap) are
   free and keyless.

After that, every push to `main` redeploys automatically.

## Requirements

No secrets, no authentication. Data sources, algorithm details, and design
decisions are in `requirements.md` and `context-archive.md`. Developer-facing
architecture notes are in `CLAUDE.md`.
