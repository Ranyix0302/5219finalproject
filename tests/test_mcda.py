"""Synthetic acceptance examples for the deterministic recommendation boundary."""

import numpy as np
import pandas as pd
import pytest

from ge5219.mcda import fit_normalization, normalize_indicators, recommend
from ge5219.settings import COST_FEATURES, FEATURES, SCENARIOS


def measured_points(values):
    """Create explicitly synthetic measurements with known percentile bounds."""
    frame = pd.DataFrame({feature: values for feature in FEATURES})
    frame["route_status"] = "Success"
    return frame


def test_fixed_percentiles_clip_and_reverse_costs_without_replacing_raw_values():
    baseline = measured_points([0.0, 25.0, 50.0, 75.0, 100.0])
    params = fit_normalization(baseline)
    result = normalize_indicators(measured_points([-1.0, 0.0, 27.5, 100.0]), params)

    assert params["campus_transit_min"] == {"p05": 5.0, "p95": 95.0, "direction": "cost"}
    assert result["campus_transit_min"].tolist() == [-1.0, 0.0, 27.5, 100.0]
    np.testing.assert_allclose(result["z_campus_transit_min"], [np.nan, 1.0, 0.75, 0.0])
    np.testing.assert_allclose(result["z_bus_stops_800m"], [np.nan, 0.0, 0.25, 1.0])


def fixed_params():
    return {
        feature: {"p05": 0.0, "p95": 100.0,
                  "direction": "cost" if feature in COST_FEATURES else "benefit"}
        for feature in FEATURES
    }


def planned_points(values):
    frame = measured_points(values)
    frame["location_id"] = [f"p{i}" for i in range(len(frame))]
    frame["area_id"] = "A"
    frame["area_name"] = "Synthetic area A"
    frame["cluster_id"] = "C"
    frame["cluster_name"] = "Synthetic cluster C"
    return frame


def test_recommendation_averages_feasible_point_contributions_and_returns_named_units():
    frame = planned_points([20.0, 60.0, 50.0, 90.0])
    frame.loc[2, ["area_id", "area_name"]] = ["B", "Synthetic area B"]
    frame.loc[3, ["area_id", "area_name"]] = ["C", "Synthetic area C"]
    result = recommend(frame, fixed_params(), SCENARIOS["balanced"])

    assert result["top5"]["unit_id"].tolist() == ["A", "B", "C"]
    np.testing.assert_allclose(result["top5"]["score"], [0.53, 0.5, 0.38])
    assert result["top5"]["unit_name"].tolist()[0] == "Synthetic area A"
    assert result["top5"]["limited_support"].all()
    assert result["metadata"]["status"] == "ok"
    assert result["metadata"]["applied_weights"]["campus_transit_min"] == 0.25
    assert result["point_scores"]["score"].iloc[0] == pytest.approx(0.59)
    assert result["top5"]["contribution_campus_transit_min"].iloc[0] == pytest.approx(0.15)
    assert result["metadata"]["result_id"] == result["area_scores"]["result_id"].iloc[0]


def test_eligibility_uses_planned_denominators_and_retains_unknown_routes():
    frame = planned_points([50.0] * 20)
    frame.loc[:8, "campus_transit_min"] = 20.0
    frame.loc[9:17, "campus_transit_min"] = 80.0
    frame.loc[18:, "campus_transit_min"] = 0.0
    frame.loc[18:, "route_status"] = ["HTTPError", "No_Route"]
    result = recommend(frame, fixed_params(), [1, 0, 0, 0, 0, 0, 0], max_commute_min=60)
    area = result["area_scores"].iloc[0]

    assert len(result["point_scores"]) == 20
    assert (area["n_planned"], area["n_valid"], area["n_feasible"]) == (20, 18, 9)
    assert area["valid_share"] == 0.9
    assert area["conditional_feasible_share"] == 0.5
    assert area["verified_feasible_share"] == 0.45
    assert not area["eligible"]
    assert result["point_scores"].loc[18:, "score"].isna().all()
    assert result["point_scores"].loc[18:, "feasibility_status"].tolist() == ["unknown", "unknown"]
    assert result["metadata"]["status"] == "no_feasible_results"


def test_measurement_coverage_failure_has_a_distinct_result_status():
    frame = planned_points([10.0] * 10)
    frame.loc[8:, "bus_stops_800m"] = np.nan
    result = recommend(frame, fixed_params(), SCENARIOS["balanced"])

    assert result["metadata"]["status"] == "data_coverage_insufficient"
    assert result["top5"].empty
    assert result["area_scores"]["n_feasible"].iloc[0] == 8


@pytest.mark.parametrize("weights", [
    [0] * 7, [-1, 1, 1, 1, 1, 1, 1], [np.nan] * 7, [np.inf] * 7,
    [1] * 6, [[1] * 7], {FEATURES[0]: 1}, None, "invalid", [True] * 7,
])
def test_invalid_importance_values_are_rejected_even_with_complete_measurements(weights):
    with pytest.raises(ValueError):
        recommend(planned_points([20.0]), fixed_params(), weights)


@pytest.mark.parametrize("kwargs", [
    {"k": 0}, {"k": -1}, {"k": 1.5}, {"k": True},
    {"group_by": "postal_code"}, {"max_commute_min": -1},
    {"max_commute_min": np.inf}, {"max_commute_min": np.nan},
    {"min_valid_share": 1.1}, {"min_valid_share": np.nan},
    {"min_feasible_share": -0.1}, {"min_feasible_share": "invalid"},
    {"metadata": ["invalid"]},
])
def test_invalid_recommendation_parameters_raise_a_clear_value_error(kwargs):
    with pytest.raises(ValueError):
        recommend(planned_points([20.0]), fixed_params(), SCENARIOS["balanced"], **kwargs)


@pytest.mark.parametrize("source", ["metadata", "column"])
def test_unsupported_campus_never_reuses_the_nus_measurements(source):
    frame = planned_points([20.0, 30.0])
    metadata = {"destination_id": "NTU"} if source == "metadata" else None
    if source == "column":
        frame["destination_id"] = "NTU"
    result = recommend(frame, fixed_params(), SCENARIOS["balanced"], metadata=metadata)

    assert result["metadata"]["status"] == "unsupported_destination"
    assert result["top5"].empty
    assert len(result["point_scores"]) == 2
    assert result["point_scores"]["score"].isna().all()


def test_exact_ties_use_raw_commute_then_rail_then_stable_unit_id():
    frame = planned_points([50.0] * 4)
    frame["area_id"] = ["A", "B", "D", "C"]
    frame["area_name"] = ["Synthetic " + value for value in frame["area_id"]]
    frame["campus_transit_min"] = [20.0, 10.0, 10.0, 10.0]
    frame["rail_exit_euclid_m"] = [100.0, 200.0, 100.0, 100.0]
    result = recommend(frame, fixed_params(), [0, 0, 1, 0, 0, 0, 0])

    assert result["top5"]["unit_id"].tolist() == ["C", "D", "B", "A"]
    assert result["top5"]["rank"].tolist() == [1, 2, 3, 4]


def test_result_identity_is_stable_across_row_order_and_changes_with_data_or_configuration():
    frame = planned_points([20.0, 30.0, 40.0])
    original = recommend(frame, fixed_params(), SCENARIOS["balanced"],
                         metadata={"dataset_version": "synthetic-v1"})
    reordered = recommend(frame.iloc[::-1], fixed_params(), SCENARIOS["balanced"],
                          metadata={"dataset_version": "synthetic-v1"})
    changed = frame.copy()
    changed.loc[0, "campus_transit_min"] = 21.0
    changed_result = recommend(changed, fixed_params(), SCENARIOS["balanced"],
                               metadata={"dataset_version": "synthetic-v1"})
    changed_version = recommend(frame, fixed_params(), SCENARIOS["balanced"],
                                metadata={"dataset_version": "synthetic-v2"})

    assert original["metadata"]["result_id"] == reordered["metadata"]["result_id"]
    assert original["metadata"]["result_id"] != changed_result["metadata"]["result_id"]
    assert original["metadata"]["result_id"] != changed_version["metadata"]["result_id"]
    pd.testing.assert_frame_equal(original["top5"], reordered["top5"])


@pytest.mark.parametrize("problem", ["duplicate_location", "missing_location", "missing_area",
                                     "inconsistent_name", "missing_dimension", "missing_status"])
def test_incomplete_or_ambiguous_planned_point_schema_is_rejected(problem):
    frame = planned_points([20.0, 30.0])
    if problem == "duplicate_location":
        frame["location_id"] = "p0"
    if problem == "missing_location":
        frame.loc[1, "location_id"] = None
    if problem == "missing_area":
        frame.loc[1, "area_id"] = None
    if problem == "inconsistent_name":
        frame.loc[1, "area_name"] = "Another name for the same ID"
    if problem == "missing_dimension":
        frame = frame.drop(columns=[FEATURES[-1]])
    if problem == "missing_status":
        frame = frame.drop(columns=["route_status"])
    with pytest.raises(ValueError):
        recommend(frame, fixed_params(), SCENARIOS["balanced"])


def test_empty_planned_input_returns_an_explicit_coverage_state_and_empty_tables():
    result = recommend(planned_points([]), fixed_params(), SCENARIOS["balanced"])
    assert result["metadata"]["status"] == "data_coverage_insufficient"
    assert result["point_scores"].empty
    assert result["area_scores"].empty
    assert result["top5"].empty
    assert "n_planned" in result["area_scores"]


def test_missing_nullable_route_status_cannot_certify_observed_minutes():
    frame = planned_points([20.0, 30.0])
    frame["route_status"] = pd.Series(["Success", pd.NA], dtype="string")
    result = recommend(frame, fixed_params(), SCENARIOS["balanced"])
    assert result["point_scores"]["is_valid"].tolist() == [True, False]
    assert pd.isna(result["point_scores"]["z_campus_transit_min"].iloc[1])


def test_constraints_apply_raw_minutes_before_clipping_and_keep_the_inclusive_boundary():
    frame = planned_points([20.0, 80.0])
    params = fixed_params()
    params["campus_transit_min"]["p95"] = 50.0
    result = recommend(frame, params, SCENARIOS["balanced"], max_commute_min=20)

    assert result["point_scores"]["is_feasible"].tolist() == [True, False]
    assert result["point_scores"]["z_campus_transit_min"].tolist() == [0.6, 0.0]
    assert result["area_scores"]["n_feasible"].iloc[0] == 1


def test_fitting_ignores_failed_campus_routes_and_rejects_constant_dimensions():
    frame = measured_points([0.0, 25.0, 50.0, 75.0, 100.0, 999.0])
    frame.loc[5, "route_status"] = "No_Route"
    params = fit_normalization(frame)
    assert params["campus_transit_min"]["p05"] == 5.0
    assert params["campus_transit_min"]["p95"] == 95.0
    frame["library_euclid_m"] = 10.0
    with pytest.raises(ValueError, match="library_euclid_m"):
        fit_normalization(frame)


def test_zero_weight_dimensions_still_require_valid_measurements_and_nonconstant_bounds():
    frame = planned_points([20.0, 30.0])
    frame.loc[1, "library_euclid_m"] = np.nan
    result = recommend(frame, fixed_params(), [1, 0, 0, 0, 0, 0, 0])
    assert result["point_scores"]["is_valid"].tolist() == [True, False]
    params = fixed_params()
    params["library_euclid_m"]["p95"] = 0.0
    with pytest.raises(ValueError, match="library_euclid_m"):
        recommend(frame, params, [1, 0, 0, 0, 0, 0, 0])


def test_full_precision_score_precedes_the_raw_value_tie_breakers():
    frame = planned_points([50.0, 50.0])
    frame["area_id"] = ["A", "B"]
    frame["area_name"] = ["Synthetic A", "Synthetic B"]
    frame["bus_stops_800m"] = [50.0, 50.0000000001]
    frame["campus_transit_min"] = [1.0, 100.0]
    result = recommend(frame, fixed_params(), [0, 0, 1, 0, 0, 0, 0])
    assert result["top5"]["unit_id"].tolist() == ["B", "A"]


def test_cluster_ranking_uses_the_same_coverage_and_named_output_contract():
    frame = planned_points([0.0, 50.0, 100.0])
    frame["cluster_id"] = ["C1", "C1", "C2"]
    frame["cluster_name"] = ["Synthetic C1", "Synthetic C1", "Synthetic C2"]
    result = recommend(frame, fixed_params(), {feature: 1.0 for feature in FEATURES},
                       group_by="cluster_id")
    assert result["top5"]["unit_id"].tolist() == ["C1", "C2"]
    assert result["top5"]["unit_type"].tolist() == ["cluster", "cluster"]
    assert result["metadata"]["applied_weights"][FEATURES[0]] == pytest.approx(1 / 7)


def test_numeric_importance_is_normalized_visibly_without_overflow():
    result = recommend(planned_points([20.0]), fixed_params(), [1e308] * 7)
    assert result["metadata"]["applied_weights"][FEATURES[0]] == pytest.approx(1 / 7)
    assert result["point_scores"]["score"].iloc[0] == pytest.approx(19 / 35)


def test_unknown_conditional_share_is_not_presented_as_zero_percent():
    frame = planned_points([20.0])
    frame["route_status"] = "HTTPError"
    result = recommend(frame, fixed_params(), SCENARIOS["balanced"])
    area = result["area_scores"].iloc[0]
    assert area["valid_share"] == 0.0
    assert area["verified_feasible_share"] == 0.0
    assert pd.isna(area["conditional_feasible_share"])
    assert pd.isna(area["score"])


@pytest.mark.parametrize("frame", [None, [], {"campus_transit_min": [10.0]}])
def test_non_table_inputs_raise_the_documented_parameter_error(frame):
    with pytest.raises(ValueError):
        recommend(frame, fixed_params(), SCENARIOS["balanced"])
