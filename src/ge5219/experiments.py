"""Declared sensitivity experiments and comparisons on comparable populations."""

from collections.abc import Collection
from itertools import combinations
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import kendalltau, spearmanr

from .artifacts import save_result, write_json
from .settings import FEATURES, SCENARIOS


def compare_rankings(left: pd.DataFrame, right: pd.DataFrame, k: int = 5) -> dict[str, Any]:
    """Compare eligible rankings in one unit system; empty overlap is undefined."""
    first = left.dropna(subset=["rank"]).sort_values("rank")
    second = right.dropna(subset=["rank"]).sort_values("rank")
    left_top = set(first.head(k)["unit_id"])
    right_top = set(second.head(k)["unit_id"])
    union = left_top | right_top
    common = first[["unit_id", "rank"]].merge(
        second[["unit_id", "rank"]], on="unit_id", suffixes=("_left", "_right"),
        validate="one_to_one",
    )
    correlations: dict[str, float | None] = {"spearman": None, "kendall": None}
    if len(common) >= 2 and common["rank_left"].nunique() > 1:
        correlations = {
            "spearman": float(np.clip(spearmanr(common.rank_left, common.rank_right).statistic, -1, 1)),
            "kendall": float(kendalltau(common.rank_left, common.rank_right).statistic),
        }
    return {
        "top_k_jaccard": len(left_top & right_top) / len(union) if union else None,
        "n_common": len(common), "n_left": len(first), "n_right": len(second),
        **correlations,
    }


def compare_spatial_selections(
    common: pd.DataFrame, subzone_ids: Collection[str], cluster_ids: Collection[str],
) -> dict[str, Any]:
    """Compare Top-5 spatial footprints using the common B positions, never IDs."""
    subzone_positions = set(common.loc[common.area_id.isin(subzone_ids), "location_id"])
    cluster_positions = set(common.loc[common.cluster_id.isin(cluster_ids), "location_id"])
    union = subzone_positions | cluster_positions
    return {
        "jaccard_positions": len(subzone_positions & cluster_positions) / len(union) if union else None,
        "n_subzone_positions": len(subzone_positions),
        "n_cluster_positions": len(cluster_positions),
        "n_common_positions": len(subzone_positions & cluster_positions),
        "subzone_position_ids": sorted(subzone_positions),
        "cluster_position_ids": sorted(cluster_positions),
        "interpretation": "Different unit sizes change footprint overlap; this alone is not robustness evidence.",
    }


def summarize_selected_units(
    selected: pd.DataFrame, building_membership: pd.DataFrame, group_by: str,
) -> pd.DataFrame:
    """Attach full candidate-record counts and bounding-box extent to selected units.

    Extent is a scale diagnostic, not an estate boundary or exact diameter.
    Counts describe source building/address records, not households or capacity.
    """
    required = {"building_id", group_by, "x_3414", "y_3414"}
    if required - set(building_membership):
        raise ValueError("Full building membership and EPSG:3414 coordinates are required")
    if building_membership.building_id.duplicated().any():
        raise ValueError("Full building membership must have unique building IDs")
    numeric = building_membership[["x_3414", "y_3414"]].to_numpy(dtype=float)
    if not np.isfinite(numeric).all() or building_membership[group_by].isna().any():
        raise ValueError("Building membership needs finite projected coordinates and group IDs")
    summary = building_membership.groupby(group_by, as_index=False).agg(
        n_building_records=("building_id", "size"),
        x_min=("x_3414", "min"), x_max=("x_3414", "max"),
        y_min=("y_3414", "min"), y_max=("y_3414", "max"))
    summary["extent_diagonal_m"] = np.hypot(summary.x_max - summary.x_min,
                                            summary.y_max - summary.y_min)
    return selected.merge(summary.rename(columns={group_by: "unit_id"}), on="unit_id",
                          how="left", validate="one_to_one")


def _save_weight_runs(
    frame: pd.DataFrame, params: dict, weights: np.ndarray, output: Path,
    prefix: str, metadata: dict, labels: list[dict[str, Any]],
) -> pd.DataFrame:
    from .mcda import recommend

    all_ranks = []
    rows_for_weights = []
    for index, vector in enumerate(weights):
        result = recommend(frame, params, vector, metadata=metadata)
        ranks = result["area_scores"].copy()
        ranks["run"] = index
        all_ranks.append(ranks)
        rows_for_weights.append({"run": index, **labels[index],
                                 **dict(zip(FEATURES, vector, strict=True)),
                                 "result_id": result["metadata"]["result_id"]})
    combined = pd.concat(all_ranks, ignore_index=True)
    combined.to_csv(output / f"{prefix}_ranks.csv", index=False)
    pd.DataFrame(rows_for_weights).to_csv(output / f"{prefix}_weights.csv", index=False)
    return combined


def _plot_experiments(
    output: Path, scenarios: dict, frequency: pd.DataFrame,
    oat_ranks: pd.DataFrame, oat_labels: list[dict], frame: pd.DataFrame,
) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figure, axes = plt.subplots(2, 2, figsize=(13, 9), constrained_layout=True)
    for axis, (name, result) in zip(axes.flat, scenarios.items(), strict=True):
        top = result["top5"].sort_values("rank", ascending=False)
        axis.barh(top["unit_name"], top["score"], color="#227a9e")
        axis.set(title=name.replace("_", " "), xlim=(0, 1), xlabel="MCDA score")
    figure.suptitle("A / Subzone — fixed normalization, no commute cap")
    figure.savefig(output / "scenario_top5.png", dpi=160)
    plt.close(figure)
    figure, axis = plt.subplots(figsize=(11, 6), constrained_layout=True)
    top_frequency = frequency.nlargest(20, "selection_frequency").sort_values("selection_frequency")
    axis.barh(top_frequency.unit_id, top_frequency.selection_frequency)
    axis.set(xlim=(0, 1), xlabel="Top-5 frequency under declared Dirichlet weights",
             title="Weight sensitivity (not resident choice probabilities)")
    figure.savefig(output / "monte_carlo_frequency.png", dpi=160)
    plt.close(figure)
    figure, axes = plt.subplots(4, 2, figsize=(13, 15), constrained_layout=True)
    labels = pd.DataFrame(oat_labels).reset_index(names="run")
    joined = oat_ranks.merge(labels, on="run", validate="many_to_one")
    for axis, feature in zip(axes.flat, FEATURES):
        subset = joined[joined.target_feature == feature]
        selected = subset.loc[subset["rank"] <= 5, "unit_id"].unique()[:12]
        for unit_id in selected:
            series = subset[subset.unit_id == unit_id].sort_values("target_weight")
            axis.plot(series.target_weight, series["rank"], label=unit_id)
        axis.set(title=feature, xlabel="Target weight", ylabel="Rank")
        axis.invert_yaxis()
    axes.flat[-1].set_visible(False)
    figure.savefig(output / "oat_ranks.png", dpi=160)
    plt.close(figure)
    figure, axis = plt.subplots(figsize=(9, 8), constrained_layout=True)
    correlation = frame[list(FEATURES)].corr(method="spearman")
    shown = axis.imshow(correlation.to_numpy(), vmin=-1, vmax=1, cmap="coolwarm")
    axis.set_xticks(range(len(FEATURES)), FEATURES, rotation=55, ha="right")
    axis.set_yticks(range(len(FEATURES)), FEATURES)
    figure.colorbar(shown, ax=axis, label="Spearman correlation")
    figure.savefig(output / "indicator_correlation.png", dpi=160)
    plt.close(figure)


def run_experiments(
    frame: pd.DataFrame, params: dict, output_dir: Path,
    building_membership: pd.DataFrame,
    metadata: dict | None = None, draws: int = 1000, seed: int = 42,
    kappa: float = 50.0, make_plots: bool = True,
) -> dict[str, Any]:
    """Run registered v1.0 scenarios, OAT, Monte Carlo and three spatial arms.

    All point rows, including failures, enter area denominators. Weight-only
    experiments use A/Subzone and no cap. Spatial and qualification experiments
    use the predeclared 60-minute cap. Normalization is never refitted here.
    """
    from .mcda import recommend

    if draws < 1000 or not isinstance(draws, int):
        raise ValueError("The approved Monte Carlo experiment requires >=1000 draws")
    if not np.isfinite(kappa) or kappa <= 0:
        raise ValueError("Dirichlet kappa must be positive and finite")
    if "sample_A" not in frame or frame.sample_A.dtype != bool:
        raise ValueError("sample_A must be a boolean frozen sampling flag")
    if not set(frame.building_id).issubset(set(building_membership.building_id)):
        raise ValueError("Full building membership must include all planned building IDs")
    empty_selection = pd.DataFrame({"unit_id": pd.Series(dtype=str)})
    for grouping in ("area_id", "cluster_id"):
        summarize_selected_units(empty_selection, building_membership, grouping)
    baseline = frame.loc[frame.sample_A].copy()
    if baseline.empty:
        raise ValueError("Frozen A baseline is empty")
    output_dir.mkdir(parents=True, exist_ok=True)
    context = dict(metadata or {})
    context["sample_set"] = "A"
    write_json(output_dir / "normalization_params.json", params)
    scenarios = {name: recommend(baseline, params, vector, metadata=context)
                 for name, vector in SCENARIOS.items()}
    for name, result in scenarios.items():
        save_result(result, output_dir / f"scenario_{name}")
    pairwise = [{"left": left, "right": right,
                 **compare_rankings(scenarios[left]["area_scores"],
                                    scenarios[right]["area_scores"])}
                for left, right in combinations(scenarios, 2)]
    pd.DataFrame(pairwise).to_csv(output_dir / "scenario_comparisons.csv", index=False)
    balanced = np.array(SCENARIOS["balanced"])
    rng = np.random.default_rng(seed)
    simulated = rng.dirichlet(kappa * balanced, size=draws)
    monte_carlo = _save_weight_runs(baseline, params, simulated, output_dir,
                                   "monte_carlo", context, [{} for _ in range(draws)])
    frequency = monte_carlo.assign(selected=monte_carlo["rank"].le(5).fillna(False)).groupby(
        "unit_id", as_index=False).agg(selection_frequency=("selected", "mean"),
                                      rank_median=("rank", "median"),
                                      rank_p05=("rank", lambda values: values.quantile(.05)),
                                      rank_p95=("rank", lambda values: values.quantile(.95)))
    frequency.to_csv(output_dir / "monte_carlo_frequency.csv", index=False)
    oat_weights, oat_labels = [], []
    for index, feature in enumerate(FEATURES):
        for target in np.arange(1, 13) / 20:
            vector = balanced * ((1 - target) / (1 - balanced[index]))
            vector[index] = target
            oat_weights.append(vector)
            oat_labels.append({"target_feature": feature, "target_weight": float(target)})
    oat_ranks = _save_weight_runs(baseline, params, np.array(oat_weights), output_dir,
                                 "oat", context, oat_labels)
    switches = []
    for feature_index, feature in enumerate(FEATURES):
        for step in range(11):
            first_run = feature_index * 12 + step
            comparison = compare_rankings(oat_ranks[oat_ranks.run == first_run],
                                          oat_ranks[oat_ranks.run == first_run + 1])
            switches.append({"target_feature": feature,
                             "interval_start": oat_labels[first_run]["target_weight"],
                             "interval_end": oat_labels[first_run + 1]["target_weight"],
                             **comparison})
    pd.DataFrame(switches).to_csv(output_dir / "oat_switch_intervals.csv", index=False)
    arms = {
        "A_subzone": recommend(baseline, params, balanced, max_commute_min=60, metadata=context),
        "B_subzone": recommend(frame, params, balanced, max_commute_min=60,
                               metadata={**context, "sample_set": "B"}),
        "B_cluster": recommend(frame, params, balanced, group_by="cluster_id", max_commute_min=60,
                               metadata={**context, "sample_set": "B"}),
    }
    for name, result in arms.items():
        save_result(result, output_dir / f"spatial_{name}")
        grouping = "cluster_id" if name == "B_cluster" else "area_id"
        support = summarize_selected_units(result["top5"], building_membership, grouping)
        support.to_csv(output_dir / f"spatial_{name}" / "selected_unit_support.csv", index=False)
    spatial = compare_spatial_selections(frame, set(arms["B_subzone"]["top5"].unit_id),
                                         set(arms["B_cluster"]["top5"].unit_id))
    spatial["supplementation_ranking_comparison"] = compare_rankings(
        arms["A_subzone"]["area_scores"], arms["B_subzone"]["area_scores"])
    selected_subzones = set(arms["B_subzone"]["top5"].unit_id)
    selected_clusters = set(arms["B_cluster"]["top5"].unit_id)
    subzone_buildings = set(building_membership.loc[
        building_membership.area_id.isin(selected_subzones), "building_id"])
    cluster_buildings = set(building_membership.loc[
        building_membership.cluster_id.isin(selected_clusters), "building_id"])
    building_union = subzone_buildings | cluster_buildings
    spatial.update({
        "n_subzone_building_records": len(subzone_buildings),
        "n_cluster_building_records": len(cluster_buildings),
        "jaccard_building_records": len(subzone_buildings & cluster_buildings) / len(building_union)
        if building_union else None,
        "building_count_semantics": "Distinct candidate source records, not verified households or capacity",
        "extent_semantics": "Projected bounding-box diagonal, not exact diameter or estate boundary",
    })
    write_json(output_dir / "spatial_comparison.json", spatial)
    qualification = {}
    for threshold in (.25, .5, .75):
        result = recommend(baseline, params, balanced, max_commute_min=60,
                           min_feasible_share=threshold, metadata=context)
        save_result(result, output_dir / f"qualification_{int(threshold * 100)}")
        qualification[str(threshold)] = result
    comparisons = [{"left_threshold": left, "right_threshold": right, "commute_cap_min": 60,
                    **compare_rankings(qualification[left]["area_scores"],
                                       qualification[right]["area_scores"])}
                   for left, right in combinations(qualification, 2)]
    pd.DataFrame(comparisons).to_csv(output_dir / "qualification_comparisons.csv", index=False)
    for cap in (40, 60):
        save_result(recommend(baseline, params, balanced, max_commute_min=cap, metadata=context),
                    output_dir / f"commute_cap_{cap}")
    if make_plots:
        _plot_experiments(output_dir, scenarios, frequency, oat_ranks, oat_labels, baseline)
    manifest = {
        "experiment_version": "v1.0", "draws": draws, "seed": seed, "kappa": kappa,
        "weight_experiment_cap_min": None, "spatial_commute_cap_min": 60,
        "qualification_commute_cap_min": 60, "normalization_refitted": False,
        "spatial_arms": list(arms), "n_A": len(baseline), "n_B": len(frame),
        "scenario_statuses": {name: value["metadata"]["status"] for name, value in scenarios.items()},
        "spatial_statuses": {name: value["metadata"]["status"] for name, value in arms.items()},
        "context": context,
        "route_review": "Not completed by model execution; independent review evidence is required.",
    }
    write_json(output_dir / "experiment_manifest.json", manifest)
    return manifest
