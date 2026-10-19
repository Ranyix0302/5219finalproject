"""Synthetic artifact contracts; these fixtures are never Singapore results."""

import json
import re
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import Polygon

from ge5219.artifacts import write_json
from ge5219.result_report import create_result_report
from ge5219.settings import DEPARTURE, FEATURES, SCENARIOS


def _save_synthetic_bundle(path, *, key, sample="A", grouping="area_id", cap=None):
    path.mkdir(parents=True)
    result_id = f"mcda-synthetic-{key}"
    metadata = {"result_id": result_id, "dataset_version": "synthetic-contract-only",
                "status": "ok", "applied_weights": dict(zip(FEATURES, SCENARIOS[key]
                 if key in SCENARIOS else SCENARIOS["balanced"], strict=True)),
                "max_commute_min": cap, "group_by": grouping, "sample_set": sample,
                "destination_id": "NUS_AS8", "departure": DEPARTURE,
                "destination": {"latitude": 1.296, "longitude": 103.772},
                "source_routes_sha256": "synthetic-route-snapshot",
                "min_valid_share": .9, "min_feasible_share": .5}
    point = {"location_id": "p1", "area_id": "s1", "cluster_id": "c1",
             "latitude": 1.3, "longitude": 103.8, "is_feasible": True, "result_id": result_id}
    unit = {"unit_id": "c1" if grouping == "cluster_id" else "s1", "unit_name": "Synthetic only",
            "unit_type": "cluster" if grouping == "cluster_id" else "subzone",
            "rank": 1, "score": .7, "n_planned": 1, "n_valid": 1, "n_feasible": 1,
            "valid_share": 1.0, "verified_feasible_share": 1.0, "limited_support": True,
            "result_id": result_id, **{f"contribution_{feature}": .1 for feature in FEATURES}}
    write_json(path / "result_metadata.json", metadata)
    pd.DataFrame([point]).to_csv(path / "point_scores.csv", index=False)
    for table in ("area_scores", "top5"):
        pd.DataFrame([unit]).to_csv(path / f"{table}.csv", index=False)
    return unit


def _make_synthetic_artifacts(root: Path):
    prepared, score, experiments = root / "prepared", root / "score", root / "experiments"
    prepared.mkdir()
    experiments.mkdir()
    write_json(prepared / "data_quality.json", {"dataset_version": "synthetic-contract-only"})
    pd.DataFrame({"location_id": ["p1"], "sample_A": [True]}).to_csv(prepared / "analysis_locations.csv", index=False)
    gpd.GeoDataFrame({"area_id": ["s1"], "area_name": ["Synthetic only"]}, geometry=[
        Polygon([(103.79, 1.29), (103.81, 1.29), (103.81, 1.31), (103.79, 1.31)])], crs=4326
    ).to_file(prepared / "subzones.geojson", driver="GeoJSON")
    _save_synthetic_bundle(score, key="balanced")
    pd.DataFrame({"location_id": ["p1"], "sample_A": [True], "route_status": ["Success"],
                  **{feature: [1.0] for feature in FEATURES}}).to_csv(score / "indicator_matrix.csv", index=False)
    write_json(experiments / "experiment_manifest.json", {
        "context": {"dataset_version": "synthetic-contract-only", "destination_id": "NUS_AS8",
                    "departure": DEPARTURE, "source_routes_sha256": "synthetic-route-snapshot"},
        "seed": 42, "kappa": 50})
    write_json(experiments / "normalization_params.json", {feature: {"p05": 0.0, "p95": 2.0}
                                                              for feature in FEATURES})
    for name in SCENARIOS:
        _save_synthetic_bundle(experiments / f"scenario_{name}", key=name)
    for cap in (40, 60):
        _save_synthetic_bundle(experiments / f"commute_cap_{cap}", key=f"cap{cap}", cap=cap)
    for name in ("A_subzone", "B_subzone", "B_cluster"):
        directory = experiments / f"spatial_{name}"
        unit = _save_synthetic_bundle(directory, key=name, sample=name[0], cap=60,
                                     grouping="cluster_id" if name == "B_cluster" else "area_id")
        unit.update(n_building_records=1, extent_diagonal_m=0.0)
        pd.DataFrame([unit]).to_csv(directory / "selected_unit_support.csv", index=False)
    for prefix, count in (("monte_carlo", 1000), ("oat", 84)):
        pd.DataFrame({"run": range(count), "result_id": [f"synthetic-{i}" for i in range(count)],
                      **{feature: [1 / 7] * count for feature in FEATURES}}
        ).to_csv(experiments / f"{prefix}_weights.csv", index=False)
        pd.DataFrame({"run": range(count), "unit_id": ["s1"] * count, "rank": [1] * count,
                      "result_id": [f"synthetic-{i}" for i in range(count)]}
        ).to_csv(experiments / f"{prefix}_ranks.csv", index=False)
    pd.DataFrame({"unit_id": ["s1"], "selection_frequency": [1.0], "rank_median": [1],
                  "rank_p05": [1], "rank_p95": [1]}
    ).to_csv(experiments / "monte_carlo_frequency.csv", index=False)
    pd.DataFrame({"target_feature": list(FEATURES), "interval_start": [.05] * 7,
                  "interval_end": [.1] * 7, "top_k_jaccard": [1.0] * 7}
    ).to_csv(experiments / "oat_switch_intervals.csv", index=False)
    for name in ("qualification_comparisons", "scenario_comparisons"):
        pd.DataFrame({"left": ["synthetic"], "right": ["synthetic"], "top_k_jaccard": [1.0]}
        ).to_csv(experiments / f"{name}.csv", index=False)
    write_json(experiments / "spatial_comparison.json", {"jaccard_positions": 1.0})
    return prepared, score, experiments


def test_saved_artifact_report_is_offline_and_refuses_mixed_result_ids(tmp_path):
    prepared, score, experiments = _make_synthetic_artifacts(tmp_path)
    output = tmp_path / "synthetic-report.html"
    assert create_result_report(prepared, score, experiments, output) == output
    document = output.read_text(encoding="utf-8")
    assert "data:image/png;base64," in document
    assert 'src="https://' not in document
    assert "独立路线复核未完成" in document
    assert "不是居民选择概率" in document
    payload = json.loads(document.split('id="report-data">')[1].split("</script>")[0])
    assert payload["views"]["scenario_balanced"]["top"][0]["score"] == .7
    assert payload["context"]["dataset_version"] == "synthetic-contract-only"
    damaged = pd.read_csv(experiments / "scenario_balanced" / "top5.csv")
    damaged["result_id"] = "mcda-other-run"
    damaged.to_csv(experiments / "scenario_balanced" / "top5.csv", index=False)
    with pytest.raises(ValueError, match="Mixed result_id"):
        create_result_report(prepared, score, experiments, tmp_path / "rejected.html")
    assert not (tmp_path / "rejected.html").exists()


@pytest.mark.parametrize("threshold,value", [("min_valid_share", .8), ("min_feasible_share", .25)])
def test_report_refuses_saved_cap_results_with_other_qualification_rules(tmp_path, threshold, value):
    prepared, score, experiments = _make_synthetic_artifacts(tmp_path)
    metadata_path = experiments / "commute_cap_60" / "result_metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata[threshold] = value
    write_json(metadata_path, metadata)
    output = tmp_path / "wrong-qualification.html"
    with pytest.raises(ValueError, match="configuration differs"):
        create_result_report(prepared, score, experiments, output)
    assert not output.exists()


@pytest.mark.parametrize("binding_case", ["old_hash", "missing_binding", "current"])
def test_route_review_requires_binding_to_current_result_snapshot(tmp_path, binding_case):
    prepared, score, experiments = _make_synthetic_artifacts(tmp_path)
    audit = {"status": "synthetic_review_complete", "reviewed_count": 20, "required_count": 20,
             "method": "synthetic contract fixture only", "binding_status": "bound",
             "source_routes_sha256": "synthetic-route-snapshot", "destination_id": "NUS_AS8",
             "destination_lat": 1.296, "destination_lon": 103.772, "departure": DEPARTURE,
             "mode": "TRANSIT", "adapter_version": "synthetic-v1", "plan_sha256": "synthetic-plan",
             "reviewer_types": {"AI_assisted_desktop": 20}, "reviewed_concerns_count": 2,
             "limitations": ["Synthetic same-provider limitation"]}
    if binding_case == "old_hash":
        audit["source_routes_sha256"] = "another-route-snapshot"
    elif binding_case == "missing_binding":
        del audit["binding_status"]
    write_json(score / "route_review.json", audit)
    output = tmp_path / "audit-binding.html"
    create_result_report(prepared, score, experiments, output)
    document = output.read_text(encoding="utf-8")
    if binding_case == "current":
        assert "记录复核 20 / 20 条" in document
        assert "AI 辅助桌面审阅：20" in document
        assert "带问题/限制的已复核案例：2" in document
        assert "不是独立数据源验证，也不是实地通勤验证" in document
        assert "Synthetic same-provider limitation" in document
    else:
        assert "独立路线复核未匹配当前快照" in document
        assert "记录复核 20 / 20 条" not in document
        assert "synthetic_review_complete" in document


def test_english_report_localizes_ui_and_figures_and_preserves_saved_values(tmp_path, monkeypatch):
    import matplotlib.pyplot as plt
    from matplotlib.text import Text

    import ge5219.result_report as report

    prepared, score, experiments = _make_synthetic_artifacts(tmp_path)
    original_inputs = {path: path.read_bytes() for path in tmp_path.rglob("*.csv")}
    figure_text = []

    def capture_figure(figure, output):
        figure_text.extend(artist.get_text() for artist in figure.findobj(Text))
        plt.close(figure)
        return "data:image/png;base64,c3ludGhldGlj"

    monkeypatch.setattr(report, "_figure_data", capture_figure)
    output = tmp_path / "english-report.html"
    create_result_report(prepared, score, experiments, output, language="en")
    document = output.read_text(encoding="utf-8")
    data = json.loads(document.split('id="report-data">')[1].split("</script>")[0])
    reader_facing = re.sub(r'<script type="application/json" id="report-data">.*?</script>', "", document, flags=re.DOTALL)
    assert '<html lang="en">' in document
    assert "Preference scenario" in reader_facing
    assert "Limited: fewer than 3 valid locations" in reader_facing
    assert "not a resident choice probability" in reader_facing
    assert "Route review is incomplete" in reader_facing
    assert not re.search(r"[\u3400-\u9fff]", reader_facing)
    assert figure_text and not any(re.search(r"[\u3400-\u9fff]", value) for value in figure_text)
    assert "Campus trip" in figure_text
    assert "SVY21 easting / m" in figure_text
    assert len(data["views"]) == 6 and len(data["arms"]) == 3
    saved = data["views"]["scenario_balanced"]
    assert saved["top"][0]["score"] == .7
    assert saved["metadata"]["applied_weights"] == dict(zip(FEATURES, SCENARIOS["balanced"], strict=True))
    assert saved["metadata"]["result_id"] == "mcda-synthetic-balanced"
    assert all(path.read_bytes() == value for path, value in original_inputs.items())


def test_english_source_limitations_require_explicit_translation():
    from ge5219.result_report import ENGLISH_SOURCE_NOTES, _audit_review_details

    audit = {"reviewer_types": {"AI_assisted_desktop": 21}, "reviewed_concerns_count": 6,
             "limitations": list(ENGLISH_SOURCE_NOTES)}
    translated = _audit_review_details(audit, "en")
    assert "AI-assisted desktop review: 21" in translated
    assert all(value in translated for value in ENGLISH_SOURCE_NOTES.values())
    assert not re.search(r"[\u3400-\u9fff]", translated)
    with pytest.raises(ValueError, match="English translation is required"):
        _audit_review_details({"limitations": ["新增的未翻译限制"]}, "en")


def test_result_report_rejects_unknown_language_before_reading_inputs(tmp_path):
    with pytest.raises(ValueError, match="language"):
        create_result_report(tmp_path, tmp_path, tmp_path, tmp_path / "unsupported.html", language="fr")
