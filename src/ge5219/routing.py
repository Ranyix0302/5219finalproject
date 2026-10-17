"""OneMap public-transit adapter with exact-scenario, resumable route caching."""

from __future__ import annotations

import hashlib
import json
import math
import os
import sqlite3
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Self, cast

import pandas as pd
import requests

from ge5219.settings import DEPARTURE

ADAPTER_VERSION = "onemap-pt-first-itinerary-v1"
ROUTE_URL = "https://www.onemap.gov.sg/api/public/routingsvc/route"
SINGAPORE_TIME = timezone(timedelta(hours=8))
RETRYABLE_STATUSES = frozenset(
    ("AuthError", "RateLimited", "ServiceError", "NetworkError", "Timeout", "ParseError")
)
RESULT_FIELDS = (
    "route_status", "campus_transit_min", "walk_min", "transit_min", "waiting_min",
    "walk_distance_m", "transfers", "http_status", "attempts", "retrieved_at",
)


def _coordinates(latitude: Any, longitude: Any) -> tuple[float, float]:
    latitude, longitude = float(latitude), float(longitude)
    if not math.isfinite(latitude) or not math.isfinite(longitude):
        raise ValueError("Route coordinates must be finite")
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        raise ValueError("Route coordinates are outside WGS84 bounds")
    return latitude, longitude


def canonical_departure(departure: str) -> str:
    """Retain the requested instant with an explicit Singapore UTC offset."""
    parsed = datetime.fromisoformat(departure)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Departure must include its UTC offset")
    return parsed.astimezone(SINGAPORE_TIME).isoformat()


@dataclass(frozen=True)
class Destination:
    """A versioned destination whose point semantics have been explicitly reviewed."""

    destination_id: str
    latitude: float
    longitude: float
    reviewed: bool = False
    coordinate_evidence: str = ""
    name: str = ""

    def require_reviewed(self) -> None:
        _coordinates(self.latitude, self.longitude)
        if not self.destination_id.strip():
            raise ValueError("Destination ID is required")
        if self.reviewed is not True or not self.coordinate_evidence.strip():
            raise ValueError(
                "Destination requires reviewed=true and coordinate evidence for a reachable "
                "ground point; an address geocode alone is insufficient"
            )


def load_destination(path: str | Path) -> Destination:
    """Read and validate the production endpoint without silently approving it."""
    config = json.loads(Path(path).read_text(encoding="utf-8"))
    destination = Destination(**{
        field: config[field]
        for field in Destination.__dataclass_fields__
        if field in config
    })
    destination.require_reviewed()
    return destination


def route_request(
    origin: tuple[float, float], destination: Destination, departure: str, mode: str = "TRANSIT"
) -> dict[str, Any]:
    """Create non-secret scenario metadata shared by cache keys and CSV outputs."""
    latitude, longitude = _coordinates(*origin)
    destination.require_reviewed()
    mode = mode.upper()
    if mode not in ("TRANSIT", "BUS", "RAIL"):
        raise ValueError("Public-transport mode must be TRANSIT, BUS, or RAIL")
    return {
        "origin_lat": latitude,
        "origin_lon": longitude,
        "destination_id": destination.destination_id,
        "destination_lat": float(destination.latitude),
        "destination_lon": float(destination.longitude),
        "departure": canonical_departure(departure),
        "mode": mode,
        "adapter_version": ADAPTER_VERSION,
    }


def route_key(request: dict[str, Any]) -> str:
    """Hash exact float values and all routing scenario parameters, without rounding."""
    exact = {
        key: float(value).hex() if key.endswith(("_lat", "_lon")) else value
        for key, value in request.items()
    }
    return hashlib.sha256(json.dumps(exact, sort_keys=True).encode()).hexdigest()


class SQLiteRouteCache:
    """Commit each route immediately so interruption does not discard completed work."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS routes "
            "(route_key TEXT PRIMARY KEY, request_json TEXT NOT NULL, result_json TEXT NOT NULL)"
        )
        self.connection.commit()

    def get(self, key: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT result_json FROM routes WHERE route_key = ?", (key,)
        ).fetchone()
        return json.loads(row[0]) if row else None

    def put(self, key: str, request: dict[str, Any], result: dict[str, Any]) -> None:
        # Only typed adapter outputs are retained: provider error text may echo credentials.
        safe_result = {field: result.get(field) for field in RESULT_FIELDS}
        self.connection.execute(
            "INSERT INTO routes VALUES (?, ?, ?) ON CONFLICT(route_key) DO UPDATE SET "
            "request_json = excluded.request_json, result_json = excluded.result_json",
            (key, json.dumps(request, sort_keys=True), json.dumps(safe_result, allow_nan=False)),
        )
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    converted = float(value)
    return converted if math.isfinite(converted) and converted >= 0 else None


def _result(status: str, attempts: int, http_status: int | None = None) -> dict[str, Any]:
    return {
        "route_status": status,
        "campus_transit_min": None,
        "walk_min": None,
        "transit_min": None,
        "waiting_min": None,
        "walk_distance_m": None,
        "transfers": None,
        "http_status": http_status,
        "attempts": attempts,
        "retrieved_at": datetime.now(UTC).isoformat(),
    }


def _parse_itinerary(payload: Any, attempt: int) -> dict[str, Any]:
    result = _result("ParseError", attempt, 200)
    if not isinstance(payload, dict):
        return result
    if payload.get("error"):
        error = payload["error"]
        code = error.get("id") if isinstance(error, dict) else None
        message = str(error).lower()
        if code in (404, "404") or "no route found" in message or "no bus route" in message:
            result["route_status"] = "NoRoute"
        elif code in (401, 403, "401", "403") or any(term in message for term in (
            "authentication", "unauthorized", "token expired", "invalid token", "token missing",
        )):
            result["route_status"] = "AuthError"
        elif code in (429, "429"):
            result["route_status"] = "RateLimited"
        return result
    plan = payload.get("plan")
    if not isinstance(plan, dict) or not isinstance(plan.get("itineraries"), list):
        return result
    itineraries = plan["itineraries"]
    if not itineraries:
        result["route_status"] = "NoRoute"
        return result
    itinerary = itineraries[0]
    if not isinstance(itinerary, dict) or _number(itinerary.get("duration")) is None:
        return result
    result["route_status"] = "Success"
    result["campus_transit_min"] = float(itinerary["duration"]) / 60
    for source, target in (
        ("walkTime", "walk_min"), ("transitTime", "transit_min"),
        ("waitingTime", "waiting_min"),
    ):
        seconds = _number(itinerary.get(source))
        result[target] = seconds / 60 if seconds is not None else None
    result["walk_distance_m"] = _number(itinerary.get("walkDistance"))
    result["transfers"] = _number(itinerary.get("transfers"))
    return result


class OneMapClient:
    """Query first transit itinerary; never retain provider bodies, tokens, or exception text."""

    def __init__(
        self, token: str | None = None, session: Any = None, max_attempts: int = 3,
        timeout: tuple[float, float] = (5, 30), sleep: Any = time.sleep,
        max_backoff_seconds: float = 60,
    ):
        if not isinstance(max_attempts, int) or not 1 <= max_attempts <= 10:
            raise ValueError("max_attempts must be an integer from 1 to 10")
        if len(timeout) != 2 or any(not math.isfinite(v) or v <= 0 for v in timeout):
            raise ValueError("Connect/read timeouts must be positive finite seconds")
        if not math.isfinite(max_backoff_seconds) or max_backoff_seconds < 0:
            raise ValueError("Maximum backoff must be finite and nonnegative")
        self._token = token if token is not None else os.environ.get("ONEMAP_TOKEN", "")
        self.session = session if session is not None else requests.Session()
        self.max_attempts = max_attempts
        self.timeout = timeout
        self.sleep = sleep
        self.max_backoff_seconds = max_backoff_seconds

    def _delay(self, attempt: int, retry_after: str | None) -> float:
        delay = min(2 ** (attempt - 1), self.max_backoff_seconds)
        if retry_after:
            try:
                delay = float(retry_after)
            except (TypeError, ValueError):
                try:
                    delay = (
                        parsedate_to_datetime(retry_after) - datetime.now(UTC)
                    ).total_seconds()
                except (TypeError, ValueError, OverflowError):
                    pass
        return max(0, min(delay, self.max_backoff_seconds))

    def route(
        self, origin: tuple[float, float], destination: Destination,
        departure: str = DEPARTURE, mode: str = "TRANSIT",
    ) -> dict[str, Any]:
        """Classify HTTP, parse, and physical no-route outcomes without inventing minutes."""
        request = route_request(origin, destination, departure, mode)
        if not self._token or not self._token.strip():
            return _result("AuthError", 0)
        selected_time = datetime.fromisoformat(request["departure"])
        params = {
            "start": f"{request['origin_lat']!r},{request['origin_lon']!r}",
            "end": f"{request['destination_lat']!r},{request['destination_lon']!r}",
            "routeType": "pt", "date": selected_time.strftime("%m-%d-%Y"),
            "time": selected_time.strftime("%H:%M:%S"), "mode": request["mode"],
            "maxWalkDistance": 1000, "numItineraries": 1,
        }
        result = _result("NetworkError", 0)
        for attempt in range(1, self.max_attempts + 1):
            retry_after = None
            try:
                response = self.session.get(
                    ROUTE_URL, params=params,
                    headers={"Authorization": self._token}, timeout=self.timeout,
                )
                code = response.status_code
                retry_after = response.headers.get("Retry-After")
                if code in (401, 403):
                    return _result("AuthError", attempt, code)
                if code == 404:
                    return _result("NoRoute", attempt, code)
                if code == 429:
                    result = _result("RateLimited", attempt, code)
                elif code >= 500:
                    result = _result("ServiceError", attempt, code)
                elif code != 200:
                    return _result("InvalidRequest", attempt, code)
                else:
                    try:
                        result = _parse_itinerary(response.json(), attempt)
                    except (ValueError, TypeError):
                        result = _result("ParseError", attempt, code)
            except requests.Timeout:
                result = _result("Timeout", attempt)
            except requests.RequestException:
                result = _result("NetworkError", attempt)
            if (
                result["route_status"] == "AuthError"
                or result["route_status"] not in RETRYABLE_STATUSES
                or attempt == self.max_attempts
            ):
                return result
            self.sleep(self._delay(attempt, retry_after))
        return result


def route_locations(
    locations: pd.DataFrame, destination: Destination, cache: SQLiteRouteCache,
    client: OneMapClient, departure: str = DEPARTURE, mode: str = "TRANSIT",
    max_requests: int | None = None, min_interval_seconds: float = 1.0,
    retry_no_route: bool = False,
) -> pd.DataFrame:
    """Route each unique position once per run; retain every planned location in output.

    Successful and invalid-request cache records are reused. Technical failures retry on
    a later invocation, once per position. NoRoute retries require an explicit option.
    max_requests counts unique client.route calls, whose HTTP attempts are separately
    bounded. Auth/rate-limit exhaustion halts new calls and leaves remaining rows Pending.
    """
    destination.require_reviewed()
    required = {"location_id", "latitude", "longitude"}
    if not required.issubset(locations):
        raise ValueError(f"Locations require columns: {sorted(required)}")
    if locations["location_id"].isna().any() or locations["location_id"].duplicated().any():
        raise ValueError("location_id must be present and unique")
    if max_requests is not None and (not isinstance(max_requests, int) or max_requests < 0):
        raise ValueError("max_requests must be a nonnegative integer or None")
    if not math.isfinite(min_interval_seconds) or min_interval_seconds < 0:
        raise ValueError("Minimum request interval must be finite and nonnegative")
    completed: dict[str, tuple[dict[str, Any], bool]] = {}
    rows: list[dict[str, Any]] = []
    requests_made = 0
    halted = False
    last_request_time: float | None = None
    result: dict[str, Any] | None
    records = cast(list[dict[str, Any]], locations.to_dict("records"))
    for location in records:
        request = route_request(
            (location["latitude"], location["longitude"]), destination, departure, mode
        )
        key = route_key(request)
        if key in completed:
            result, _ = completed[key]
            cached = True
        else:
            result = cache.get(key)
            cached = result is not None
            should_retry = result is None or result["route_status"] in RETRYABLE_STATUSES
            should_retry |= bool(
                retry_no_route and result is not None and result["route_status"] == "NoRoute"
            )
            within_budget = max_requests is None or requests_made < max_requests
            if should_retry and not halted and within_budget:
                if last_request_time is not None:
                    remaining = min_interval_seconds - (time.monotonic() - last_request_time)
                    if remaining > 0:
                        time.sleep(remaining)
                last_request_time = time.monotonic()
                result = client.route(
                    (request["origin_lat"], request["origin_lon"]), destination,
                    request["departure"], request["mode"],
                )
                requests_made += 1
                cache.put(key, request, result)
                cached = False
                halted = result["route_status"] in ("AuthError", "RateLimited")
            if result is None:
                result = _result("Pending", 0)
            completed[key] = (result, cached)
        rows.append({**location, **request, "route_key": key, **result, "cached": cached})
    result_columns = list(locations.columns) + list(route_request(
        (0, 0), destination, departure, mode
    )) + ["route_key", *RESULT_FIELDS, "cached"]
    return pd.DataFrame(rows, columns=list(dict.fromkeys(result_columns)))
