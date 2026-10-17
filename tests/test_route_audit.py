"""Synthetic audit fixtures check mechanics, never certify actual route accuracy."""

import hashlib
import json

import pandas as pd
import pytest

from ge5219.route_audit import (
    collect_route_evidence,
    inspect_route_evidence,
    preregister_route_audit,
    sanitize_route_response,
    write_route_audit_report,
)
from ge5219.routing import Destination
from ge5219.settings import DEPARTURE


@pytest.fixture
def destination():
    return Destination("TEST", 1.3, 103.8, True, "Synthetic reachable point")


def locations():
    return pd.DataFrame({
        "location_id": [f"L{i:02}" for i in range(32)],
        "latitude": [1.2 + (i % 8) * .03 for i in range(32)],
        "longitude": [103.6 + (i // 8) * .1 for i in range(32)],
        "housing_type": ["HDB", "Landed", "Non-Landed", "EC"] * 8,
        "sample_A": [i != 17 for i in range(32)],
        "area_id": [f"A{i // 4}" for i in range(32)],
    })


def production():
    return pd.DataFrame({
        "location_id": [f"L{i:02}" for i in range(32)],
        "route_status": ["Success"] * 31 + ["NoRoute"],
        "campus_transit_min": list(range(20, 51)) + [None],
    })


def encode_polyline(points):
    result = ""
    previous = (0, 0)
    for point in points:
        current = tuple(round(value * 1e5) for value in point)
        for value, old in zip(current, previous):
            delta = value - old
            shifted = ~(delta << 1) if delta < 0 else delta << 1
            while shifted >= 0x20:
                result += chr((0x20 | (shifted & 0x1f)) + 63)
                shifted >>= 5
            result += chr(shifted + 63)
        previous = current
    return result


def response():
    start = int(pd.Timestamp(DEPARTURE).timestamp() * 1000)
    return {"plan": {"itineraries": [{
        "duration": 120, "startTime": start + 30000, "endTime": start + 150000,
        "walkTime": 120, "transitTime": 0, "waitingTime": 0, "walkDistance": 120,
        "legs": [{
            "mode": "WALK", "duration": 120, "distance": 120,
            "startTime": start + 30000, "endTime": start + 150000,
            "from": {"name": "Origin", "lat": 1.299, "lon": 103.8},
            "to": {"name": "AS8 proxy", "lat": 1.3, "lon": 103.8},
            "legGeometry": {"points": encode_polyline([(1.299, 103.8), (1.3, 103.8)])},
        }],
    }]}, "headers": {"Authorization": "secret"}, "error": "secret"}


def frozen():
    return {
        "location_id": "L00", "origin_lat": 1.299, "origin_lon": 103.8,
        "destination_lat": 1.3, "destination_lon": 103.8,
        "departure": DEPARTURE, "campus_transit_min": 2,
        "walk_min": 2, "transit_min": 0, "waiting_min": 0, "walk_distance_m": 120,
        "route_status": "Success",
    }


def evidence():
    return {"status": "Success", "payload": sanitize_route_response(response())}


def test_selection_is_reproducible_and_covers_strata_without_discarding_failure(destination):
    selected = preregister_route_audit(locations(), production(), destination)
    shuffled = preregister_route_audit(
        locations().sample(frac=1, random_state=9),
        production().sample(frac=1, random_state=1), destination,
    )
    assert selected.location_id.tolist() == shuffled.location_id.tolist()
    assert len(selected) == 20
    assert selected.location_id.is_unique
    assert set(selected.housing_type) == {"HDB", "Landed", "Non-Landed", "EC"}
    assert "L17" in set(selected.location_id)
    assert "L31" in set(selected.location_id)
    assert selected.review_status.eq("pending").all()
    assert selected.latitude.min() == locations().latitude.min()
    assert selected.latitude.max() == locations().latitude.max()


def test_selection_rejects_duplicates_and_small_universe(destination):
    with pytest.raises(ValueError, match="unique"):
        preregister_route_audit(pd.concat([locations(), locations().iloc[:1]]),
                               production(), destination)
    with pytest.raises(ValueError, match="at least"):
        preregister_route_audit(locations().iloc[:10], production().iloc[:10], destination)


def test_optional_scores_add_lower_and_upper_strata_without_removing_unknown(destination):
    frame = locations()
    frame["score"] = [i / 32 for i in range(31)] + [None]
    selected = preregister_route_audit(frame, production(), destination)
    assert {"lower", "middle", "upper", "unknown"} <= set(selected.score_band)
    assert "L31" in set(selected.location_id)


def test_allowlist_excludes_credentials_and_untrusted_provider_metadata():
    safe = sanitize_route_response(response())
    assert "secret" not in json.dumps(safe)
    assert safe["itinerary"]["legs"][0]["to"]["name"] == "AS8 proxy"
    assert "legGeometry" in safe["itinerary"]["legs"][0]


def test_time_semantics_and_frozen_production_comparison_are_explicit():
    checked = inspect_route_evidence(evidence(), frozen())
    assert checked["duration_difference_seconds"] == 0
    assert checked["initial_scheduling_delay_seconds"] == 30
    assert checked["requested_to_arrival_min"] == 2.5
    assert checked["destination_geometry_gap_m"] == pytest.approx(0)
    assert checked["flags"] == []
    assert checked["review_status"] == "pending"


def test_geometric_time_and_walk_anomalies_are_flagged_without_auto_rejection():
    changed = evidence()
    itinerary = changed["payload"]["itinerary"]
    itinerary["duration"] = 300
    itinerary["legs"][0]["legGeometry"]["points"] = encode_polyline(
        [(1.299, 103.8), (1.31, 103.8)]
    )
    itinerary["legs"][0]["distance"] = 1500
    checked = inspect_route_evidence(changed, frozen())
    assert {"production_duration_changed", "itinerary_time_mismatch",
            "component_sum_mismatch", "destination_geometry_gap",
            "walk_leg_over_1000m", "walk_speed_outside_review_range"} <= set(checked["flags"])
    assert checked["review_status"] == "pending"


def test_missing_legs_and_geometry_are_visible():
    changed = evidence()
    changed["payload"]["itinerary"]["legs"] = []
    checked = inspect_route_evidence(changed, frozen())
    assert "missing_legs" in checked["flags"]
    assert checked["destination_geometry_gap_m"] is None
    assert checked["review_status"] == "pending"


def test_collection_requires_environment_and_redacts_http_failure(tmp_path, monkeypatch, destination):
    class Session:
        calls = 0

        def get(self, *args, **kwargs):
            self.calls += 1
            return type("Response", (), {"status_code": 401, "text": "secret"})()

    session = Session()
    monkeypatch.delenv("SYNTHETIC_AUDIT_TOKEN", raising=False)
    selected = preregister_route_audit(locations(), production(), destination)
    with pytest.raises(ValueError, match="environment"):
        collect_route_evidence(selected, destination, tmp_path,
                               token_env="SYNTHETIC_AUDIT_TOKEN", session=session)
    assert session.calls == 0
    monkeypatch.setenv("SYNTHETIC_AUDIT_TOKEN", "synthetic-secret")
    collect_route_evidence(selected, destination, tmp_path,
                           token_env="SYNTHETIC_AUDIT_TOKEN", session=session)
    assert session.calls == 1
    saved = list(tmp_path.glob("*.json"))
    assert len(saved) == 1
    assert "secret" not in saved[0].read_text()
    assert json.loads(saved[0].read_text())["status"] == "AuthError"


def test_successful_collection_uses_frozen_scene_and_reuses_existing_evidence(
    tmp_path, monkeypatch, destination,
):
    class Session:
        def __init__(self):
            self.calls = []

        def get(self, url, **kwargs):
            self.calls.append((url, kwargs))
            return type("Response", (), {"status_code": 200, "json": lambda self: response()})()

    monkeypatch.setenv("SYNTHETIC_AUDIT_TOKEN", "synthetic-secret")
    selected = preregister_route_audit(locations(), production(), destination).iloc[:1]
    session = Session()
    for _ in range(2):
        collect_route_evidence(selected, destination, tmp_path,
                               token_env="SYNTHETIC_AUDIT_TOKEN", session=session)
    assert len(session.calls) == 1
    params = session.calls[0][1]["params"]
    assert params["date"] == "10-19-2026"
    assert params["time"] == "08:00:00"
    assert params["mode"] == "TRANSIT"
    saved = next(tmp_path.glob("*.json")).read_text()
    assert "synthetic-secret" not in saved
    assert json.loads(saved)["status"] == "Success"


def test_report_preserves_pending_reviews_and_safe_local_maps(tmp_path):
    plan = pd.DataFrame([{**frozen(), "reviewer": "", "review_status": "pending",
                          "review_notes": "<script>bad</script>"}])
    path = tmp_path / "evidence"
    path.mkdir()
    (path / "L00.json").write_text(json.dumps(evidence()))
    checks = write_route_audit_report(plan, path, tmp_path / "report")
    assert checks.review_status.tolist() == ["pending"]
    html = (tmp_path / "report" / "route_audit.html").read_text(encoding="utf-8")
    assert "maps/dir/?api=1" in html
    assert "<svg" in html
    assert "&lt;script&gt;bad&lt;/script&gt;" in html
    assert "<script>bad</script>" not in html
    assert "独立数据源" in html


def signed_row():
    return {**frozen(), "destination_id": "TEST", "mode": "TRANSIT",
            "adapter_version": "onemap-pt-first-itinerary-v1", "route_key": "frozen-key",
            "reviewer": "Separate synthetic reviewer", "reviewer_type": "AI_assisted_desktop",
            "reviewed_at": "2026-10-17T10:00:00+08:00",
            "review_status": "reviewed_acceptable", "review_notes": "Inspected synthetic legs"}


def collected_evidence(row):
    request_fields = ("origin_lat", "origin_lon", "destination_id", "destination_lat",
                      "destination_lon", "departure", "mode", "adapter_version")
    return {**evidence(), "location_id": row["location_id"],
            "retrieved_at": "2026-10-17T09:00:00+08:00",
            "request": {field: row[field] for field in request_fields}}


@pytest.mark.parametrize("ids", [["L00"] * 20, [""], [None], ["  "]])
def test_report_rejects_repeated_or_empty_review_identifiers(tmp_path, ids):
    plan = pd.DataFrame([{**signed_row(), "location_id": identifier} for identifier in ids])
    with pytest.raises(ValueError, match="unique|nonempty"):
        write_route_audit_report(plan, tmp_path / "evidence", tmp_path / "report")


@pytest.mark.parametrize("column,value", [
    ("origin_lat", 1.4), ("destination_lon", 103.9), ("departure", "2026-10-19T09:00:00+08:00"),
    ("mode", "BUS"), ("route_key", "substituted-key"), ("campus_transit_min", 1),
    ("location_id", "other-position"),
])
def test_report_rejects_changes_to_frozen_plan(tmp_path, column, value):
    plan = pd.DataFrame([signed_row()])
    plan.to_csv(tmp_path / "audit_plan.csv", index=False)
    plan.loc[0, column] = value
    with pytest.raises(ValueError, match="frozen"):
        write_route_audit_report(plan, tmp_path / "evidence", tmp_path)


def test_signed_reviews_without_matching_collected_evidence_do_not_count(tmp_path):
    row = signed_row()
    plan = pd.DataFrame([row])
    directory = tmp_path / "evidence"
    directory.mkdir()
    write_route_audit_report(plan, directory, tmp_path)
    assert json.loads((tmp_path / "route_review.json").read_text(encoding="utf-8"))["reviewed_count"] == 0
    changed = collected_evidence(row)
    changed["request"]["departure"] = "2026-10-19T09:00:00+08:00"
    (directory / "L00.json").write_text(json.dumps(changed))
    checks = write_route_audit_report(plan, directory, tmp_path)
    assert json.loads((tmp_path / "route_review.json").read_text(encoding="utf-8"))["reviewed_count"] == 0
    assert checks.review_status.tolist() == ["pending"]


def test_matching_evidence_counts_one_review_and_no_route_requires_concern(tmp_path):
    row = signed_row()
    plan = pd.DataFrame([row])
    plan.assign(review_status="pending").to_csv(tmp_path / "audit_plan.csv", index=False)
    directory = tmp_path / "evidence"
    directory.mkdir()
    collected = collected_evidence(row)
    path = directory / "L00.json"
    path.write_text(json.dumps(collected))
    write_route_audit_report(plan, directory, tmp_path)
    summary = json.loads((tmp_path / "route_review.json").read_text(encoding="utf-8"))
    assert summary["reviewed_count"] == 1
    assert summary["status"] == "pending"
    collected.update(status="NoRoute", http_status=404)
    collected.pop("payload")
    path.write_text(json.dumps(collected))
    write_route_audit_report(plan, directory, tmp_path)
    assert json.loads((tmp_path / "route_review.json").read_text(encoding="utf-8"))["reviewed_count"] == 0
    plan.loc[0, "review_status"] = "reviewed_concern"
    write_route_audit_report(plan, directory, tmp_path)
    summary = json.loads((tmp_path / "route_review.json").read_text(encoding="utf-8"))
    assert summary["reviewed_count"] == 1
    assert summary["reviewed_concerns_count"] == 1
    assert summary["audited_count"] == 0


def test_report_binds_manifest_route_snapshot_scene_and_review_content(tmp_path):
    row = signed_row()
    plan = pd.DataFrame([row])
    path = tmp_path / "audit_plan.csv"
    plan.to_csv(path, index=False)
    plan_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    route_hash = "a" * 64
    (tmp_path / "audit_plan_manifest.json").write_text(json.dumps({
        "routes_sha256": route_hash, "plan_sha256": plan_hash,
    }))
    write_route_audit_report(plan, tmp_path / "evidence", tmp_path)
    summary = json.loads((tmp_path / "route_review.json").read_text(encoding="utf-8"))
    assert summary["binding_status"] == "bound"
    assert summary["source_routes_sha256"] == route_hash
    assert summary["plan_sha256"] == plan_hash
    assert summary["destination_id"] == "TEST"
    assert summary["destination_lat"] == 1.3
    assert summary["destination_lon"] == 103.8
    assert summary["departure"] == DEPARTURE
    assert summary["mode"] == "TRANSIT"
    assert summary["adapter_version"] == row["adapter_version"]
    first_review_hash = summary["review_table_sha256"]
    plan.loc[0, "review_notes"] = "A different separate review"
    write_route_audit_report(plan, tmp_path / "evidence", tmp_path)
    summary = json.loads((tmp_path / "route_review.json").read_text(encoding="utf-8"))
    assert summary["binding_status"] == "bound"
    assert summary["review_table_sha256"] != first_review_hash


def test_missing_manifest_is_explicitly_unbound_without_inventing_route_hash(tmp_path):
    plan = pd.DataFrame([signed_row()])
    write_route_audit_report(plan, tmp_path / "evidence", tmp_path)
    summary = json.loads((tmp_path / "route_review.json").read_text(encoding="utf-8"))
    assert summary["binding_status"] == "unbound"
    assert summary["source_routes_sha256"] is None
    assert summary["plan_sha256"] is None
    assert "manifest_missing" in summary["binding_issues"]


def test_mixed_scene_or_mismatched_plan_hash_cannot_claim_binding(tmp_path):
    plan = pd.DataFrame([signed_row(), {**signed_row(), "location_id": "L01",
                                      "departure": "2026-10-19T09:00:00+08:00"}])
    path = tmp_path / "audit_plan.csv"
    plan.to_csv(path, index=False)
    (tmp_path / "audit_plan_manifest.json").write_text(json.dumps({
        "routes_sha256": "a" * 64, "plan_sha256": "b" * 64,
    }))
    write_route_audit_report(plan, tmp_path / "evidence", tmp_path)
    summary = json.loads((tmp_path / "route_review.json").read_text(encoding="utf-8"))
    assert summary["binding_status"] == "unbound"
    assert summary["departure"] is None
    assert "scene_not_unique:departure" in summary["binding_issues"]
    assert "frozen_plan_hash_mismatch" in summary["binding_issues"]
