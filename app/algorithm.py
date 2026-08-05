"""
Core expansion algorithm for ResVal.

Given a mapspot (lat/lon), a target dollar value, and a geography level,
find the largest contiguous set of geographies expanding outward from the
mapspot whose total residential value does not exceed the target.
"""

import heapq
from dataclasses import dataclass, field

import numpy as np
from scipy.spatial import KDTree


@dataclass
class ExpansionResult:
    """Result of the contiguous expansion algorithm."""
    selected_geoids: list[str]
    total_value: float
    target_value: float
    num_selected: int
    remaining_budget: float
    furthest_distance_km: float
    # Enrichment stats for the selected area
    area_median_income: float = 0.0
    area_median_home_value: float = 0.0
    area_total_housing_units: float = 0.0
    median_houses_to_target: float = 0.0


def find_nearest_geoid(
    lat: float,
    lon: float,
    centroids: dict[str, tuple[float, float]],
) -> str:
    """Find the GEOID whose centroid is nearest to the given point."""
    geoids = list(centroids.keys())
    coords = np.array([centroids[g] for g in geoids])
    tree = KDTree(coords)
    _, idx = tree.query([lon, lat])
    return geoids[idx]


def haversine_km(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Great-circle distance between two points in kilometers."""
    R = 6371.0
    lat1_r, lat2_r = np.radians(lat1), np.radians(lat2)
    dlat = np.radians(lat2 - lat1)
    dlon = np.radians(lon2 - lon1)
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1_r) * np.cos(lat2_r) * np.sin(dlon / 2) ** 2
    return R * 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))


def compute_area_stats(
    selected: set[str],
    enrichment: dict[str, dict],
    target_value: float,
) -> tuple[float, float, float, float]:
    """Compute weighted area statistics for selected geographies."""
    total_units = 0.0
    weighted_income = 0.0
    weighted_home_value = 0.0

    for geoid in selected:
        e = enrichment.get(geoid, {})
        units = e.get("housing_units", 0)
        total_units += units
        weighted_income += e.get("median_income", 0) * units
        weighted_home_value += e.get("median_home_value", 0) * units

    if total_units > 0:
        area_median_income = weighted_income / total_units
        area_median_home_value = weighted_home_value / total_units
    else:
        area_median_income = 0.0
        area_median_home_value = 0.0

    median_houses = target_value / area_median_home_value if area_median_home_value > 0 else 0.0

    return area_median_income, area_median_home_value, total_units, median_houses


def expand_contiguous(
    start_geoid: str,
    target_value: float,
    values: dict[str, float],
    adjacency: dict[str, set[str]],
    centroids: dict[str, tuple[float, float]],
    mapspot_lon: float,
    mapspot_lat: float,
    enrichment: dict[str, dict] | None = None,
) -> ExpansionResult:
    """
    Greedy contiguous expansion from start_geoid.

    Always undershoots: never exceeds the target value.
    """
    selected = set()
    running_total = 0.0
    furthest_dist = 0.0

    # Check if start geography itself fits
    start_val = values.get(start_geoid, 0)
    if start_val > target_value:
        # Still compute houses-to-target using the start geography's median home value
        start_income = 0.0
        start_home_value = 0.0
        start_houses = 0.0
        if enrichment:
            e = enrichment.get(start_geoid, {})
            start_income = e.get("median_income", 0)
            start_home_value = e.get("median_home_value", 0)
            start_houses = target_value / start_home_value if start_home_value > 0 else 0.0
        return ExpansionResult(
            selected_geoids=[],
            total_value=0.0,
            target_value=target_value,
            num_selected=0,
            remaining_budget=target_value,
            furthest_distance_km=0.0,
            area_median_income=start_income,
            area_median_home_value=start_home_value,
            area_total_housing_units=0.0,
            median_houses_to_target=start_houses,
        )

    selected.add(start_geoid)
    running_total += start_val

    # Distance cache
    distances: dict[str, float] = {}

    def get_distance(geoid: str) -> float:
        if geoid not in distances:
            c = centroids[geoid]
            distances[geoid] = haversine_km(mapspot_lon, mapspot_lat, c[0], c[1])
        return distances[geoid]

    # Greedy expansion via a min-heap of (distance, geoid) frontier candidates,
    # nearest-first. Geography values are always >= 0, so running_total only
    # grows -- a candidate that doesn't fit under the current running_total can
    # never fit later, so a rejected candidate is discarded permanently rather
    # than re-considered (equivalent to re-sorting the whole remaining frontier
    # on every pass, just without redoing that sort).
    frontier: list[tuple[float, str]] = []
    in_frontier: set[str] = set()

    def push(geoid: str) -> None:
        if geoid not in selected and geoid not in in_frontier and geoid in values:
            heapq.heappush(frontier, (get_distance(geoid), geoid))
            in_frontier.add(geoid)

    for neighbor in adjacency.get(start_geoid, set()):
        push(neighbor)

    while frontier:
        dist, candidate = heapq.heappop(frontier)
        in_frontier.discard(candidate)

        candidate_val = values.get(candidate, 0)
        if running_total + candidate_val <= target_value:
            selected.add(candidate)
            running_total += candidate_val
            furthest_dist = max(furthest_dist, dist)

            for neighbor in adjacency.get(candidate, set()):
                push(neighbor)

    # Compute enrichment stats
    area_income = 0.0
    area_home_value = 0.0
    area_units = 0.0
    median_houses = 0.0
    if enrichment and selected:
        area_income, area_home_value, area_units, median_houses = compute_area_stats(
            selected, enrichment, target_value
        )

    return ExpansionResult(
        selected_geoids=sorted(selected),
        total_value=running_total,
        target_value=target_value,
        num_selected=len(selected),
        remaining_budget=target_value - running_total,
        furthest_distance_km=furthest_dist,
        area_median_income=area_income,
        area_median_home_value=area_home_value,
        area_total_housing_units=area_units,
        median_houses_to_target=median_houses,
    )
