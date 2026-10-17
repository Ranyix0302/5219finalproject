"""Synthetic HTTP-boundary fixtures; these are not observed Singapore route results."""

import json

import pandas as pd
import pytest
import requests

from ge5219.routing import (
    ADAPTER_VERSION,
    Destination,
    OneMapClient,
    SQLiteRouteCache,
    load_destination,
    route_key,
    route_locations,
    route_request,
)
from ge5219.settings import DEPARTURE


class Response:
    def __init__(self, code=200, payload=None, headers=None):
        self.status_code = code
        self.payload = payload
        self.headers = headers or {}

    def json(self):
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


class Session:
    def __init__(self, *responses):
        self.responses = iter(responses)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return response


@pytest.fixture
def destination():
    return Destination("TEST_DESTINATION", 1.296, 103.772, True, "Synthetic test endpoint")


def success(seconds=1200, **extra):
    return Response(payload={"plan": {"itineraries": [
        {"duration": seconds, **extra}, {"duration": 1},
    ]}})


def test_first_itinerary_units_request_and_unknown_components(destination):
    session = Session(success(1800, walkTime=300, waitingTime=60))
    result = OneMapClient("synthetic-secret", session=session).route((1.3, 103.8), destination)
    assert result["route_status"] == "Success"
    assert result["campus_transit_min"] == 30
    assert result["walk_min"] == 5
    assert result["waiting_min"] == 1
    assert result["transit_min"] is None
    assert result["transfers"] is None
    url, request = session.calls[0]
    assert url.startswith("https://www.onemap.gov.sg/api/public/routingsvc/route")
    assert request["params"]["date"] == "10-19-2026"
    assert request["params"]["time"] == "08:00:00"
    assert request["params"]["routeType"] == "pt"
    assert request["params"]["numItineraries"] == 1
    assert request["headers"] == {"Authorization": "synthetic-secret"}
    assert request["timeout"] == (5, 30)


@pytest.mark.parametrize("response,status", [
    (Response(401), "AuthError"), (Response(403), "AuthError"),
    (Response(404), "NoRoute"), (Response(400), "InvalidRequest"),
    (Response(429), "RateLimited"), (Response(503), "ServiceError"),
    (Response(payload=ValueError("untrusted body")), "ParseError"),
    (Response(payload={"plan": {"itineraries": []}}), "NoRoute"),
    (Response(payload={"error": "Authentication token missing"}), "AuthError"),
    (Response(payload={"error": {"id": 404}}), "NoRoute"),
    (Response(payload={"plan": {"itineraries": [{"duration": -1}]}}), "ParseError"),
    (requests.Timeout("untrusted exception"), "Timeout"),
    (requests.ConnectionError("untrusted exception"), "NetworkError"),
])
def test_distinct_failure_statuses_do_not_invent_minutes(response, status, destination):
    result = OneMapClient("test", session=Session(response), max_attempts=1).route(
        (1.3, 103.8), destination
    )
    assert result["route_status"] == status
    assert result["campus_transit_min"] is None
    assert "untrusted" not in json.dumps(result)


def test_bounded_retry_after_and_parse_retry(destination):
    delays = []
    session = Session(
        Response(429, headers={"Retry-After": "120"}),
        Response(payload=ValueError("bad JSON")), success(),
    )
    result = OneMapClient(
        "test", session=session, sleep=delays.append, max_backoff_seconds=4
    ).route((1.3, 103.8), destination)
    assert result["route_status"] == "Success"
    assert result["attempts"] == 3
    assert delays == [4, 2]


def test_review_required_before_any_request(tmp_path):
    session = Session(success())
    provisional = Destination("AS8", 1.296, 103.772, False, "Address geocode only")
    with pytest.raises(ValueError, match="reachable"):
        OneMapClient("test", session=session).route((1.3, 103.8), provisional)
    path = tmp_path / "destination.json"
    path.write_text(json.dumps({
        "destination_id": "AS8", "latitude": 1.296, "longitude": 103.772,
        "reviewed": True, "coordinate_evidence": "",
    }))
    with pytest.raises(ValueError, match="evidence"):
        load_destination(path)
    assert session.calls == []


def test_exact_cache_scenario_and_close_coordinate_separation(destination):
    base = route_request((1.3, 103.8), destination, DEPARTURE)
    original = route_key(base)
    assert route_key(route_request((1.3, 103.8), destination, "2026-10-19T00:00:00+00:00")) == original
    for field, value in {
        "origin_lat": 1.300000000000001,
        "destination_id": "different",
        "destination_lon": 103.77200000000002,
        "departure": "2026-10-19T09:00:00+08:00",
        "mode": "BUS", "adapter_version": ADAPTER_VERSION + "-next",
    }.items():
        assert route_key({**base, field: value}) != original
    with pytest.raises(ValueError, match="UTC offset"):
        route_request((1.3, 103.8), destination, "2026-10-19T08:00:00")


def test_deduplicate_resume_and_preserve_all_location_metadata(tmp_path, destination):
    locations = pd.DataFrame({
        "location_id": ["A", "B", "C"], "latitude": [1.3, 1.3, 1.31],
        "longitude": [103.8, 103.8, 103.81], "sample_A": [True, False, True],
    })
    session = Session(success(), success(2400))
    client = OneMapClient("test", session=session)
    with SQLiteRouteCache(tmp_path / "routes.sqlite") as cache:
        first = route_locations(
            locations, destination, cache, client, max_requests=1, min_interval_seconds=0
        )
        assert first["route_status"].tolist() == ["Success", "Success", "Pending"]
        assert first["route_key"].iloc[0] == first["route_key"].iloc[1]
        assert len(session.calls) == 1
        second = route_locations(locations, destination, cache, client, min_interval_seconds=0)
        assert second["route_status"].eq("Success").all()
        assert second["location_id"].tolist() == ["A", "B", "C"]
        assert second["destination_id"].eq(destination.destination_id).all()
        assert second["departure"].eq(DEPARTURE).all()
        assert second["origin_lat"].tolist() == locations["latitude"].tolist()
        assert second["origin_lon"].tolist() == locations["longitude"].tolist()
        assert len(session.calls) == 2


def test_retry_failure_on_resume_but_not_repeated_duplicate_rows(tmp_path, destination):
    locations = pd.DataFrame({
        "location_id": ["A", "B"], "latitude": [1.3, 1.3], "longitude": [103.8, 103.8],
    })
    session = Session(Response(503), success())
    client = OneMapClient("test", session=session, max_attempts=1)
    with SQLiteRouteCache(tmp_path / "routes.sqlite") as cache:
        first = route_locations(locations, destination, cache, client, min_interval_seconds=0)
        assert first["route_status"].eq("ServiceError").all()
        assert len(session.calls) == 1
        second = route_locations(locations, destination, cache, client, min_interval_seconds=0)
        assert second["route_status"].eq("Success").all()
        assert len(session.calls) == 2


def test_no_route_retries_only_when_explicitly_requested(tmp_path, destination):
    locations = pd.DataFrame({"location_id": ["A"], "latitude": [1.3], "longitude": [103.8]})
    session = Session(Response(404), success())
    client = OneMapClient("test", session=session)
    with SQLiteRouteCache(tmp_path / "routes.sqlite") as cache:
        for _ in range(2):
            result = route_locations(locations, destination, cache, client, min_interval_seconds=0)
            assert result.iloc[0]["route_status"] == "NoRoute"
        result = route_locations(
            locations, destination, cache, client, min_interval_seconds=0, retry_no_route=True
        )
        assert result.iloc[0]["route_status"] == "Success"
    assert len(session.calls) == 2


def test_auth_failure_halts_batch_and_cache_contains_no_token(tmp_path, destination, monkeypatch):
    token = "synthetic-secret-never-persist"
    monkeypatch.setenv("ONEMAP_TOKEN", token)
    locations = pd.DataFrame({
        "location_id": ["A", "B"], "latitude": [1.3, 1.31], "longitude": [103.8, 103.81],
    })
    session = Session(Response(401, {"error": token}))
    path = tmp_path / "routes.sqlite"
    with SQLiteRouteCache(path) as cache:
        result = route_locations(
            locations, destination, cache, OneMapClient(session=session), min_interval_seconds=0
        )
        assert result["route_status"].tolist() == ["AuthError", "Pending"]
        for request_json, result_json in cache.connection.execute(
            "SELECT request_json, result_json FROM routes"
        ):
            assert token not in request_json + result_json
    assert token not in result.to_json()
    assert token.encode() not in path.read_bytes()
    assert len(session.calls) == 1


def test_empty_locations_have_full_schema(tmp_path, destination):
    locations = pd.DataFrame(columns=["location_id", "latitude", "longitude"])
    with SQLiteRouteCache(tmp_path / "routes.sqlite") as cache:
        result = route_locations(locations, destination, cache, OneMapClient("test"))
    assert result.empty
    assert {"route_status", "campus_transit_min", "departure", "route_key"}.issubset(result)
