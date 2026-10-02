"""Geodesic area calculation and GeoJSON zone resolution.

Pure-Python implementation — no external dependencies.
Area formula: spherical excess method (Chamberlain & Duquette, JPL 07-03),
matching @turf/area output.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

EARTH_RADIUS = 6_371_008.8  # mean radius in meters

_ZONE_TYPE_MOWING = 1
_ZONE_TYPE_NO_GO = 2
_ZONE_TYPE_OBSTACLE = 9

_CHILD_TYPES = {_ZONE_TYPE_NO_GO, _ZONE_TYPE_OBSTACLE}

MIN_RUNTIME_SECONDS = 30


@dataclass(frozen=True)
class ZoneInfo:
    """Pre-computed area info for a single mowing zone."""

    name: str
    gross_area: float
    net_area: float


def _ring_area(coords: list[list[float]]) -> float:
    """Spherical excess area of a coordinate ring in m².

    coords: list of [longitude, latitude] pairs.
    Handles both closed (first == last) and unclosed rings.
    """
    if len(coords) < 3:
        return 0.0

    # Close the ring if needed
    if coords[0][0] != coords[-1][0] or coords[0][1] != coords[-1][1]:
        coords = list(coords) + [coords[0]]

    n = len(coords)
    total = 0.0
    for i in range(n):
        p1 = coords[i]
        p2 = coords[(i + 1) % n]
        p3 = coords[(i + 2) % n]
        total += (math.radians(p3[0]) - math.radians(p1[0])) * math.sin(
            math.radians(p2[1])
        )

    return abs(total * EARTH_RADIUS * EARTH_RADIUS / 2)


def polygon_area(coordinates: list[list[list[float]]]) -> float:
    """Compute area of a GeoJSON Polygon geometry in m².

    coordinates[0] is the exterior ring; coordinates[1:] are holes.
    """
    if not coordinates:
        return 0.0

    total = _ring_area(coordinates[0])
    for hole in coordinates[1:]:
        total -= _ring_area(hole)
    return max(0.0, total)


def parse_geojson_zones(
    geojson_str: str | None,
) -> dict[str, ZoneInfo]:
    """Parse a GeoJSON FeatureCollection and return mowing zone info.

    Returns a dict mapping zone feature ID to ZoneInfo with computed
    gross and net (minus no-go/obstacle children) areas.
    """
    if not geojson_str:
        return {}

    import json

    try:
        fc = json.loads(geojson_str)
    except (json.JSONDecodeError, TypeError):
        return {}

    features = fc.get("features")
    if not isinstance(features, list):
        return {}

    mowing_zones: list[dict] = []
    children: list[dict] = []

    for f in features:
        props = f.get("properties") or {}
        ftype = props.get("type")
        if ftype is None:
            continue
        try:
            ftype = int(ftype)
        except (TypeError, ValueError):
            continue

        if ftype == _ZONE_TYPE_MOWING:
            mowing_zones.append(f)
        elif ftype in _CHILD_TYPES:
            children.append(f)

    zones: dict[str, ZoneInfo] = {}
    for zone in mowing_zones:
        props = zone.get("properties") or {}
        zone_id = str(props.get("id", ""))
        if not zone_id:
            continue

        geom = zone.get("geometry") or {}
        coords = geom.get("coordinates")
        gross = polygon_area(coords) if coords else 0.0

        child_area = 0.0
        for child in children:
            cp = child.get("properties") or {}
            if str(cp.get("parent_id", "")) == zone_id:
                cgeom = child.get("geometry") or {}
                ccoords = cgeom.get("coordinates")
                if ccoords:
                    child_area += polygon_area(ccoords)

        zones[zone_id] = ZoneInfo(
            name=props.get("name", "") or "",
            gross_area=round(gross, 1),
            net_area=round(max(0.0, gross - child_area), 1),
        )

    return zones


def resolve_task_areas(
    zones: dict[str, ZoneInfo],
    area_ids: list[str],
    top_area: float | None,
    remaining_area: float | None,
    runtime_seconds: int | None,
) -> tuple[float | None, float | None, float | None, float | None]:
    """Compute mowed area, selected zone area, zone remaining, and progress.

    Returns (mowed, selected_area, zone_remaining, progress) where progress
    is 0.0–1.0.
    """
    # Selected zone area from GeoJSON
    selected = 0.0
    matched = 0
    for aid in area_ids:
        zone = zones.get(aid)
        if zone is not None:
            selected += zone.net_area
            matched += 1

    selected_area = round(selected, 1) if matched > 0 else None

    # Mowed = topArea - remainingArea with stale-data guard
    mowed: float | None = None
    if top_area is not None and remaining_area is not None:
        runtime_ok = (runtime_seconds or 0) >= MIN_RUNTIME_SECONDS
        diff = top_area - remaining_area
        values_ok = remaining_area <= top_area and diff >= 0
        if runtime_ok and values_ok:
            mowed = round(diff, 1)

    # Progress = mowed / selected, clamped to [0, 1]
    progress: float | None = None
    if mowed is not None and selected_area is not None and selected_area > 0:
        progress = min(1.0, mowed / selected_area)

    zone_remaining: float | None = None
    if mowed is not None and selected_area is not None:
        zone_remaining = round(max(0.0, selected_area - mowed), 1)

    return mowed, selected_area, zone_remaining, progress
