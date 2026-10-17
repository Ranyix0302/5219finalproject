"""Deterministic, seven-dimension MCDA with explicit measurement coverage."""

import hashlib
import json
from collections.abc import Mapping
from numbers import Integral, Real

import numpy as np
import pandas as pd

from ge5219.settings import ANALYSIS_VERSION, COST_FEATURES, DESTINATION_ID, FEATURES


def _observed_indicators(frame):
    if not isinstance(frame, pd.DataFrame) or not frame.columns.is_unique:
        raise ValueError("Measurements must be a DataFrame with unique column names")
    required = set(FEATURES) | {"route_status"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"Missing required measurement columns: {sorted(missing)}")
    observed = frame.loc[:, FEATURES].apply(pd.to_numeric, errors="coerce")
    observed = observed.where(np.isfinite(observed) & observed.ge(0))
    observed.loc[~frame["route_status"].eq("Success").fillna(False), FEATURES[0]] = np.nan
    return observed


def fit_normalization(frame_A: pd.DataFrame) -> dict:
    """Fit separate P5/P95 bounds on observed, nonnegative baseline measurements.

    Campus minutes are observed only when route_status is Success. Bounds must
    be defined and nonconstant for all seven dimensions, including zero-weight
    dimensions. The returned parameters remain fixed across scoring scenarios.
    """
    observed = _observed_indicators(frame_A)
    params = {}
    for feature in FEATURES:
        lower, upper = observed[feature].quantile([0.05, 0.95])
        if not np.isfinite([lower, upper]).all() or lower >= upper:
            raise ValueError(f"Undefined or constant P5/P95 bounds for {feature}")
        params[feature] = {
            "p05": float(lower),
            "p95": float(upper),
            "direction": "cost" if feature in COST_FEATURES else "benefit",
        }
    return params


def normalize_indicators(frame: pd.DataFrame, params: dict) -> pd.DataFrame:
    """Retain raw inputs and add clipped 0–1 scores; invalid observations stay NaN."""
    observed = _observed_indicators(frame)
    result = frame.copy()
    if not isinstance(params, Mapping) or set(params) != set(FEATURES):
        raise ValueError("Normalization parameters must cover exactly seven indicators")
    for feature in FEATURES:
        config = params[feature]
        try:
            lower, upper = float(config["p05"]), float(config["p95"])
            direction = config["direction"]
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"Invalid normalization parameters for {feature}") from exc
        expected_direction = "cost" if feature in COST_FEATURES else "benefit"
        if not np.isfinite([lower, upper]).all() or lower < 0 or lower >= upper:
            raise ValueError(f"Undefined or constant P5/P95 bounds for {feature}")
        if direction != expected_direction:
            raise ValueError(f"Unexpected indicator direction for {feature}")
        score = (observed[feature].clip(lower, upper) - lower) / (upper - lower)
        result[f"z_{feature}"] = 1 - score if direction == "cost" else score
    return result


def _apply_weights(weights):
    if isinstance(weights, Mapping):
        if set(weights) != set(FEATURES):
            raise ValueError("Weights must cover exactly seven indicators")
        weights = [weights[feature] for feature in FEATURES]
    try:
        original = np.asarray(weights, dtype=object)
        if any(isinstance(item, (bool, np.bool_)) for item in original.flat):
            raise ValueError("Boolean values are not importance weights")
        values = np.asarray(weights, dtype=float)
    except (TypeError, ValueError) as exc:
        raise ValueError("Weights must be seven nonnegative finite numbers") from exc
    if values.shape != (len(FEATURES),) or not np.isfinite(values).all():
        raise ValueError("Weights must be seven nonnegative finite numbers")
    if (values < 0).any() or not (values > 0).any():
        raise ValueError("Weights must be nonnegative and not all zero")
    scaled = values / values.max()
    return dict(zip(FEATURES, (scaled / scaled.sum()).tolist()))


def _validate_options(group_by, max_commute_min, min_valid_share, min_feasible_share, metadata, k):
    if group_by not in ("area_id", "cluster_id"):
        raise ValueError("group_by must be area_id or cluster_id")
    if not isinstance(k, Integral) or isinstance(k, bool) or k <= 0:
        raise ValueError("k must be a positive integer")
    for name, value in (("min_valid_share", min_valid_share),
                        ("min_feasible_share", min_feasible_share)):
        if not isinstance(value, Real) or isinstance(value, bool):
            # The public API promises ValueError for every invalid caller parameter.
            raise ValueError(f"{name} must be a finite number in [0, 1]")  # noqa: TRY004
        if not np.isfinite(float(value)) or not 0 <= float(value) <= 1:
            raise ValueError(f"{name} must be a finite number in [0, 1]")
    if max_commute_min is not None:
        if not isinstance(max_commute_min, Real) or isinstance(max_commute_min, bool):
            raise ValueError("max_commute_min must be a finite nonnegative number or None")
        if not np.isfinite(float(max_commute_min)) or float(max_commute_min) < 0:
            raise ValueError("max_commute_min must be a finite nonnegative number or None")
    if metadata is not None and not isinstance(metadata, Mapping):
        raise ValueError("metadata must be a mapping or None")


def _validate_planned_points(frame, group_by):
    name_column = "area_name" if group_by == "area_id" else "cluster_name"
    for column in ("location_id", group_by, name_column):
        if column not in frame:
            raise ValueError(f"Missing planned-point column: {column}")
        if not frame[column].map(lambda value: isinstance(value, str) and bool(value.strip())).all():
            raise ValueError(f"{column} must contain nonempty string IDs or names")
    if frame["location_id"].duplicated().any():
        raise ValueError("location_id must be unique across all planned positions")
    if frame.groupby(group_by)[name_column].nunique().gt(1).any():
        raise ValueError(f"Each {group_by} must have exactly one consistent name")


def _json_value(value):
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, np.ndarray)):
        return [_json_value(item) for item in value]
    if isinstance(value, np.generic):
        return _json_value(value.item())
    if value is None or value is pd.NA:
        return None
    if isinstance(value, float) and not np.isfinite(value):
        return str(value)
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _make_result_id(frame, configuration):
    ordered = frame.sort_values("location_id").reindex(sorted(frame.columns), axis=1)
    payload = {"configuration": configuration, "points": ordered.to_dict(orient="records")}
    encoded = json.dumps(_json_value(payload), sort_keys=True, separators=(",", ":"))
    return "mcda-" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:24]


def _aggregate_points(points, group_by, min_valid_share, min_feasible_share):
    name_column = "area_name" if group_by == "area_id" else "cluster_name"
    rows = []
    for unit_id, group in points.groupby(group_by, sort=True):
        group = group.sort_values("location_id")
        feasible = group.loc[group["is_feasible"]]
        n_planned, n_valid, n_feasible = len(group), int(group["is_valid"].sum()), len(feasible)
        row = {
            "unit_id": unit_id, "unit_name": group[name_column].iloc[0],
            "unit_type": "subzone" if group_by == "area_id" else "cluster",
            "n_planned": n_planned, "n_valid": n_valid, "n_feasible": n_feasible,
            "valid_share": n_valid / n_planned,
            "conditional_feasible_share": n_feasible / n_valid if n_valid else np.nan,
            "verified_feasible_share": n_feasible / n_planned,
            "limited_support": n_valid < 3,
            "eligible": n_valid / n_planned >= min_valid_share
            and n_feasible / n_planned >= min_feasible_share and n_feasible > 0,
            "score": feasible["score"].mean(), "score_std": feasible["score"].std(ddof=0),
            "score_min": feasible["score"].min(), "score_max": feasible["score"].max(),
            "mean_commute_min": pd.to_numeric(feasible[FEATURES[0]]).mean(),
            "mean_rail_exit_euclid_m": pd.to_numeric(feasible[FEATURES[1]]).mean(),
        }
        row.update({f"contribution_{feature}": feasible[f"contribution_{feature}"].mean()
                    for feature in FEATURES})
        rows.append(row)
    columns = ["unit_id", "unit_name", "unit_type", "n_planned", "n_valid", "n_feasible",
               "valid_share", "conditional_feasible_share", "verified_feasible_share",
               "limited_support", "eligible", "score", "score_std", "score_min", "score_max",
               "mean_commute_min", "mean_rail_exit_euclid_m"]
    columns += [f"contribution_{feature}" for feature in FEATURES]
    return pd.DataFrame(rows, columns=columns).astype({"eligible": bool, "limited_support": bool})


def recommend(frame: pd.DataFrame, params: dict, weights, group_by="area_id",
              max_commute_min=None, min_valid_share=0.9, min_feasible_share=0.5,
              metadata=None, k=5) -> dict:
    """Score planned locations and rank eligible named Subzones or analysis clusters.

    All planned rows remain in point_scores. Complete seven-dimensional observed
    measurements are required regardless of weights. Constraints use raw minutes;
    unknown observations never become zeros or verified feasible positions.
    """
    _validate_options(group_by, max_commute_min, min_valid_share, min_feasible_share, metadata, k)
    applied_weights = _apply_weights(weights)
    points = normalize_indicators(frame, params)
    _validate_planned_points(points, group_by)
    destination_supported = (metadata or {}).get("destination_id", DESTINATION_ID) == DESTINATION_ID
    if "destination_id" in frame:
        destination_supported &= bool(frame["destination_id"].eq(DESTINATION_ID).fillna(False).all())
    points["is_valid"] = points[[f"z_{feature}" for feature in FEATURES]].notna().all(axis=1)
    points["is_valid"] &= destination_supported
    points["is_feasible"] = points["is_valid"]
    if max_commute_min is not None:
        points["is_feasible"] &= pd.to_numeric(points[FEATURES[0]], errors="coerce").le(max_commute_min)
    points["measurement_status"] = np.where(points["is_valid"], "valid", "invalid_measurement")
    points["feasibility_status"] = np.select(
        [~points["is_valid"], points["is_feasible"]],
        ["unknown", "feasible"], default="commute_exceeds_limit",
    )
    if not destination_supported:
        points["feasibility_status"] = "unsupported_destination"
    for feature in FEATURES:
        points[f"contribution_{feature}"] = (
            points[f"z_{feature}"] * applied_weights[feature]
        ).where(points["is_feasible"])
    contribution_columns = [f"contribution_{feature}" for feature in FEATURES]
    points["score"] = points[contribution_columns].sum(axis=1, min_count=len(FEATURES))
    areas = _aggregate_points(points, group_by, min_valid_share, min_feasible_share)
    areas = areas.sort_values(["score", "mean_commute_min", "mean_rail_exit_euclid_m", "unit_id"],
                              ascending=[False, True, True, True]).reset_index(drop=True)
    areas["rank"] = pd.Series(pd.NA, index=areas.index, dtype="Int64")
    areas.loc[areas["eligible"], "rank"] = np.arange(1, int(areas["eligible"].sum()) + 1)
    config = {"params": params, "applied_weights": applied_weights, "group_by": group_by,
              "max_commute_min": max_commute_min, "min_valid_share": min_valid_share,
              "min_feasible_share": min_feasible_share, "k": k, "metadata": metadata or {},
              "analysis_version": ANALYSIS_VERSION}
    result_id = _make_result_id(frame, config)
    points["result_id"], areas["result_id"] = result_id, result_id
    status = "ok" if areas["eligible"].any() else "no_feasible_results"
    if not areas["valid_share"].ge(min_valid_share).any():
        status = "data_coverage_insufficient"
    if not destination_supported:
        status = "unsupported_destination"
    result_metadata = dict(metadata or {})
    result_metadata.update({"result_id": result_id, "status": status,
                            "analysis_version": ANALYSIS_VERSION,
                            "destination_id": result_metadata.get("destination_id", DESTINATION_ID),
                            "applied_weights": applied_weights, "group_by": group_by,
                            "max_commute_min": max_commute_min,
                            "min_valid_share": min_valid_share,
                            "min_feasible_share": min_feasible_share})
    return {"point_scores": points, "area_scores": areas,
            "top5": areas.loc[areas["eligible"]].head(k).copy(), "metadata": result_metadata}
