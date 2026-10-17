"""Preregistered route evidence and desktop checks, separate from production routing."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import os
import time
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlencode

import pandas as pd
import requests

from ge5219.artifacts import read_locations, write_json
from ge5219.routing import ROUTE_URL, Destination, load_destination, route_request
from ge5219.settings import DEPARTURE

AUDIT_VERSION = "route-desktop-audit-v1"
ACCESS_GUIDE = (
    "https://fass.nus.edu.sg/ecs/wp-content/uploads/sites/4/2022/03/"
    "Roadmap-for-Conference-Venue.pdf"
)
LIMITATIONS = [
    "同一 OneMap API 重查只检验复现、几何和桌面合理性，不是独立数据源或实地真值。",
    "自动异常标志仅用于引导审阅；没有标志不等于路线已验证。",
    "Google Maps 链接不固定出发时间，外部复核时须手动设置同一日期、08:00 和公共交通。",
    "AS8 终点为经桌面核查的地面到达代理，非测绘门口；室内行走和电梯不在模型中。",
]
PRODUCTION_FIELDS = (
    "route_status", "campus_transit_min", "walk_min", "transit_min", "waiting_min",
    "walk_distance_m", "transfers", "route_key", "retrieved_at", "adapter_version",
)
ITINERARY_FIELDS = (
    "duration", "startTime", "endTime", "walkTime", "transitTime", "waitingTime",
    "walkDistance", "walkLimitExceeded", "transfers",
)
LEG_FIELDS = (
    "mode", "route", "routeShortName", "routeLongName", "duration", "distance",
    "startTime", "endTime", "realTime", "transitLeg", "serviceDate",
)
STOP_FIELDS = ("name", "lat", "lon", "stopId", "stopCode", "arrival", "departure")
REVIEW_FIELDS = frozenset((
    "reviewer", "reviewer_type", "reviewed_at", "review_notes", "external_source_url",
    "external_observed_min", "external_departure_confirmed", "review_status",
))
REQUEST_FIELDS = (
    "origin_lat", "origin_lon", "destination_id", "destination_lat", "destination_lon",
    "departure", "mode", "adapter_version",
)


def _finite(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _distance(first: tuple[float, float], second: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (*first, *second))
    a = math.sin((lat2 - lat1) / 2) ** 2
    a += math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 6371000 * 2 * math.asin(min(1, math.sqrt(a)))


def _coordinates(value: Any) -> tuple[float, float] | None:
    if not isinstance(value, dict):
        return None
    lat, lon = _finite(value.get("lat")), _finite(value.get("lon"))
    if lat is None or lon is None or not -90 <= lat <= 90 or not -180 <= lon <= 180:
        return None
    return lat, lon


def _selection_tags(row: Mapping[str, Any], destination: Destination) -> set[str]:
    angle = math.degrees(math.atan2(
        float(row["latitude"]) - destination.latitude,
        (float(row["longitude"]) - destination.longitude)
        * math.cos(math.radians(destination.latitude)),
    )) % 360
    sector = ("E", "NE", "N", "NW", "W", "SW", "S", "SE")[int((angle + 22.5) // 45) % 8]
    duration = _finite(row.get("campus_transit_min"))
    band = "unknown" if duration is None else (
        "0-40" if duration <= 40 else "40-60" if duration <= 60 else "over-60"
    )
    baseline = str(row.get("sample_A", "True")).lower() == "true"
    tags = {f"sector:{sector}", f"housing:{row.get('housing_type', 'unknown')}",
            f"commute:{band}", f"status:{row.get('route_status', 'Pending')}",
            f"sample:{'A' if baseline else 'B_supplement'}"}
    if "score_band" in row:
        tags.add(f"score:{row['score_band']}")
    return tags


def preregister_route_audit(
    locations: pd.DataFrame, routes: pd.DataFrame, destination: Destination,
    n: int = 20, seed: int = 42,
) -> pd.DataFrame:
    """Freeze a deterministic diverse sample before inspecting individual raw legs.

    Start with N/S/E/W and nearest/farthest origins. Greedily cover observed bearing,
    housing, A/B, duration-band and route-status strata, then fill with seeded hashes.
    An optional precomputed score column adds lower/middle/upper score thirds.
    Production outcomes may stratify selection but never exclude failures. Coverage
    is descriptive, not a probability sample or proof that every stratum is covered.
    """
    destination.require_reviewed()
    required = {"location_id", "latitude", "longitude", "housing_type", "sample_A"}
    if not required <= set(locations):
        raise ValueError(f"Audit locations require {sorted(required)}")
    for frame in (locations, routes):
        if frame.location_id.isna().any() or frame.location_id.duplicated().any():
            raise ValueError("Audit location_id must be present and unique")
    if not isinstance(n, int) or n < 6 or len(locations) < n:
        raise ValueError("Audit requires at least n origins and n >= 6")
    if not set(routes.location_id) <= set(locations.location_id):
        raise ValueError("Route origins must belong to the frozen location universe")
    origins = locations.set_index("location_id")
    for route in cast(list[dict[str, Any]], routes.to_dict("records")):
        origin = origins.loc[route["location_id"]]
        expected = route_request((origin["latitude"], origin["longitude"]), destination, DEPARTURE)
        if any(route[field] != value for field, value in expected.items() if field in route):
            raise ValueError("Production route provenance differs from frozen audit scenario")
    columns = ["location_id", *[field for field in PRODUCTION_FIELDS if field in routes]]
    frame = locations.drop(columns=list(PRODUCTION_FIELDS), errors="ignore").merge(
        routes[columns], on="location_id", how="left", validate="one_to_one",
    ).sort_values("location_id").reset_index(drop=True)
    if "route_status" not in frame:
        frame["route_status"] = "Pending"
    frame["route_status"] = frame.route_status.fillna("Pending")
    if "score" in frame:
        scores = pd.to_numeric(frame.score, errors="coerce")
        lower, upper = scores.quantile(1 / 3), scores.quantile(2 / 3)
        frame["score_band"] = ["unknown" if not math.isfinite(score) else
                               "lower" if score <= lower else "upper" if score >= upper
                               else "middle" for score in scores]
    records = cast(list[dict[str, Any]], frame.to_dict("records"))
    coordinates = [_coordinates({"lat": row["latitude"], "lon": row["longitude"]})
                   for row in records]
    if any(point is None for point in coordinates):
        raise ValueError("Audit origins require valid finite WGS84 coordinates")
    frame["distance_to_destination_m"] = [
        _distance((float(row["latitude"]), float(row["longitude"])),
                  (destination.latitude, destination.longitude)) for row in records
    ]
    records = cast(list[dict[str, Any]], frame.to_dict("records"))
    tags = [_selection_tags(row, destination) for row in records]
    selected: list[int] = []
    for column, ascending in (("latitude", False), ("latitude", True),
                              ("longitude", False), ("longitude", True),
                              ("distance_to_destination_m", True),
                              ("distance_to_destination_m", False)):
        index = int(frame.sort_values([column, "location_id"],
                                     ascending=[ascending, True]).index[0])
        if index not in selected:
            selected.append(index)
    covered = set().union(*(tags[index] for index in selected))
    priority = {index: hashlib.sha256(f"{seed}:{row['location_id']}".encode()).hexdigest()
                for index, row in enumerate(records)}
    while len(selected) < n:
        remaining = set(range(len(frame))) - set(selected)
        chosen = min(remaining, key=lambda index: (-len(tags[index] - covered), priority[index]))
        selected.append(chosen)
        covered.update(tags[chosen])
    result = frame.loc[selected].copy()
    result["selection_tags"] = [";".join(sorted(tags[index])) for index in selected]
    result["selection_order"] = range(1, n + 1)
    result["audit_version"] = AUDIT_VERSION
    result["audit_seed"] = seed
    for key in ("reviewer", "reviewer_type", "reviewed_at", "review_notes", "external_source_url",
                "external_observed_min", "external_departure_confirmed"):
        result[key] = ""
    result["review_status"] = "pending"
    for key, value in route_request((0, 0), destination, DEPARTURE).items():
        if key not in ("origin_lat", "origin_lon", "adapter_version"):
            result[key] = value
    result["origin_lat"] = result.latitude
    result["origin_lon"] = result.longitude
    result.attrs["all_observed_strata"] = sorted(set().union(*tags))
    return result.reset_index(drop=True)


def _allow_fields(value: Any, names: tuple[str, ...]) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {key: item for key, item in value.items()
            if key in names and isinstance(item, (str, int, float, bool))
            and (not isinstance(item, float) or math.isfinite(item))}


def sanitize_route_response(payload: Any) -> dict[str, Any]:
    """Retain only first-itinerary measurements, legs, stop points and encoded geometry.

    Response errors, request parameters, headers, debug metadata, agency URLs and
    arbitrary nested fields are excluded because provider text can echo credentials.
    """
    plan = payload.get("plan", {}) if isinstance(payload, dict) else {}
    if not isinstance(plan, dict):
        return {}
    itineraries = plan.get("itineraries", [])
    if not isinstance(itineraries, list) or not itineraries or not isinstance(itineraries[0], dict):
        return {}
    first = itineraries[0]
    itinerary = _allow_fields(first, ITINERARY_FIELDS)
    itinerary["legs"] = []
    raw_legs = first.get("legs", [])
    for source in raw_legs if isinstance(raw_legs, list) else []:
        if not isinstance(source, dict):
            continue
        leg = _allow_fields(source, LEG_FIELDS)
        for key in ("from", "to"):
            leg[key] = _allow_fields(source.get(key), STOP_FIELDS)
        leg["legGeometry"] = _allow_fields(source.get("legGeometry"), ("points", "length"))
        itinerary["legs"].append(leg)
    return {"from": _allow_fields(plan.get("from"), STOP_FIELDS),
            "to": _allow_fields(plan.get("to"), STOP_FIELDS), "itinerary": itinerary}


def collect_route_evidence(
    plan: pd.DataFrame, destination: Destination, evidence_dir: Path,
    token_env: str = "ONEMAP_TOKEN", session: Any = None, min_interval_seconds: float = 1,
) -> None:
    """Explicitly requery frozen origins without touching production cache or route files.

    Read a caller-selected environment variable only when invoked. Existing evidence
    is immutable/reused, one HTTP attempt per new origin; auth/rate exhaustion stops
    collection. No provider body or exception text is written on failure.
    """
    destination.require_reviewed()
    token = os.environ.get(token_env, "")
    if not token.strip():
        raise ValueError(f"Configure the {token_env} environment variable before collection")
    if not math.isfinite(min_interval_seconds) or min_interval_seconds < 0:
        raise ValueError("Request interval must be finite and nonnegative")
    if plan.location_id.duplicated().any():
        raise ValueError("Audit location_id must be unique")
    evidence_dir.mkdir(parents=True, exist_ok=True)
    client = session if session is not None else requests.Session()
    last_started: float | None = None
    for row in plan.to_dict("records"):
        identifier = str(row["location_id"])
        if not identifier or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for char in identifier):
            raise ValueError("location_id must be safe for evidence filenames")
        path = evidence_dir / f"{identifier}.json"
        if path.exists():
            continue
        request = route_request((row["origin_lat"], row["origin_lon"]), destination,
                                str(row["departure"]), str(row["mode"]))
        if any(request[field] != row[field] for field in (
            "destination_id", "destination_lat", "destination_lon", "departure", "mode",
        )):
            raise ValueError("Audit destination/scenario differs from the frozen plan")
        if last_started is not None:
            time.sleep(max(0, min_interval_seconds - (time.monotonic() - last_started)))
        last_started = time.monotonic()
        departure = datetime.fromisoformat(request["departure"])
        record: dict[str, Any] = {"location_id": identifier, "request": request,
                                  "retrieved_at": datetime.now(UTC).isoformat()}
        try:
            response = client.get(ROUTE_URL, params={
                "start": f"{request['origin_lat']!r},{request['origin_lon']!r}",
                "end": f"{destination.latitude!r},{destination.longitude!r}",
                "routeType": "pt", "date": departure.strftime("%m-%d-%Y"),
                "time": departure.strftime("%H:%M:%S"), "mode": request["mode"],
                "maxWalkDistance": 1000, "numItineraries": 1,
            }, headers={"Authorization": token}, timeout=(5, 30))
            record["http_status"] = response.status_code
            record["status"] = {
                401: "AuthError", 403: "AuthError", 429: "RateLimited", 404: "NoRoute",
            }.get(response.status_code, "HttpError")
            if response.status_code == 200:
                safe = sanitize_route_response(response.json())
                record["payload"] = safe
                record["status"] = "Success" if safe else "NoItineraryOrParseError"
        except requests.RequestException:
            record["status"] = "NetworkError"
        except (ValueError, TypeError):
            record["status"] = "ParseError"
        write_json(path, record)
        if record["status"] in ("AuthError", "RateLimited"):
            break


def _decode_polyline(encoded: Any) -> list[tuple[float, float]]:
    if not isinstance(encoded, str) or not encoded:
        return []
    coordinates: list[tuple[float, float]] = []
    index, latitude, longitude = 0, 0, 0
    while index < len(encoded):
        values = []
        for _ in range(2):
            shift, value = 0, 0
            while True:
                if index >= len(encoded) or shift > 30:
                    raise ValueError("Malformed encoded polyline")
                byte = ord(encoded[index]) - 63
                index += 1
                if not 0 <= byte <= 63:
                    raise ValueError("Malformed encoded polyline")
                value |= (byte & 31) << shift
                shift += 5
                if byte < 32:
                    break
            values.append(~(value >> 1) if value & 1 else value >> 1)
        latitude += values[0]
        longitude += values[1]
        point = latitude / 1e5, longitude / 1e5
        if not -90 <= point[0] <= 90 or not -180 <= point[1] <= 180:
            raise ValueError("Polyline coordinates outside WGS84")
        coordinates.append(point)
    return coordinates


def inspect_route_evidence(evidence: dict[str, Any], frozen: Mapping[str, Any]) -> dict[str, Any]:
    """Flag discrepancies and geometric/time anomalies; leave separate review pending.

    Tolerances (2 s time sums, 100 m geometry attachment, 1,000 m single walking
    leg, 2,000 m total walk, 0.5–2 m/s walk speed) are declared desktop heuristics,
    not validated service standards. The production value remains unchanged.
    """
    result: dict[str, Any] = {"location_id": frozen["location_id"], "review_status": "pending",
                              "evidence_status": evidence.get("status", "NotCollected"),
                              "flags": [], "destination_geometry_gap_m": None}
    flags: list[str] = result["flags"]
    itinerary = evidence.get("payload", {}).get("itinerary", {})
    if evidence.get("status") != "Success" or not isinstance(itinerary, dict) or not itinerary:
        flags.append("evidence_unavailable")
        return result
    duration = _finite(itinerary.get("duration"))
    start, end = _finite(itinerary.get("startTime")), _finite(itinerary.get("endTime"))
    result["evidence_duration_min"] = duration / 60 if duration is not None else None
    original = _finite(frozen.get("campus_transit_min"))
    result["duration_difference_seconds"] = (
        duration - original * 60 if duration is not None and original is not None else None
    )
    if result["duration_difference_seconds"] is not None:
        if abs(result["duration_difference_seconds"]) > 1:
            flags.append("production_duration_changed")
    else:
        flags.append("production_duration_unavailable")
    for source, target, factor in (("walkTime", "walk_min", 60),
                                    ("transitTime", "transit_min", 60),
                                    ("waitingTime", "waiting_min", 60),
                                    ("walkDistance", "walk_distance_m", 1)):
        observed, baseline = _finite(itinerary.get(source)), _finite(frozen.get(target))
        difference = observed - baseline * factor if observed is not None and baseline is not None else None
        result[f"{target}_difference_raw"] = difference
        if difference is not None and abs(difference) > 2:
            flags.append(f"production_{target}_changed")
    if duration is None or start is None or end is None:
        flags.append("itinerary_time_missing")
    elif abs((end - start) / 1000 - duration) > 2 or duration < 0:
        flags.append("itinerary_time_mismatch")
    requested = datetime.fromisoformat(str(frozen["departure"])).timestamp() * 1000
    result["initial_scheduling_delay_seconds"] = (start - requested) / 1000 if start else None
    result["requested_to_arrival_min"] = (end - requested) / 60000 if end else None
    if start is not None and (start < requested - 1000 or start > requested + 900000):
        flags.append("initial_scheduling_delay_outside_review_range")
    components = [_finite(itinerary.get(key)) for key in ("walkTime", "transitTime", "waitingTime")]
    if duration is not None and all(value is not None for value in components):
        if abs(sum(float(value) for value in components if value is not None) - duration) > 2:
            flags.append("component_sum_mismatch")
    else:
        flags.append("component_times_missing")
    legs = itinerary.get("legs", [])
    if not isinstance(legs, list) or not legs:
        flags.append("missing_legs")
        return result
    gaps, walking_distances, walking_speeds, leg_durations, temporal_gaps = [], [], [], [], []
    previous_to, previous_end = None, None
    geometries = []
    for leg in legs:
        origin, destination = _coordinates(leg.get("from")), _coordinates(leg.get("to"))
        if previous_to is not None and origin is not None:
            gaps.append(_distance(previous_to, origin))
        if origin is None or destination is None:
            flags.append("leg_coordinates_missing")
        leg_start, leg_end = _finite(leg.get("startTime")), _finite(leg.get("endTime"))
        leg_duration = _finite(leg.get("duration"))
        if leg_start is None or leg_end is None or leg_duration is None:
            flags.append("leg_time_missing")
        else:
            leg_durations.append(leg_duration)
            if leg_duration < 0 or abs((leg_end - leg_start) / 1000 - leg_duration) > 2:
                flags.append("leg_time_mismatch")
            if previous_end is not None and leg_start < previous_end - 1000:
                flags.append("legs_overlap_in_time")
            if previous_end is not None:
                temporal_gaps.append((leg_start - previous_end) / 1000)
        try:
            points = _decode_polyline(leg.get("legGeometry", {}).get("points"))
        except ValueError:
            points = []
            flags.append("malformed_geometry")
        if not points:
            flags.append("leg_geometry_missing")
        elif ((origin is not None and _distance(points[0], origin) > 100)
              or (destination is not None and _distance(points[-1], destination) > 100)):
            flags.append("leg_geometry_attachment_gap")
        geometries.append(points)
        distance = _finite(leg.get("distance"))
        if leg.get("mode") == "WALK" and distance is not None:
            walking_distances.append(distance)
            if distance > 1000:
                flags.append("walk_leg_over_1000m")
            if leg_duration is not None and leg_duration > 0:
                walking_speeds.append(distance / leg_duration)
        previous_to, previous_end = destination, leg_end
    if (len(leg_durations) == len(legs) and duration is not None
            and abs(sum(leg_durations) + sum(temporal_gaps) - duration) > 2):
        flags.append("leg_sum_mismatch")
    result["maximum_leg_connection_gap_m"] = max(gaps) if gaps else None
    if gaps and max(gaps) > 100:
        flags.append("spatial_leg_discontinuity")
    if geometries[-1]:
        final_point = (float(frozen["destination_lat"]), float(frozen["destination_lon"]))
        result["destination_geometry_gap_m"] = _distance(geometries[-1][-1], final_point)
        if result["destination_geometry_gap_m"] > 100:
            flags.append("destination_geometry_gap")
    first_origin = (float(frozen["origin_lat"]), float(frozen["origin_lon"]))
    result["origin_geometry_gap_m"] = _distance(geometries[0][0], first_origin) if geometries[0] else None
    if result["origin_geometry_gap_m"] is not None and result["origin_geometry_gap_m"] > 100:
        flags.append("origin_geometry_gap")
    result["total_walk_leg_distance_m"] = sum(walking_distances)
    if not walking_distances:
        result["total_walk_leg_distance_m"] = None
    if sum(walking_distances) > 2000:
        flags.append("total_walk_over_2000m")
    if any(speed < .5 or speed > 2 for speed in walking_speeds):
        flags.append("walk_speed_outside_review_range")
    if itinerary.get("walkLimitExceeded") is True:
        flags.append("provider_walk_limit_exceeded")
    if start is not None and _finite(legs[0].get("startTime")) != start:
        flags.append("first_leg_start_mismatch")
    if end is not None and _finite(legs[-1].get("endTime")) != end:
        flags.append("last_leg_end_mismatch")
    result["flags"] = sorted(set(flags))
    return result


def _svg(legs: list[dict[str, Any]]) -> str:
    lines = []
    for leg in legs:
        try:
            points = _decode_polyline(leg.get("legGeometry", {}).get("points"))
        except ValueError:
            points = []
        if points:
            lines.append((leg.get("mode"), points))
    if not lines:
        return "<p>没有可绘制的路线几何。</p>"
    all_points = [point for _, points in lines for point in points]
    min_lat, max_lat = min(p[0] for p in all_points), max(p[0] for p in all_points)
    min_lon, max_lon = min(p[1] for p in all_points), max(p[1] for p in all_points)
    scale = min(500 / max((max_lon - min_lon) * math.cos(math.radians(min_lat)), .0001),
                300 / max(max_lat - min_lat, .0001))
    parts = ['<svg viewBox="0 0 540 340" role="img" aria-label="路线几何示意，无底图">']
    for mode, points in lines:
        coordinates = " ".join(f"{20 + (lon-min_lon)*math.cos(math.radians(min_lat))*scale:.1f},"
                               f"{320-(lat-min_lat)*scale:.1f}" for lat, lon in points)
        color = {"WALK": "#d68115", "BUS": "#177f64"}.get(str(mode), "#2d5fb2")
        parts.append(f'<polyline points="{coordinates}" fill="none" stroke="{color}" stroke-width="3"/>')
    return "".join(parts) + "</svg><p>橙色：步行；绿色：公交；蓝色：轨道。几何示意无道路底图，不能证明道路可通行。</p>"


def _validate_review_plan(plan: pd.DataFrame, output: Path) -> None:
    if "location_id" not in plan or plan.empty:
        raise ValueError("Review plan requires nonempty, unique location_id values")
    identifiers = plan.location_id
    if (not identifiers.map(lambda value: isinstance(value, str) and bool(value.strip())).all()
            or identifiers.duplicated().any()):
        raise ValueError("Review location_id values must be nonempty and unique")
    frozen_path = output / "audit_plan.csv"
    if not frozen_path.exists():
        return
    frozen = read_locations(frozen_path)
    if frozen.location_id.duplicated().any() or set(frozen.location_id) != set(identifiers):
        raise ValueError("Review positions differ from the frozen audit plan")
    immutable = set(frozen.columns) - REVIEW_FIELDS
    if not immutable <= set(plan.columns) or (set(plan.columns) - set(frozen.columns)) - REVIEW_FIELDS:
        raise ValueError("Review columns differ from the frozen audit plan")
    expected = frozen.set_index("location_id").sort_index()
    observed = plan.set_index("location_id").sort_index()
    for column in sorted(immutable - {"location_id"}):
        equal = expected[column].eq(observed[column])
        equal |= expected[column].isna() & observed[column].isna()
        if not equal.all():
            raise ValueError(f"Review changed frozen audit field: {column}")


def _evidence_matches_request(evidence: dict[str, Any], frozen: Mapping[str, Any]) -> bool:
    request = evidence.get("request")
    if (not isinstance(request, dict) or evidence.get("location_id") != frozen["location_id"]
            or not isinstance(evidence.get("retrieved_at"), str)):
        return False
    try:
        retrieved_at = datetime.fromisoformat(evidence["retrieved_at"])
    except ValueError:
        return False
    return (retrieved_at.tzinfo is not None and all(
        field in frozen and field in request and request[field] == frozen[field]
        for field in REQUEST_FIELDS
    ))


def _reviewable_evidence(evidence: dict[str, Any], status: str) -> bool:
    if evidence.get("status") == "Success":
        itinerary = evidence.get("payload", {}).get("itinerary")
        return isinstance(itinerary, dict) and bool(itinerary)
    return status == "reviewed_concern" and evidence.get("status") in {
        "NoRoute", "AuthError", "RateLimited", "HttpError", "NetworkError",
        "ParseError", "NoItineraryOrParseError",
    }


def _sha256_value(value: Any) -> str | None:
    if not isinstance(value, str) or len(value) != 64:
        return None
    return value.lower() if all(character in "0123456789abcdefABCDEF" for character in value) else None


def _audit_snapshot_binding(plan: pd.DataFrame, output: Path) -> dict[str, Any]:
    issues: list[str] = []
    manifest_path, plan_path = output / "audit_plan_manifest.json", output / "audit_plan.csv"
    manifest: dict[str, Any] = {}
    if manifest_path.exists():
        try:
            loaded = json.loads(manifest_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                manifest = loaded
            else:
                issues.append("manifest_invalid")
        except (ValueError, UnicodeError):
            issues.append("manifest_invalid")
    else:
        issues.append("manifest_missing")
    route_hash = _sha256_value(manifest.get("routes_sha256"))
    if route_hash is None:
        issues.append("source_routes_hash_missing_or_invalid")
    actual_plan_hash = hashlib.sha256(plan_path.read_bytes()).hexdigest() if plan_path.exists() else None
    if actual_plan_hash is None:
        issues.append("frozen_plan_missing")
    expected_plan_hash = _sha256_value(manifest.get("plan_sha256"))
    if expected_plan_hash is None:
        issues.append("manifest_plan_hash_missing_or_invalid")
    elif expected_plan_hash != actual_plan_hash:
        issues.append("frozen_plan_hash_mismatch")
    scene: dict[str, Any] = {}
    for field in ("destination_id", "destination_lat", "destination_lon", "departure",
                  "mode", "adapter_version"):
        values = plan[field].dropna().drop_duplicates().tolist() if field in plan else []
        if len(values) == 1 and plan[field].notna().all() and str(values[0]).strip():
            scene[field] = values[0]
        else:
            scene[field] = None
            issues.append(f"scene_not_unique:{field}")
    canonical_reviews = plan.sort_values("location_id").reindex(columns=sorted(plan.columns))
    review_hash = hashlib.sha256(
        canonical_reviews.to_csv(index=False, lineterminator="\n").encode("utf-8")
    ).hexdigest()
    return {
        "binding_status": "unbound" if issues else "bound", "binding_issues": issues,
        "source_routes_sha256": route_hash, "plan_sha256": actual_plan_hash,
        "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        if manifest_path.exists() else None,
        "review_table_sha256": review_hash,
        "review_table_hash_format": "UTF-8 CSV; LF; sorted location_id and column names; missing empty",
        **scene,
    }


def write_route_audit_report(plan: pd.DataFrame, evidence_dir: Path, output: Path) -> pd.DataFrame:
    """Validate frozen identities/evidence before counting separate desktop sign-offs.

    Only review fields may differ from output/audit_plan.csv when that frozen plan
    exists. Unique positions and matching collected request evidence are required;
    a genuine failed request can only receive a reviewed-concern sign-off.
    """
    _validate_review_plan(plan, output)
    binding = _audit_snapshot_binding(plan, output)
    output.mkdir(parents=True, exist_ok=True)
    rows, sections = [], []
    reviewed_count, audited_count, concern_count, external_count = 0, 0, 0, 0
    reviewer_types: dict[str, int] = {}
    records = cast(list[dict[str, Any]], plan.fillna("").to_dict("records"))
    for frozen in records:
        path = evidence_dir / f"{frozen['location_id']}.json"
        evidence = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        checked = inspect_route_evidence(evidence, frozen)
        matching_evidence = _evidence_matches_request(evidence, frozen)
        if evidence and not matching_evidence:
            checked["flags"].append("evidence_request_mismatch")
        audited_count += int(matching_evidence and checked["evidence_status"] == "Success")
        status = frozen.get("review_status", "pending")
        reviewer = str(frozen.get("reviewer", "")).strip()
        reviewer_type = str(frozen.get("reviewer_type", "")).strip()
        if (matching_evidence and _reviewable_evidence(evidence, str(status))
                and status in ("reviewed_acceptable", "reviewed_concern") and reviewer
                and reviewer_type in ("AI_assisted_desktop", "human_desktop")
                and frozen.get("reviewed_at") and str(frozen.get("review_notes", "")).strip()):
            reviewed_count += 1
            concern_count += int(status == "reviewed_concern")
            external_count += int(bool(str(frozen.get("external_source_url", "")).strip()))
            reviewer_types[reviewer_type] = reviewer_types.get(reviewer_type, 0) + 1
            checked["review_status"] = status
        checked["reviewer"] = reviewer
        checked["reviewer_type"] = reviewer_type
        checked["flags"] = ";".join(checked["flags"])
        rows.append(checked)
        legs = evidence.get("payload", {}).get("itinerary", {}).get("legs", [])
        google = "https://www.google.com/maps/dir/?" + urlencode({
            "api": 1, "origin": f"{frozen['origin_lat']},{frozen['origin_lon']}",
            "destination": f"{frozen['destination_lat']},{frozen['destination_lon']}",
            "travelmode": "transit",
        })
        leg_rows = "".join("<tr>" + "".join(f"<td>{html.escape(str(value))}</td>" for value in (
            index + 1, leg.get("mode", ""), leg.get("route", ""),
            leg.get("from", {}).get("name", ""), leg.get("to", {}).get("name", ""),
            leg.get("duration", ""), leg.get("distance", ""),
        )) + "</tr>" for index, leg in enumerate(legs))
        sections.append(
            f"<section><h2>{html.escape(str(frozen['location_id']))}</h2>"
            f"<p>独立桌面审阅：{html.escape(str(checked['review_status']))}；"
            f"审阅类型：{html.escape(reviewer_type or '待记录')}；"
            f"自动标志：{html.escape(checked['flags'] or '无')}。</p>"
            f"<p>冻结通勤 {html.escape(str(frozen.get('campus_transit_min', '')))} min；"
            f"重查 {checked.get('evidence_duration_min', '未知')} min；"
            f"初始发车等待 {checked.get('initial_scheduling_delay_seconds', '未知')} s；"
            f"请求时刻至到达 {checked.get('requested_to_arrival_min', '未知')} min；"
            f"终点几何连接 {checked.get('destination_geometry_gap_m', '未知')} m。</p>"
            f'<p><a href="{html.escape(google)}">Google Maps 外部路线复核</a>：'
            "请手动设 2026-10-19 08:00 公共交通。</p>"
            f"{_svg(legs)}<table><tr><th>段</th><th>方式</th><th>线路</th><th>起</th>"
            f"<th>终</th><th>秒</th><th>米</th></tr>{leg_rows}</table>"
            f"<p>审阅备注：{html.escape(str(frozen.get('review_notes', '')))}</p></section>"
        )
    summary = {"status": "reviewed" if reviewed_count >= 20 else "pending",
               "reviewed_count": reviewed_count, "required_count": 20,
               "audited_count": audited_count, "planned_count": len(plan),
               "reviewed_concerns_count": concern_count,
               "external_source_records_count": external_count,
               "reviewer_types": reviewer_types,
               "method": "same-provider reproduction, geometry/time checks, separate desktop review",
               "audit_version": AUDIT_VERSION, "limitations": LIMITATIONS, **binding}
    write_json(output / "route_review.json", summary)
    frame = pd.DataFrame(rows)
    frame.to_csv(output / "route_checks.csv", index=False)
    write_json(output / "route_checks.json", rows)
    limitations = "".join(f"<li>{html.escape(item)}</li>" for item in LIMITATIONS)
    document = (
        '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>路线复核证据</title>'
        "<style>body{max-width:1100px;margin:40px auto;padding:0 20px;font:16px/1.6 system-ui;color:#193447}"
        "section{margin:30px 0;padding:24px;background:#f3f7f8;border-radius:12px}"
        "table{border-collapse:collapse;width:100%;font-size:14px}td,th{padding:8px;border-bottom:1px solid #cbd8df}"
        "svg{background:white;width:100%;max-width:650px}a{color:#1e5c9b}</style>"
        f"<h1>20 条路线桌面复核</h1><p>已获取结构证据 {audited_count}/{len(plan)}；"
        f"已独立桌面审阅 {reviewed_count}/20。自动检查不填写独立审阅状态。</p>"
        f"<p>生产路线快照关联：{binding['binding_status']}。未关联摘要不能作为当前结果的复核证明。</p>"
        "<p>AI_assisted_desktop 表示 AI 辅助桌面复核；human_desktop 表示人工桌面复核。"
        f"两者均非实地测量。</p><ul>{limitations}</ul>"
        f'<p><a href="{ACCESS_GUIDE}">NUS 官方 AS8 地面到达图文说明（PDF 第 3–6 页）</a>；'
        '<a href="https://scale.nus.edu.sg/contact/contact-us">NUS AS8 官方地址</a>。</p>'
        + "".join(sections) + "</html>"
    )
    (output / "route_audit.html").write_text(document, encoding="utf-8")
    return frame


def main(argv: list[str] | None = None) -> int:
    """Separate explicit plan/collect/report commands; never invoked by production CLI."""
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    planning = commands.add_parser("plan")
    planning.add_argument("--static", type=Path, required=True)
    planning.add_argument("--routes", type=Path, required=True)
    planning.add_argument("--scores", type=Path,
                          help="Optional frozen balanced/no-cap point_scores.csv for score thirds")
    planning.add_argument("--destination", type=Path, default=Path("config/destination.json"))
    planning.add_argument("--output", type=Path, default=Path("outputs/route_audit"))
    for command in ("collect", "report"):
        target = commands.add_parser(command)
        target.add_argument("--plan", type=Path, default=Path("outputs/route_audit/audit_plan.csv"))
        target.add_argument("--output", type=Path, default=Path("outputs/route_audit"))
        if command == "collect":
            target.add_argument("--destination", type=Path, default=Path("config/destination.json"))
            target.add_argument("--token-env", default="ONEMAP_TOKEN")
    args = parser.parse_args(argv)
    if args.command == "plan":
        path = args.output / "audit_plan.csv"
        if path.exists():
            raise ValueError("Audit plan already exists; use a new explicitly versioned output directory")
        static, routes = read_locations(args.static), read_locations(args.routes)
        if args.scores:
            scores = read_locations(args.scores)
            if scores.location_id.duplicated().any() or not set(scores.location_id) <= set(static.location_id):
                raise ValueError("Scores require unique IDs from the frozen location universe")
            static = static.drop(columns="score", errors="ignore").merge(
                scores[["location_id", "score"]], on="location_id", how="left", validate="one_to_one",
            )
        destination = load_destination(args.destination)
        plan = preregister_route_audit(static, routes, destination)
        args.output.mkdir(parents=True, exist_ok=True)
        plan.to_csv(path, index=False)
        plan.to_csv(args.output / "audit_review.csv", index=False)
        all_tags = plan.attrs["all_observed_strata"]
        selected_tags = sorted({tag for value in plan.selection_tags for tag in value.split(";")})
        write_json(args.output / "audit_plan_manifest.json", {
            "audit_version": AUDIT_VERSION, "seed": 42, "created_at": datetime.now(UTC).isoformat(),
            "static_sha256": hashlib.sha256(args.static.read_bytes()).hexdigest(),
            "routes_sha256": hashlib.sha256(args.routes.read_bytes()).hexdigest(),
            "scores_sha256": hashlib.sha256(args.scores.read_bytes()).hexdigest() if args.scores else None,
            "plan_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "all_observed_strata": all_tags, "selected_strata": selected_tags,
            "uncovered_strata": sorted(set(all_tags) - set(selected_tags)),
            "selection": "geographic extrema then greedy observed-stratum coverage then seeded hash",
            "limitations": LIMITATIONS,
        })
    else:
        plan = read_locations(args.plan)
        if args.command == "collect":
            collect_route_evidence(plan, load_destination(args.destination), args.output / "evidence",
                                   token_env=args.token_env)
        write_route_audit_report(plan, args.output / "evidence", args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
