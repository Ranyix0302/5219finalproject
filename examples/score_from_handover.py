"""Re-score the frozen handover through public APIs without routing requests."""

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from ge5219.artifacts import read_locations, save_result, write_json
from ge5219.mcda import recommend
from ge5219.pipeline import assemble_matrix
from ge5219.settings import FEATURES, SCENARIOS

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "outputs" / "interface_acceptance"


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compare_saved(result, directory):
    saved = read_locations(directory / "top5.csv")
    assert result["top5"].unit_id.tolist() == saved.unit_id.tolist()
    np.testing.assert_allclose(result["top5"].score, saved.score, rtol=0, atol=1e-12)
    assert int(result["area_scores"].eligible.sum()) == int(
        read_locations(directory / "area_scores.csv").eligible.sum()
    )


def main():
    prepared = ROOT / "outputs" / "prepared"
    route_path = ROOT / "outputs" / "routes.csv"
    normalization_path = ROOT / "outputs" / "normalization-v1.json"
    baseline_directory = ROOT / "outputs" / "score"
    frozen_paths = [
        prepared / "static_indicators.csv",
        route_path,
        normalization_path,
        *baseline_directory.glob("*"),
    ]
    hashes_before = {str(path.relative_to(ROOT)): sha256(path) for path in frozen_paths}
    metadata = read_json(baseline_directory / "result_metadata.json")
    normalization = read_json(normalization_path)
    assert normalization["dataset_version"] == metadata["dataset_version"]
    assert sha256(route_path) == metadata["source_routes_sha256"]
    assert sha256(prepared / "static_indicators.csv") == metadata["static_measurements_sha256"]
    matrix = assemble_matrix(
        read_locations(prepared / "static_indicators.csv"),
        read_locations(route_path),
        metadata["destination"],
    )
    baseline = matrix.loc[matrix.sample_A].copy()
    fingerprint = hashlib.sha256(
        pd.util.hash_pandas_object(
            baseline.sort_values("location_id")[["location_id", *FEATURES, "route_status"]],
            index=False,
        )
        .to_numpy()
        .tobytes()
    ).hexdigest()
    assert fingerprint == normalization["baseline_measurements_sha256"]
    result_keys = {
        "result_id",
        "status",
        "applied_weights",
        "group_by",
        "max_commute_min",
        "min_valid_share",
        "min_feasible_share",
    }
    context = {key: value for key, value in metadata.items() if key not in result_keys}
    params = normalization["parameters"]
    summary = {}
    cases = [
        ("baseline", baseline, {}, SCENARIOS["balanced"], context),
        ("cap40", baseline, {"max_commute_min": 40}, SCENARIOS["balanced"], context),
        ("cap60", baseline, {"max_commute_min": 60}, SCENARIOS["balanced"], context),
        ("custom_weights", baseline, {}, [3, 2, 1, 1, 1, 1, 1], context),
        (
            "qualification75",
            baseline,
            {"max_commute_min": 60, "min_feasible_share": 0.75},
            SCENARIOS["balanced"],
            context,
        ),
        ("top3", baseline, {"k": 3}, SCENARIOS["balanced"], context),
        (
            "B_cluster",
            matrix,
            {"group_by": "cluster_id", "max_commute_min": 60},
            SCENARIOS["balanced"],
            {**context, "sample_set": "B"},
        ),
        ("cap0_no_results", baseline, {"max_commute_min": 0}, SCENARIOS["balanced"], context),
    ]
    for name, frame, options, weights, case_context in cases:
        result = recommend(frame, params, weights, metadata=case_context, **options)
        save_result(result, OUTPUT / name)
        for key in ("point_scores", "area_scores", "top5"):
            assert result[key].result_id.eq(result["metadata"]["result_id"]).all()
        write_json(
            OUTPUT / name / "response.json",
            {
                "metadata": result["metadata"],
                "top5": result["top5"].to_dict(orient="records"),
            },
        )
        summary[name] = {
            "result_id": result["metadata"]["result_id"],
            "status": result["metadata"]["status"],
            "n_planned": len(result["point_scores"]),
            "eligible_units": int(result["area_scores"].eligible.sum()),
            "top_names": result["top5"].unit_name.tolist(),
            "applied_weights": result["metadata"]["applied_weights"],
        }
        if name == "baseline":
            assert result["metadata"]["result_id"] == metadata["result_id"]
            compare_saved(result, baseline_directory)
        comparison = {
            "cap40": "commute_cap_40",
            "cap60": "commute_cap_60",
            "qualification75": "qualification_75",
            "B_cluster": "spatial_B_cluster",
        }
        if name in comparison:
            compare_saved(result, ROOT / "outputs" / "experiments" / comparison[name])
        if name == "top3":
            assert len(result["top5"]) == 3
        if name == "cap0_no_results":
            assert result["metadata"]["status"] == "no_feasible_results"
        if name == "custom_weights":
            np.testing.assert_allclose(
                list(result["metadata"]["applied_weights"].values()),
                [0.3, 0.2, 0.1, 0.1, 0.1, 0.1, 0.1],
                rtol=0,
                atol=1e-15,
            )
    assert all(sha256(ROOT / path) == digest for path, digest in hashes_before.items())
    write_json(
        OUTPUT / "acceptance_summary.json",
        {
            "status": "passed",
            "no_route_client_imported_or_called": True,
            "frozen_inputs_and_baseline_unchanged": True,
            "normalization_dataset_and_A_fingerprint_verified": True,
            "case_count": len(summary),
            "cases": summary,
        },
    )
    print(
        json.dumps(
            {"status": "passed", "cases": len(summary), "output": str(OUTPUT)}, ensure_ascii=False
        )
    )


if __name__ == "__main__":
    main()
