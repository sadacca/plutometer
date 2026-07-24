"""
FastAPI backend for ResVal.
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .algorithm import expand_contiguous, find_nearest_geoid
from .data_loader import DataStore

store = DataStore()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load data on startup."""
    store.load_all()
    yield


app = FastAPI(title="ResVal", lifespan=lifespan)

STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


class ComputeRequest(BaseModel):
    lat: float
    lon: float
    target_value: float
    geo_level: str


class ComputeResponse(BaseModel):
    selected_geoids: list[str]
    selected_names: list[str]
    total_value: float
    target_value: float
    num_selected: int
    remaining_budget: float
    furthest_distance_km: float
    start_geoid_value: float  # value of the geography the user clicked on
    geo_level: str
    # Enrichment
    area_median_income: float
    area_median_home_value: float
    area_total_housing_units: float
    median_houses_to_target: float
    national_median_home_value: float
    national_median_houses_to_target: float


@app.get("/")
async def index():
    return FileResponse(str(STATIC_DIR / "index.html"))


@app.get("/api/reference-values")
async def get_reference_values():
    return store.reference_values


@app.get("/api/levels")
async def get_available_levels():
    return list(store.levels.keys())


@app.get("/api/boundaries/{geo_level}")
async def get_boundaries(geo_level: str):
    geojson_str = store.get_geojson_str(geo_level)
    if geojson_str is None:
        raise HTTPException(status_code=404, detail=f"Geography level '{geo_level}' not loaded")
    return Response(content=geojson_str, media_type="application/json")


@app.get("/api/boundaries/{geo_level}/viewport")
async def get_boundaries_viewport(
    geo_level: str,
    minx: float = Query(...),
    miny: float = Query(...),
    maxx: float = Query(...),
    maxy: float = Query(...),
):
    """Return boundaries clipped to a viewport bounding box (for tract level)."""
    geo_data = store.get_level(geo_level)
    if geo_data is None:
        raise HTTPException(status_code=404, detail=f"Geography level '{geo_level}' not loaded")
    geojson_str = geo_data.get_viewport_geojson((minx, miny, maxx, maxy))
    return Response(content=geojson_str, media_type="application/json")


@app.get("/api/educational-content")
async def get_educational_content():
    return {"content": store.educational_content}


@app.post("/api/compute-selection", response_model=ComputeResponse)
async def compute_selection(req: ComputeRequest):
    geo_data = store.get_level(req.geo_level)
    if geo_data is None:
        raise HTTPException(
            status_code=404,
            detail=f"Geography level '{req.geo_level}' not loaded",
        )

    start_geoid = find_nearest_geoid(req.lat, req.lon, geo_data.centroids)

    result = expand_contiguous(
        start_geoid=start_geoid,
        target_value=req.target_value,
        values=geo_data.values,
        adjacency=geo_data.adjacency,
        centroids=geo_data.centroids,
        mapspot_lon=req.lon,
        mapspot_lat=req.lat,
        enrichment=geo_data.enrichment,
    )

    # Resolve names for selected geographies
    selected_names = [geo_data.names.get(g, g) for g in result.selected_geoids]

    # National median houses calculation
    nat_median = store.national_median_home_value
    nat_houses = req.target_value / nat_median if nat_median > 0 else 0.0

    # Value of the starting geography (for auto-level switching)
    start_value = geo_data.values.get(start_geoid, 0)

    return ComputeResponse(
        selected_geoids=result.selected_geoids,
        selected_names=selected_names,
        total_value=result.total_value,
        target_value=result.target_value,
        num_selected=result.num_selected,
        remaining_budget=result.remaining_budget,
        furthest_distance_km=result.furthest_distance_km,
        start_geoid_value=start_value,
        geo_level=req.geo_level,
        area_median_income=result.area_median_income,
        area_median_home_value=result.area_median_home_value,
        area_total_housing_units=result.area_total_housing_units,
        median_houses_to_target=result.median_houses_to_target,
        national_median_home_value=nat_median,
        national_median_houses_to_target=nat_houses,
    )
