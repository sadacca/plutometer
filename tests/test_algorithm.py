"""
Unit tests for app/algorithm.py -- no network, no data files needed.

Uses a synthetic 3x3 grid of geographies (queen contiguity) to check the two
invariants the algorithm promises (requirements.md): it never exceeds the
target ("always undershoot"), and the selected set is always a single
contiguous region expanding from the click point.
"""

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))

from algorithm import expand_contiguous, find_nearest_geoid  # noqa: E402

GRID = [
    ["A", "B", "C"],
    ["D", "E", "F"],
    ["G", "H", "I"],
]


def _make_grid(seed: int = 0, value_range: tuple[int, int] = (5, 20)):
    rng = random.Random(seed)
    centroids: dict[str, tuple[float, float]] = {}
    adjacency: dict[str, set[str]] = {}
    values: dict[str, float] = {}
    enrichment: dict[str, dict] = {}

    positions = {}
    for r, row in enumerate(GRID):
        for c, geoid in enumerate(row):
            positions[geoid] = (r, c)
            centroids[geoid] = (c * 1.0, -r * 1.0)  # (lon, lat)
            values[geoid] = float(rng.randint(*value_range))
            units = rng.randint(1, 100)
            enrichment[geoid] = {
                "housing_units": units,
                "median_home_value": rng.randint(100_000, 500_000),
                "median_income": rng.randint(30_000, 150_000),
            }

    for geoid, (r, c) in positions.items():
        neighbors = set()
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if dr == 0 and dc == 0:
                    continue
                nr, nc = r + dr, c + dc
                if 0 <= nr < len(GRID) and 0 <= nc < len(GRID[0]):
                    neighbors.add(GRID[nr][nc])
        adjacency[geoid] = neighbors

    return values, adjacency, centroids, enrichment


def _is_contiguous(selected: set[str], adjacency: dict[str, set[str]], start: str) -> bool:
    if not selected:
        return True
    assert start in selected
    seen = {start}
    frontier = [start]
    while frontier:
        node = frontier.pop()
        for neighbor in adjacency.get(node, set()):
            if neighbor in selected and neighbor not in seen:
                seen.add(neighbor)
                frontier.append(neighbor)
    return seen == selected


def test_never_exceeds_target():
    values, adjacency, centroids, enrichment = _make_grid(seed=1)
    for target in [1, 15, 30, 60, 200]:
        result = expand_contiguous("E", target, values, adjacency, centroids, 0.4, -0.4, enrichment)
        assert result.total_value <= target


def test_selection_is_contiguous():
    values, adjacency, centroids, enrichment = _make_grid(seed=2)
    result = expand_contiguous("E", 70, values, adjacency, centroids, 0.4, -0.4, enrichment)
    assert _is_contiguous(set(result.selected_geoids), adjacency, "E")


def test_selection_is_locally_optimal():
    """At termination, no geography adjacent to the selection could be added without exceeding target."""
    values, adjacency, centroids, enrichment = _make_grid(seed=3)
    result = expand_contiguous("E", 45, values, adjacency, centroids, 0.4, -0.4, enrichment)
    selected = set(result.selected_geoids)

    frontier = set()
    for geoid in selected:
        for neighbor in adjacency[geoid]:
            if neighbor not in selected:
                frontier.add(neighbor)

    for geoid in frontier:
        assert result.total_value + values[geoid] > result.target_value


def test_start_alone_exceeds_target_returns_empty_selection():
    values, adjacency, centroids, enrichment = _make_grid(seed=4)
    values["E"] = 1000.0
    result = expand_contiguous("E", 10, values, adjacency, centroids, 0.4, -0.4, enrichment)
    assert result.selected_geoids == []
    assert result.total_value == 0.0
    assert result.median_houses_to_target == 10 / enrichment["E"]["median_home_value"]


def test_huge_target_covers_whole_grid_without_exceeding():
    values, adjacency, centroids, enrichment = _make_grid(seed=5)
    target = sum(values.values()) + 1000
    result = expand_contiguous("A", target, values, adjacency, centroids, 0.0, 0.0, enrichment)
    assert set(result.selected_geoids) == set(values.keys())
    assert result.total_value == sum(values.values())


def test_find_nearest_geoid():
    _, _, centroids, _ = _make_grid(seed=6)
    # (0, -1) is exactly B's centroid (col=1, row=0 -> lon=1.0, lat=0.0)... use a clearer point.
    assert find_nearest_geoid(lat=0.0, lon=1.0, centroids=centroids) == "B"
    assert find_nearest_geoid(lat=-2.0, lon=2.0, centroids=centroids) == "I"
