"""Experiments use synthetic fixtures; none are measured Singapore results."""

import pandas as pd
import pytest

from ge5219.experiments import compare_rankings, compare_spatial_selections, run_experiments
from ge5219.settings import COST_FEATURES, FEATURES


def test_rank_comparison_reports_common_candidates_and_different_order():
    first = pd.DataFrame({"unit_id": ["a", "b", "c"], "rank": [1, 2, 3]})
    second = pd.DataFrame({"unit_id": ["b", "a", "d"], "rank": [1, 2, 3]})
    observed = compare_rankings(first, second, k=2)
    assert observed["top_k_jaccard"] == 1.0
    assert observed["n_common"] == 2
    assert observed["spearman"] == pytest.approx(-1.0)


def test_empty_lists_do_not_claim_perfect_robustness():
    empty = pd.DataFrame(columns=["unit_id", "rank"])
    observed = compare_rankings(empty, empty)
    assert observed["top_k_jaccard"] is None
    assert observed["spearman"] is None


def test_spatial_comparison_maps_different_unit_types_to_common_positions():
    common = pd.DataFrame({
        "location_id": ["p1", "p2", "p3"],
        "area_id": ["s1", "s1", "s2"],
        "cluster_id": ["c1", "c2", "c3"],
    })
    observed = compare_spatial_selections(common, {"s1"}, {"c2"})
    assert observed["jaccard_positions"] == 0.5
    assert observed["n_subzone_positions"] == 2
    assert observed["n_cluster_positions"] == 1


def test_experiment_bundle_keeps_1000_draws_and_all_three_spatial_arms(tmp_path):
    frame = pd.DataFrame({
        "location_id": ["p1", "p2", "p3"], "building_id": ["b1", "b2", "b3"],
        "area_id": ["s1", "s2", "s2"], "area_name": ["ONE", "TWO", "TWO"],
        "cluster_id": ["c1", "c2", "c3"], "cluster_name": ["ONE C1", "TWO C2", "TWO C3"],
        "sample_A": [True, True, False], "route_status": ["Success"] * 3,
        **{feature: [20.0, 40.0, 70.0] for feature in FEATURES},
    })
    params = {feature: {"p05": 0.0, "p95": 100.0,
                       "direction": "cost" if feature in COST_FEATURES else "benefit"}
              for feature in FEATURES}
    manifest = run_experiments(frame, params, tmp_path, make_plots=False)
    draws = pd.read_csv(tmp_path / "monte_carlo_weights.csv")
    assert len(draws) == 1000
    assert manifest["seed"] == 42
    assert set(manifest["spatial_arms"]) == {"A_subzone", "B_subzone", "B_cluster"}
    assert manifest["spatial_commute_cap_min"] == 60
    assert pd.read_csv(tmp_path / "spatial_B_cluster" / "area_scores.csv").shape[0] == 3
