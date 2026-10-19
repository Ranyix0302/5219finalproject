"""Portable bilingual handover of saved MCDA results, without rerunning the model."""

import base64
import html
import io
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd

from .artifacts import read_locations
from .settings import FEATURES, SCENARIOS

LABELS = ("校园通勤", "轨道出口", "公交供给", "超市供给", "图书馆", "医疗供给", "绿地邻近")
ENGLISH_LABELS = ("Campus trip", "Rail exits", "Bus stops", "Supermarkets", "Library", "Clinics", "Park proximity")
COLORS = ("#167d9a", "#528a63", "#c59032", "#bb6c49", "#87669e", "#648ac0", "#63a18d")
STATUS_LABELS = {"ok": "已生成候选排名", "no_feasible_results": "没有符合资格的区域",
                 "data_coverage_insufficient": "测量覆盖不足", "unsupported_destination": "目的地不受支持"}
ARM_LABELS = {"A_subzone": "A → Subzone", "B_subzone": "B → Subzone", "B_cluster": "B → cluster"}
ENGLISH_SOURCE_NOTES = {
    "同一 OneMap API 重查只检验复现、几何和桌面合理性，不是独立数据源或实地真值。":
        "Repeating the same OneMap API checks reproducibility, geometry and desktop plausibility; it does not provide an independent data source or field ground truth.",
    "自动异常标志仅用于引导审阅；没有标志不等于路线已验证。":
        "Automatic anomaly flags guide review. An absence of flags does not mean that a route has been validated.",
    "Google Maps 链接不固定出发时间，外部复核时须手动设置同一日期、08:00 和公共交通。":
        "Google Maps links do not fix the departure time. An external review must manually set the same date, 08:00 and public transport.",
    "AS8 终点为经桌面核查的地面到达代理，非测绘门口；室内行走和电梯不在模型中。":
        "The AS8 endpoint is a desktop-reviewed ground-arrival proxy, not a surveyed entrance. Indoor walking and lifts are outside the model.",
}


def _text(language: str, chinese: str, english: str) -> str:
    return english if language == "en" else chinese


def _indicator_labels(language: str) -> tuple[str, ...]:
    return ENGLISH_LABELS if language == "en" else LABELS


def _source_note(value: Any, language: str) -> str:
    original = str(value)
    if language != "en":
        return original
    translated = ENGLISH_SOURCE_NOTES.get(original, original)
    if re.search(r"[\u3400-\u9fff]", translated):
        raise ValueError("An English translation is required for a reader-facing source note")
    return translated


@dataclass
class _Bundle:
    metadata: dict[str, Any]
    points: pd.DataFrame
    areas: pd.DataFrame
    top: pd.DataFrame


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"Expected a JSON object: {path}")
    return value


def _require_columns(frame: pd.DataFrame, columns: set[str], path: Path) -> None:
    missing = columns - set(frame)
    if missing:
        raise ValueError(f"Missing columns in {path.name}: {sorted(missing)}")


def _read_bundle(path: Path, dataset_version: str) -> _Bundle:
    metadata = _read_json(path / "result_metadata.json")
    result_id = metadata.get("result_id")
    if not isinstance(result_id, str) or not result_id.startswith("mcda-"):
        raise ValueError(f"Missing or invalid result_id: {path}")
    if metadata.get("dataset_version") != dataset_version:
        raise ValueError(f"Result dataset_version differs from prepared data: {path}")
    if metadata.get("status") not in STATUS_LABELS:
        raise ValueError(f"Unknown result status: {path}")
    tables = {}
    common = {"unit_id", "unit_name", "unit_type", "n_planned", "n_valid", "n_feasible",
              "valid_share", "verified_feasible_share", "limited_support", "rank", "score",
              *{f"contribution_{feature}" for feature in FEATURES}}
    for name in ("point_scores", "area_scores", "top5"):
        table_path = path / f"{name}.csv"
        frame = read_locations(table_path)
        required = {"result_id"} | (common if name != "point_scores" else {
            "location_id", "area_id", "cluster_id", "latitude", "longitude", "is_feasible"})
        _require_columns(frame, required, table_path)
        if not frame.result_id.eq(result_id).all():
            raise ValueError(f"Mixed result_id in {table_path}")
        identity = "location_id" if name == "point_scores" else "unit_id"
        if frame[identity].isna().any() or frame[identity].duplicated().any():
            raise ValueError(f"Missing or duplicate identities in {table_path}")
        tables[name] = frame
    if tables["point_scores"].empty or tables["area_scores"].empty:
        raise ValueError(f"Result bundle has no planned positions or areas: {path}")
    top, areas = tables["top5"], tables["area_scores"]
    if len(top) > 5 or not top.unit_id.isin(areas.unit_id).all():
        raise ValueError(f"Top-5 table is inconsistent with saved areas: {path}")
    if not top.empty:
        saved = areas.set_index("unit_id").loc[top.unit_id]
        for column in ("rank", "score"):
            if not np.array_equal(saved[column].to_numpy(), top[column].to_numpy(), equal_nan=True):
                raise ValueError(f"Top-5 {column} differs from saved area table: {path}")
    return _Bundle(metadata, tables["point_scores"], areas, top.sort_values("rank"))


def _check_configuration(bundle: _Bundle, weights: tuple[float, ...], cap: int | None,
                         group_by: str, sample_set: str) -> None:
    metadata = bundle.metadata
    vector = metadata.get("applied_weights", {})
    if set(vector) != set(FEATURES) or not np.allclose(
            [vector[feature] for feature in FEATURES], weights, rtol=0, atol=1e-12):
        raise ValueError("Saved scenario weights differ from the registered report view")
    expected = {"max_commute_min": cap, "group_by": group_by, "sample_set": sample_set,
                "min_valid_share": .9, "min_feasible_share": .5}
    if any(metadata.get(key) != value for key, value in expected.items()):
        raise ValueError("Saved result configuration differs from its report view")


def _validate_runs(directory: Path, prefix: str, minimum_runs: int) -> pd.DataFrame:
    weights_path = directory / f"{prefix}_weights.csv"
    weights = pd.read_csv(weights_path, dtype={"result_id": str})
    _require_columns(weights, {"run", "result_id", *FEATURES}, weights_path)
    if len(weights) < minimum_runs or weights.run.duplicated().any() or weights.result_id.isna().any():
        raise ValueError(f"Incomplete or ambiguous saved {prefix} weight runs")
    ids_for_run = weights.set_index("run").result_id
    seen_runs: set[int] = set()
    for ranks in pd.read_csv(directory / f"{prefix}_ranks.csv", chunksize=50_000,
                             usecols=["run", "result_id", "unit_id", "rank"]):
        expected_ids = ranks.run.map(ids_for_run)
        if expected_ids.isna().any() or not ranks.result_id.eq(expected_ids).all():
            raise ValueError(f"Mixed result_id in saved {prefix} ranking runs")
        seen_runs.update(ranks.run.astype(int))
    if seen_runs != set(weights.run):
        raise ValueError(f"Missing saved {prefix} ranking runs")
    return weights


def _figure_data(figure: Any, output: Path) -> str:
    import matplotlib.pyplot as plt

    buffer = io.BytesIO()
    figure.savefig(buffer, format="png", dpi=135, bbox_inches="tight", facecolor="white")
    output.write_bytes(buffer.getvalue())
    plt.close(figure)
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def _bundle_figures(bundle: _Bundle, subzones: gpd.GeoDataFrame,
                    directory: Path, name: str, language: str = "zh") -> dict[str, str]:
    import matplotlib.pyplot as plt

    figure, axis = plt.subplots(figsize=(10, 4.8), constrained_layout=True)
    top = bundle.top.sort_values("rank", ascending=False)
    if top.empty:
        axis.text(.5, .5, _text(language, "没有符合资格的区域；未补造分数", "No eligible areas; no scores fabricated"), ha="center", va="center", transform=axis.transAxes)
    else:
        previous = np.zeros(len(top))
        for feature, label, color in zip(FEATURES, _indicator_labels(language), COLORS, strict=True):
            values = top[f"contribution_{feature}"].to_numpy(dtype=float)
            axis.barh(top.unit_name, values, left=previous, label=label, color=color)
            previous += values
        axis.legend(ncol=4, loc="upper center", bbox_to_anchor=(.5, -.12), frameon=False)
    axis.set(xlim=(0, 1), xlabel=_text(language, "合格样本的平均贡献；各段之和为保存的 MCDA 分数", "Mean contribution over valid feasible locations; segments sum to the saved MCDA score"))
    contributions = _figure_data(figure, directory / f"{name}-contributions.png")
    figure, axis = plt.subplots(figsize=(10, 6.1), constrained_layout=True)
    subzones.plot(ax=axis, facecolor="#edf2f4", edgecolor="#c7d3da", linewidth=.35)
    grouping = bundle.metadata["group_by"]
    points = gpd.GeoDataFrame(bundle.points, geometry=gpd.points_from_xy(
        bundle.points.longitude, bundle.points.latitude), crs=4326).to_crs(3414)
    colors_for_rank = ("#a74831", "#c87d27", "#247d92", "#6878a2", "#618b56")
    for (_, unit), color in zip(bundle.top.iterrows(), colors_for_rank):
        label = f"{int(unit['rank'])}. {unit.unit_name}"
        selected = points.loc[points[grouping].eq(unit.unit_id)]
        if grouping == "area_id":
            subzones.loc[subzones.area_id.eq(unit.unit_id)].plot(
                ax=axis, facecolor=color, edgecolor="white", alpha=.75, linewidth=.6)
            if not selected.empty:
                axis.scatter(selected.geometry.x, selected.geometry.y, s=7, color=color, label=label)
        elif not selected.empty:
            axis.scatter(selected.geometry.x, selected.geometry.y, s=35, color=color,
                         edgecolors="white", linewidths=.4, label=label)
    if not top.empty:
        axis.legend(loc="upper left", fontsize=8, framealpha=.95)
    axis.set(title=_text(language, "官方 Subzone 边界与入选区的计划样本", "Official Subzones and planned locations in selected areas") if grouping == "area_id"
             else _text(language, "入选分析簇的计划样本位置（不绘制或推断小区边界）", "Planned locations of selected analysis clusters; no estate boundaries inferred"),
             xlabel=_text(language, "SVY21 东坐标 / m", "SVY21 easting / m"), ylabel=_text(language, "SVY21 北坐标 / m", "SVY21 northing / m"))
    return {"contributions": contributions,
            "map": _figure_data(figure, directory / f"{name}-map.png")}


def _sensitivity_figures(figures: Path, names: dict[str, str],
                         frequency: pd.DataFrame, switches: pd.DataFrame,
                         matrix: pd.DataFrame, language: str = "zh") -> dict[str, str]:
    import matplotlib.pyplot as plt

    selected = frequency.nlargest(15, "selection_frequency").sort_values("selection_frequency")
    figure, axis = plt.subplots(figsize=(10, 6), constrained_layout=True)
    axis.barh(selected.unit_id.map(names).fillna(selected.unit_id), selected.selection_frequency,
              color="#237d95")
    axis.set(xlim=(0, 1), xlabel=_text(language, "在已保存的权重扰动运行中进入 Top 5 的频率", "Top-5 frequency across the saved weight perturbation runs"),
             title=_text(language, "均衡权重附近的敏感性；不是居民选择概率", "Sensitivity around balanced weights; not resident choice probabilities"))
    frequency_image = _figure_data(figure, figures / "weight-frequency.png")
    correlation = matrix.loc[matrix.sample_A, list(FEATURES)].corr(method="spearman")
    figure, axis = plt.subplots(figsize=(8, 6.2), constrained_layout=True)
    shown = axis.imshow(correlation.to_numpy(), vmin=-1, vmax=1, cmap="RdBu_r")
    axis.set_xticks(range(7), _indicator_labels(language), rotation=35, ha="right")
    axis.set_yticks(range(7), _indicator_labels(language))
    values_for_correlation = correlation.to_numpy(dtype=float)
    for row in range(7):
        for column in range(7):
            value = values_for_correlation[row, column]
            axis.text(column, row, f"{value:.2f}" if pd.notna(value) else _text(language, "未知", "Unknown"),
                      ha="center", va="center", fontsize=8)
    figure.colorbar(shown, ax=axis, label=_text(language, "原始指标的 Spearman 相关", "Spearman correlation of raw indicators"))
    correlation_image = _figure_data(figure, figures / "indicator-correlation.png")
    figure, axis = plt.subplots(figsize=(10, 4.5), constrained_layout=True)
    for feature, label, color in zip(FEATURES, _indicator_labels(language), COLORS, strict=True):
        subset = switches.loc[switches.target_feature.eq(feature)].sort_values("interval_start")
        axis.plot(subset.interval_end, subset.top_k_jaccard, marker="o", label=label, color=color)
    axis.set(xlim=(.05, .6), ylim=(-.03, 1.03), xlabel=_text(language, "目标权重区间的右端点（步长 0.05）", "Right endpoint of target-weight interval (step 0.05)"),
             ylabel=_text(language, "与上一权重步的 Top-5 Jaccard", "Top-5 Jaccard against previous weight step"), title=_text(language, "OAT：其余权重按原比例缩放", "OAT: remaining weights are proportionally rescaled"))
    axis.legend(ncol=4, loc="upper center", bbox_to_anchor=(.5, -.18), frameon=False)
    return {"frequency": frequency_image, "correlation": correlation_image,
            "oat": _figure_data(figure, figures / "oat-switches.png")}


def _json_records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    return json.loads(frame.to_json(orient="records", force_ascii=False))


def _audit_binding_mismatches(audit: dict[str, Any], metadata: dict[str, Any]) -> list[str]:
    destination = metadata.get("destination")
    destination = destination if isinstance(destination, dict) else {}
    expected = {"source_routes_sha256": metadata.get("source_routes_sha256"),
                "destination_id": metadata.get("destination_id"),
                "destination_lat": destination.get("latitude"),
                "destination_lon": destination.get("longitude"),
                "departure": metadata.get("departure"), "mode": metadata.get("mode", "TRANSIT")}
    mismatches = [key for key, value in expected.items()
                  if value is None or audit.get(key) != value]
    if audit.get("binding_status") != "bound":
        mismatches.append("binding_status")
    for key in ("plan_sha256", "adapter_version"):
        if not isinstance(audit.get(key), str) or not audit[key].strip():
            mismatches.append(key)
    if metadata.get("adapter_version") is not None and audit.get("adapter_version") != metadata["adapter_version"]:
        mismatches.append("adapter_version")
    return sorted(set(mismatches))


def _audit_review_details(audit: dict[str, Any], language: str = "zh") -> str:
    reviewer_names = {"AI_assisted_desktop": _text(language, "AI 辅助桌面审阅", "AI-assisted desktop review"), "human_desktop": _text(language, "人工桌面审阅", "Human desktop review")}
    counts = audit.get("reviewer_type_counts", audit.get("reviewer_types"))
    if isinstance(counts, dict) and counts:
        separator = _text(language, "；", "; ")
        colon = _text(language, "：", ": ")
        reviewers = separator.join(f"{reviewer_names.get(str(key), str(key))}{colon}{value}"
                            for key, value in counts.items())
    else:
        reviewers = _text(language, "审阅者类型未记录，不能推定为人工审阅", "Reviewer type is not recorded; human review cannot be assumed")
    concerns = html.escape(str(audit.get("reviewed_concerns_count", _text(language, "未记录", "Not recorded"))))
    limitations = audit.get("limitations")
    limitations = limitations if isinstance(limitations, list) else []
    listed = "".join(f"<li>{html.escape(_source_note(value, language))}</li>" for value in limitations)
    if language == "en":
        return (f"<br>Review type: {html.escape(reviewers)}. Reviewed cases with concerns or limitations: {concerns}. "
                "Completing a review does not mean that all routes passed without concerns."
                "<br>This is a reproduction and desktop plausibility check using the same OneMap API. "
                "It is not independent-source validation or field commute validation."
                f"<details><summary>Limitations recorded in the audit</summary><ul>{listed}</ul></details>")
    return (f"<br>审阅方式：{html.escape(reviewers)}。带问题/限制的已复核案例：{concerns}。"
            "完成审阅不表示所有路线均已通过或没有疑点。"
            "<br>这是同一 OneMap API 的重现与桌面合理性检查，"
            "不是独立数据源验证，也不是实地通勤验证。"
            f"<details><summary>审计文件中的限制</summary><ul>{listed}</ul></details>")


def _audit_status(score_dir: Path, experiments_dir: Path, metadata: dict[str, Any], language: str = "zh") -> str:
    for directory in (score_dir, experiments_dir):
        path = directory / "route_review.json"
        if path.exists():
            audit = _read_json(path)
            mismatches = _audit_binding_mismatches(audit, metadata)
            if mismatches:
                summary_keys = ("status", "binding_status", "source_routes_sha256", "destination_id",
                                "destination_lat", "destination_lon", "departure", "mode",
                                "adapter_version", "plan_sha256")
                summary = json.dumps({key: audit.get(key, "未记录") for key in summary_keys},
                                     ensure_ascii=False, indent=2)
                if language == "en":
                    summary = json.dumps({key: audit.get(key, "Not recorded") for key in summary_keys}, ensure_ascii=False, indent=2)
                    return ("The route review is not bound to the current snapshot. Missing or mismatched fields: "
                            f"{html.escape(', '.join(mismatches))}. Old audit counts are not counted as current review evidence."
                            "<details><summary>Original audit summary (not counted for the current snapshot)</summary>"
                            f"<pre>{html.escape(summary)}</pre></details>")
                return ("独立路线复核未匹配当前快照；缺失或不匹配字段："
                        f"{html.escape(', '.join(mismatches))}。旧审计计数未作为当前复核成果。"
                        "<details><summary>原审计摘要（未计入当前复核）</summary>"
                        f"<pre>{html.escape(summary)}</pre></details>")
            count = audit.get("reviewed_count", "未记录")
            required = audit.get("required_count", 20)
            if language == "en":
                count = audit.get("reviewed_count", "Not recorded")
                method = html.escape(_source_note(audit.get("method", "Not described"), language))
                status = html.escape(_source_note(audit.get("status", "Not recorded"), language))
                return ("The audit binding matches the current snapshot. "
                        f"Route audit file status: {status}; "
                        f"recorded reviews: {html.escape(str(count))} / {html.escape(str(required))}. "
                        f"Method: {method}. "
                        "These statements report the audit file; successful API responses are not independent route validation."
                        + _audit_review_details(audit, language))
            return ("当前快照绑定已匹配。"
                    f"独立路线审计文件状态：{html.escape(str(audit.get('status', '未记录')))}；"
                    f"记录复核 {html.escape(str(count))} / {html.escape(str(required))} 条。"
                    f"方法：{html.escape(str(audit.get('method', '未说明')))}。"
                    "此处按审计文件转述，不把接口成功响应当作独立路线验证。"
                    + _audit_review_details(audit, language))
    if language == "en":
        return "Route review is incomplete: no route_review.json was supplied. API success and model execution do not establish that at least 20 routes received independent validation."
    return "独立路线复核未完成：未提供 route_review.json；接口成功和模型执行均不等于已完成至少20条独立核验。"


def create_result_report(prepared: Path, score_dir: Path, experiments_dir: Path,
                         output: Path, language: str = "zh") -> Path:
    """Show saved, version-matched result bundles as an offline Chinese or English page.

    This function does not invoke MCDA, refit normalization, change weights or
    infer estate boundaries. Correlations and figures describe saved inputs and
    outputs. Missing artifacts or mixed IDs fail before writing the HTML.
    The optional route_review.json is independent evidence, never inferred from
    successful requests. Its absence is displayed as an outstanding review.
    """
    if language not in {"zh", "en"}:
        raise ValueError("Report language must be 'zh' or 'en'")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "DejaVu Sans"]
    quality = _read_json(prepared / "data_quality.json")
    version = quality.get("dataset_version")
    if not isinstance(version, str) or not version:
        raise ValueError("Prepared data has no dataset_version")
    manifest = _read_json(experiments_dir / "experiment_manifest.json")
    if manifest.get("context", {}).get("dataset_version") != version:
        raise ValueError("Experiment manifest has a different dataset_version")
    if manifest.get("seed") != 42 or manifest.get("kappa") != 50:
        raise ValueError("Saved Monte Carlo settings differ from the registered experiment")
    parameters = _read_json(experiments_dir / "normalization_params.json")
    if set(parameters) != set(FEATURES):
        raise ValueError("Saved normalization parameters must cover all seven indicators")
    primary = _read_bundle(score_dir, version)
    _check_configuration(primary, SCENARIOS["balanced"], None, "area_id", "A")
    for key in ("departure", "destination_id", "source_routes_sha256"):
        if manifest.get("context", {}).get(key) != primary.metadata.get(key):
            raise ValueError(f"Experiment manifest has a different {key}")
    matrix = read_locations(score_dir / "indicator_matrix.csv")
    _require_columns(matrix, {"location_id", "sample_A", *FEATURES}, score_dir / "indicator_matrix.csv")
    planned = read_locations(prepared / "analysis_locations.csv")
    _require_columns(planned, {"location_id", "sample_A"}, prepared / "analysis_locations.csv")
    if matrix.location_id.duplicated().any() or set(matrix.location_id) != set(planned.location_id):
        raise ValueError("Indicator matrix does not match the frozen planned B locations")
    if set(matrix.loc[matrix.sample_A, "location_id"]) != set(planned.loc[planned.sample_A, "location_id"]):
        raise ValueError("Indicator matrix changed the frozen A sampling flag")
    bundles = {}
    for name, weights in SCENARIOS.items():
        bundle = _read_bundle(experiments_dir / f"scenario_{name}", version)
        _check_configuration(bundle, weights, None, "area_id", "A")
        bundles[f"scenario_{name}"] = bundle
    for cap in (40, 60):
        bundle = _read_bundle(experiments_dir / f"commute_cap_{cap}", version)
        _check_configuration(bundle, SCENARIOS["balanced"], cap, "area_id", "A")
        bundles[f"commute_cap_{cap}"] = bundle
    arms: dict[str, Any] = {}
    for name in ARM_LABELS:
        bundle = _read_bundle(experiments_dir / f"spatial_{name}", version)
        _check_configuration(bundle, SCENARIOS["balanced"], 60,
                             "cluster_id" if name == "B_cluster" else "area_id", name[0])
        support_path = experiments_dir / f"spatial_{name}" / "selected_unit_support.csv"
        support = read_locations(support_path)
        _require_columns(support, {"unit_id", "result_id", "n_building_records", "extent_diagonal_m"}, support_path)
        if set(support.unit_id) != set(bundle.top.unit_id) or not support.result_id.eq(bundle.metadata["result_id"]).all():
            raise ValueError(f"Spatial support has different selected units or result_id: {support_path}")
        arms[name] = {"bundle": bundle, "support": support}
    for bundle in [primary, *bundles.values(), *(value["bundle"] for value in arms.values())]:
        expected_points = matrix.loc[matrix.sample_A, "location_id"] if bundle.metadata["sample_set"] == "A" else matrix.location_id
        if set(bundle.points.location_id) != set(expected_points):
            raise ValueError("Saved result does not retain every planned point in its A/B sample set")
        for key in ("departure", "destination_id", "source_routes_sha256"):
            if bundle.metadata.get(key) != primary.metadata.get(key):
                raise ValueError(f"Result bundles have different {key}")
    monte_carlo = _validate_runs(experiments_dir, "monte_carlo", 1000)
    _validate_runs(experiments_dir, "oat", 84)
    frequency = pd.read_csv(experiments_dir / "monte_carlo_frequency.csv", dtype={"unit_id": str})
    _require_columns(frequency, {"unit_id", "selection_frequency", "rank_median", "rank_p05", "rank_p95"}, experiments_dir / "monte_carlo_frequency.csv")
    if not frequency.selection_frequency.between(0, 1).all():
        raise ValueError("Saved Monte Carlo frequencies fall outside [0,1]")
    if set(frequency.unit_id) != set(primary.areas.unit_id):
        raise ValueError("Saved Monte Carlo frequencies use different area IDs")
    switches = pd.read_csv(experiments_dir / "oat_switch_intervals.csv")
    _require_columns(switches, {"target_feature", "interval_start", "interval_end", "top_k_jaccard"}, experiments_dir / "oat_switch_intervals.csv")
    qualification = pd.read_csv(experiments_dir / "qualification_comparisons.csv")
    pairwise = pd.read_csv(experiments_dir / "scenario_comparisons.csv")
    spatial = _read_json(experiments_dir / "spatial_comparison.json")
    subzones = gpd.read_file(prepared / "subzones.geojson").to_crs(3414)
    output.parent.mkdir(parents=True, exist_ok=True)
    figures_dir = output.parent / f"{output.stem}_figures"
    figures_dir.mkdir(exist_ok=True)
    views = {key: {"metadata": bundle.metadata, "top": _json_records(bundle.top),
                    "area_count": len(bundle.areas), "eligible_count": int(bundle.areas['rank'].notna().sum()),
                    **_bundle_figures(bundle, subzones, figures_dir, key, language)}
             for key, bundle in bundles.items()}
    spatial_views = {key: {"label": ARM_LABELS[key], "top": _json_records(value["support"]),
                           "metadata": value["bundle"].metadata,
                           **_bundle_figures(value["bundle"], subzones, figures_dir, key, language)}
                     for key, value in arms.items()}
    names = {str(row.unit_id): str(row.unit_name) for row in primary.areas.itertuples()}
    images = _sensitivity_figures(figures_dir, names, frequency, switches, matrix, language)
    route_status = matrix.route_status.value_counts().to_dict() if "route_status" in matrix else {}
    context = {"primary_result_id": primary.metadata["result_id"], "dataset_version": version,
               "departure": primary.metadata.get("departure"), "destination": primary.metadata.get("destination"),
               "source_routes_sha256": primary.metadata.get("source_routes_sha256"),
               "generated_utc": datetime.now(UTC).isoformat(), "route_status_counts": route_status,
               "n_A": int(matrix.sample_A.sum()), "n_B": len(matrix),
               "normalization_parameters": parameters,
               "draws_saved": len(monte_carlo), "seed": manifest.get("seed"), "kappa": manifest.get("kappa")}
    payload = json.dumps({"views": views, "arms": spatial_views, "context": context,
                          "spatial": spatial, "labels": dict(zip(FEATURES, _indicator_labels(language), strict=True))},
                         ensure_ascii=False, allow_nan=False, default=str).replace("<", "\\u003c")
    document = _render_document(payload, context, quality, images, qualification, pairwise,
                                _audit_status(score_dir, experiments_dir, primary.metadata, language), language)
    output.write_text(document, encoding="utf-8")
    return output


def _render_document(payload: str, context: dict[str, Any], quality: dict[str, Any],
                     images: dict[str, str], qualification: pd.DataFrame,
                     pairwise: pd.DataFrame, audit: str, language: str = "zh") -> str:
    generated = html.escape(str(context["generated_utc"]))
    departure = html.escape(str(context["departure"]))
    version = html.escape(str(context["dataset_version"]))
    blockers = "".join(f"<li>{html.escape(_source_note(value, language))}</li>" for value in quality.get("readiness_blockers", []))
    template = _PAGE if language == "zh" else _PAGE_EN.replace("@@STYLE@@", _PAGE.split("<style>", 1)[1].split("</style>", 1)[0])
    missing = _text(language, "未定义", "Undefined")
    return template.replace("@@PAYLOAD@@", payload).replace("@@GENERATED@@", generated).replace(
        "@@DEPARTURE@@", departure).replace("@@VERSION@@", version).replace("@@AUDIT@@", audit).replace(
        "@@FREQUENCY@@", images["frequency"]).replace("@@CORRELATION@@", images["correlation"]).replace(
        "@@OAT@@", images["oat"]).replace("@@BLOCKERS@@", blockers).replace(
        "@@QUALIFICATION@@", qualification.to_html(index=False, border=0, na_rep=missing, float_format=lambda value: f"{value:.3f}")).replace(
        "@@PAIRWISE@@", pairwise.to_html(index=False, border=0, na_rep=missing, float_format=lambda value: f"{value:.3f}"))


_PAGE = r'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>GE5219 · MCDA 真实结果与交接</title>
<style>
:root{color-scheme:light;--ink:#183244;--muted:#5b6e79;--line:#dce5e9;--teal:#167d9a}*{box-sizing:border-box}body{margin:0;background:#eff3f4;color:var(--ink);font:16px/1.75 'Microsoft YaHei',system-ui,sans-serif}main{max-width:1220px;margin:auto;padding:42px 24px}header{border-left:6px solid #bd704d;padding-left:25px;margin-bottom:28px}.eyebrow{color:var(--teal);letter-spacing:2px;font-weight:700;font-size:13px}h1{font-size:38px;line-height:1.3;margin:10px 0}h2{font-size:25px;margin-top:0}h3{font-size:19px}p{margin:10px 0}.sub,small{color:var(--muted)}section,.panel{background:#fff;border-radius:14px;padding:26px;margin:23px 0;box-shadow:0 4px 18px #122d3b09}.notice{border-left:5px solid #bd704d;background:#fff1e2;padding:19px 23px;border-radius:9px}.notice b{color:#8a4228}.flow,.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}.flow>div,.card{padding:16px;border:1px solid var(--line);border-radius:9px}.card b{font-size:27px;display:block;color:var(--teal)}label{font-weight:700;margin-right:12px}select{font:inherit;padding:9px 13px;border:1px solid #a2b8c2;border-radius:7px;background:white;color:var(--ink);margin-right:22px}img{max-width:100%;height:auto}.two{display:grid;grid-template-columns:1fr 1fr;gap:18px}.three{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}.three .panel{margin:0;padding:15px;min-width:0}.table-wrap{overflow:auto}table{border-collapse:collapse;width:100%;font-size:13px}th,td{padding:10px 8px;border-bottom:1px solid var(--line);text-align:left;white-space:nowrap}th{color:var(--teal);background:#f4f8f9}.tag{color:#9b4d21;font-weight:700}.weights{display:flex;gap:8px;flex-wrap:wrap}.weights span{font-size:13px;background:#edf5f6;padding:5px 10px;border-radius:5px}code,pre{font-size:12px;overflow-wrap:anywhere;white-space:pre-wrap}details{margin-top:14px}summary{cursor:pointer;color:var(--teal)}.result-id{font-size:12px;overflow-wrap:anywhere;color:var(--muted)}.caption{font-size:13px;color:var(--muted)}.empty{padding:24px;background:#f5f7f8}a{color:var(--teal)}footer{font-size:13px;color:var(--muted);margin:26px 0}.switch-note{font-size:13px;color:var(--muted)}@media(max-width:850px){.two,.three{grid-template-columns:1fr}.cards,.flow{grid-template-columns:repeat(2,1fr)}h1{font-size:29px}main{padding:24px 13px}section{padding:20px}select{margin-bottom:10px}}@media(prefers-reduced-motion:no-preference){#result-view{animation:appear .18s ease-out}@keyframes appear{from{opacity:.7}to{opacity:1}}}@media print{body{background:white}section,.panel{box-shadow:none;break-inside:avoid}select{display:none}}
</style></head><body><main><header><div class="eyebrow">GE5219 / XIE BINGSHENG / SAVED RESULTS</div><h1>这些地方，为什么进入 Top 5？</h1><p class="sub">实际保存的 GIS–MCDA 结果 · NUS AS8 · @@DEPARTURE@@</p></header>
<div class="notice"><b>研究候选建议；数据核验仍有限。</b>住宅用途依据来源分类，公园类别与开放状态、剩余轨道出口及公交运营尚未全部核验。欧氏距离和缓冲供给不是实际步行可达性；采样位置的测量不能冒充每栋楼均已测量。AS8 是经桌面资料和路由连通性核准的地面到达代理点，不是实地验证的精确入口。</div>
<section><h2>先看规则，再看排名</h2><div class="flow"><div><b>1 · 实际住宅样本</b><br>A 为400 m基线，B 补齐漏簇；均为真实来源中的住宅点。</div><div><b>2 · 七维统一评分</b><br>A 的 P5/P95 固定，距离/时间成本反向，权重按已登记情景应用。</div><div><b>3 · 资格审查</b><br>有效测量 ≥90%，已验证可行/计划样本 ≥50%；失败不补零。</div><div><b>4 · 合格样本均分</b><br>Top 5 为不同 Subzones；cluster 单独作为空间对照。</div></div><p class="caption">这些阈值、权重和150 m连接规则是预先声明的工作假设，未被本地行为数据校准。敏感性检验说明排名如何变化，不能证明指标概念本身合理。</p></section>
<section id="results"><h2>01 · 已保存的推荐结果</h2><label for="scenario">偏好情景</label><select id="scenario"><option value="balanced">均衡</option><option value="campus_first">校园优先</option><option value="transit_first">交通优先</option><option value="lifestyle">生活优先</option></select><label for="cap">通勤上限</label><select id="cap"><option value="none">默认无上限</option><option value="40">40 min</option><option value="60">60 min</option></select><p class="switch-note" id="switch-note">40/60 min 试验只登记了均衡情景；选择上限将切回均衡。页面展示保存的结果，不现场重算。</p><div id="result-view"></div></section>
<section><h2>02 · 换分组，会推荐到相同地方吗？</h2><p>三臂均固定均衡权重、60 min 通勤上限及 A 标准化参数。A→B 检查补点影响；B→Subzone 与 B→cluster 检查相同位置改变分组后的影响。</p><div class="three" id="spatial-arms"></div><div id="spatial-summary" class="notice"></div><p class="caption">Subzone 用官方边界；cluster 地图只显示计划样本位置，不推断真实小区边界。150 m 可以链式连接为数公里的大簇。建筑数指不同来源住宅记录，不是住户数；跨度为投影包围盒对角线，不是精确最大距离。</p></section>
<section><h2>03 · 权重改变后，哪些区域经常入选？</h2><div id="experiment-note"></div><img alt="已保存权重扰动下的Top5选择频率" src="@@FREQUENCY@@"><p>这个频率只描述指定 Dirichlet 权重分布中的模型结果，<b>不是居民选择概率</b>，也不是对推荐真实性的置信度。</p><img alt="单因素权重逐步改变时的Top5切换" src="@@OAT@@"><p class="caption">OAT 每次只改一个目标权重，其余按比例缩放。相邻步的 Jaccard 为1表示这一步 Top 5 集合未变；空集合比较保持未定义。切换发生在区间内，不能称已找到精确临界点。</p><details><summary>查看四情景两两排名比较（保存表）</summary><div class="table-wrap">@@PAIRWISE@@</div><p class="caption">Spearman/Kendall 仅在两组共同有资格的候选上计算；n_common 表示共同候选数。空值表示未定义。</p></details><details><summary>查看25% / 50% / 75%资格门槛对照（固定60 min）</summary><div class="table-wrap">@@QUALIFICATION@@</div><p class="caption">资格规则实验与权重实验回答不同问题；没有变化也按原结果报告。</p></details></section>
<section><h2>04 · 指标会不会重复计量？</h2><div class="two"><div><p>这里使用保存的 A 原始指标计算 Spearman 相关，缺失值按成对观测处理。强相关提示可能测量相近的城市条件，需要回看服务功能与权重分配。</p><p>距离成本与供给收益的符号方向不同；负相关也可能意味着两项同时奖励相似位置。相关性不能自动决定删哪一项，标准化也不能修正概念不合理的指标。</p><p class="caption">公交是800 m内站点数，不是线路数、班次或运力；超市与医疗按服务地址单元计数；公园是几何邻近，不是入口或网络距离。</p></div><img alt="A原始七项指标Spearman相关矩阵" src="@@CORRELATION@@"></div></section>
<section><h2>05 · 验证与证据边界</h2><div class="notice">@@AUDIT@@</div><p>通勤采用 OneMap 首条 itinerary 的 duration。它反映所返回行程的持续时间；尚不能保证涵盖从请求时刻到该行程出发前的额外等待，也不能替代实际通勤观测。</p><details><summary>空间准备时记录的待复核项（原样保留，状态可能需结合后续证据）</summary><ul>@@BLOCKERS@@</ul></details></section>
<section><h2>06 · 下游地图与 Agent 怎样接入？</h2><p>下游按同一 <code>result_id</code> 读取一个 bundle，不从不同情景拼表。Top 5 次序沿用保存的 rank；显示分数可四舍五入，不能据显示分数重新排名。</p><div class="table-wrap"><table><thead><tr><th>文件</th><th>用途</th><th>关键约束</th></tr></thead><tbody><tr><td>result_metadata.json</td><td>状态、权重、上限、版本与目的地</td><td>先读 status 与 result_id，再读取表</td></tr><tr><td>point_scores.csv</td><td>位置、原始/标准分、可行性和贡献</td><td>保留失败与未知；不能补成零</td></tr><tr><td>area_scores.csv</td><td>所有分区及资格/样本支持</td><td>n_valid / n_planned 与 n_feasible / n_planned 分别显示</td></tr><tr><td>top5.csv</td><td>已排序的入选结果</td><td>不足5个按实际数量展示；空结果不补造</td></tr><tr><td>indicator_matrix.csv</td><td>共享的原始输入快照</td><td>按 location_id 连接；不把 B 宣称为 A</td></tr><tr><td>selected_unit_support.csv</td><td>空间臂的建筑记录数和跨度</td><td>不当作住户数或真实小区边界</td></tr></tbody></table></div><p>推荐解释应引用具体贡献与实际样本支持；遇到低样本、缺失和类别不确定性，直接解释证据限制。新增目的地、指标或标准化版本需要重新生成 bundle。</p><details><summary>追溯信息与本页读取的结果 ID</summary><pre id="provenance"></pre></details></section>
<footer>生成时间 UTC：@@GENERATED@@<br>数据版本：<code>@@VERSION@@</code><br>本页是结果交接与解释工具，未代写正式课程报告；图表均来自保存的实际输入与结果，未混入演示评分。所有图片已内嵌，可离线分享。</footer>
</main><script type="application/json" id="report-data">@@PAYLOAD@@</script><script>
'use strict';
const data=JSON.parse(document.getElementById('report-data').textContent);
const esc=value=>String(value??'未记录').replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const num=(value,digits=3)=>value===null||value===undefined?'未知':Number(value).toFixed(digits);
const pct=value=>value===null||value===undefined?'未知':`${(100*Number(value)).toFixed(1)}%`;
const bool=value=>value===true||String(value).toLowerCase()==='true';
const statuses={ok:'已生成候选排名',no_feasible_results:'没有符合资格的区域',data_coverage_insufficient:'测量覆盖不足',unsupported_destination:'目的地不受支持'};
function table(rows,spatial=false){if(!rows.length)return '<p class="empty">没有符合资格的区域；结果按实际情况保留。</p>';return `<div class="table-wrap"><table><thead><tr><th>名次 / 区域</th><th>分数</th><th>计划 / 有效 / 可行</th><th>有效覆盖</th><th>可行 / 计划</th><th>样本支持</th>${spatial?'<th>建筑记录 / 跨度</th>':''}</tr></thead><tbody>${rows.map(row=>`<tr><td>${esc(row.rank)} · ${esc(row.unit_name)}</td><td>${num(row.score)}</td><td>${esc(row.n_planned)} / ${esc(row.n_valid)} / ${esc(row.n_feasible)}</td><td>${pct(row.valid_share)}</td><td>${pct(row.verified_feasible_share)}</td><td>${bool(row.limited_support)?'<span class="tag">有限：有效样本少于3</span>':'显示实际样本量'}</td>${spatial?`<td>${esc(row.n_building_records)} / ${num(row.extent_diagonal_m,0)} m</td>`:''}</tr>`).join('')}</tbody></table></div>`;}
function render(){const scenario=document.getElementById('scenario').value;const cap=document.getElementById('cap').value;const key=cap==='none'?`scenario_${scenario}`:`commute_cap_${cap}`;const view=data.views[key];const m=view.metadata;document.getElementById('result-view').innerHTML=`<p><b>${esc(statuses[m.status])}</b> · 样本 ${esc(m.sample_set)} · ${view.eligible_count} / ${view.area_count} 个分区符合资格</p><div class="weights">${Object.entries(m.applied_weights).map(([key,value])=>`<span>${esc(data.labels[key])} ${pct(value)}</span>`).join('')}</div>${table(view.top)}<p class="caption">分区总分与各项贡献均为符合通勤约束的有效样本均值。有效覆盖门槛 ${pct(m.min_valid_share)}；已验证可行/计划样本门槛 ${pct(m.min_feasible_share)}。</p><img src="${view.contributions}" alt="所选结果的七项平均贡献"><img src="${view.map}" alt="所选Top5官方分区及样本地图"><p class="result-id">result_id：${esc(m.result_id)}</p>`;}
document.getElementById('scenario').addEventListener('change',()=>{document.getElementById('cap').value='none';render();});document.getElementById('cap').addEventListener('change',()=>{if(document.getElementById('cap').value!=='none')document.getElementById('scenario').value='balanced';render();});render();
document.getElementById('spatial-arms').innerHTML=Object.values(data.arms).map(view=>`<div class="panel"><h3>${esc(view.label)}</h3><p>${esc(statuses[view.metadata.status])}</p>${table(view.top,true)}<img src="${view.map}" alt="${esc(view.label)}空间位置"><details><summary>查看分项贡献</summary><img src="${view.contributions}" alt="空间臂平均贡献"></details><p class="result-id">${esc(view.metadata.result_id)}</p></div>`).join('');
const s=data.spatial;const addition=s.supplementation_ranking_comparison||{};document.getElementById('spatial-summary').innerHTML=`<b>补点影响：</b>A/B Subzone 的 Top-5 Jaccard = ${num(addition.top_k_jaccard)}，共同候选 ${esc(addition.n_common)} 个。<br><b>分组影响：</b>共同 B 位置集合 Jaccard = ${num(s.jaccard_positions)}；Subzone 推荐覆盖 ${esc(s.n_subzone_positions)} 个计划位置，cluster 推荐覆盖 ${esc(s.n_cluster_positions)} 个。建筑来源记录覆盖分别为 ${esc(s.n_subzone_building_records)} / ${esc(s.n_cluster_building_records)}。<br>这两种单位大小不同，重叠较低不能单独证明不稳健或某个分组更好。`;
document.getElementById('experiment-note').textContent=`保存 ${data.context.draws_saved} 次扰动，seed=${data.context.seed}，κ=${data.context.kappa}；A/Subzone，无通勤上限。每次权重与排名均可追溯。`;
document.getElementById('provenance').textContent=JSON.stringify({...data.context,result_ids:Object.fromEntries(Object.entries(data.views).map(([key,value])=>[key,value.metadata.result_id])),spatial_result_ids:Object.fromEntries(Object.entries(data.arms).map(([key,value])=>[key,value.metadata.result_id]))},null,2);
</script></body></html>'''


_PAGE_EN = r'''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>GE5219 · Actual MCDA results and handover</title>
<style>@@STYLE@@</style></head><body><main><header><div class="eyebrow">GE5219 / XIE BINGSHENG / SAVED RESULTS</div><h1>Why do these areas enter the Top 5?</h1><p class="sub">Actual saved GIS–MCDA results · NUS AS8 · @@DEPARTURE@@</p></header>
<div class="notice"><b>Research candidate recommendations; verification remains limited.</b> Residential use follows source classifications. Park categories and public opening, retained rail exits and bus-stop operation have not all been verified. Euclidean proximity and buffer supply are not actual walking accessibility. Measurements at sampled locations do not mean that every residential record was measured. AS8 is a desktop-reviewed, route-connected ground-arrival proxy, not a field-verified exact entrance.</div>
<section><h2>Read the rules before the ranking</h2><div class="flow"><div><b>1 · Real residential samples</b><br>A uses the 400 m baseline. B adds locations for uncovered analysis clusters. Both select residential points from actual source records.</div><div><b>2 · Seven comparable scores</b><br>Reuse A's P5/P95 limits. Reverse distance/time costs and apply the registered scenario weights.</div><div><b>3 · Eligibility</b><br>Valid coverage ≥90%; verified feasible/planned locations ≥50%. Failed measurements are not filled with zero.</div><div><b>4 · Mean over feasible locations</b><br>The formal Top 5 contains distinct Subzones. Analysis clusters form a separate spatial comparison.</div></div><p class="caption">These thresholds, weights and the 150 m connection rule are declared working assumptions, not parameters calibrated from local travel behavior. Sensitivity analysis shows ranking changes; it does not establish conceptual validity.</p></section>
<section id="results"><h2>01 · Saved recommendation results</h2><label for="scenario">Preference scenario</label><select id="scenario"><option value="balanced">Balanced</option><option value="campus_first">Campus first</option><option value="transit_first">Transit first</option><option value="lifestyle">Lifestyle</option></select><label for="cap">Commute cap</label><select id="cap"><option value="none">No cap (default)</option><option value="40">40 min</option><option value="60">60 min</option></select><p class="switch-note" id="switch-note">The saved 40/60-minute tests use balanced weights only. Selecting a cap returns to Balanced; selecting a preference clears the cap. This page reads saved results and does not recalculate scores.</p><div id="result-view"></div></section>
<section><h2>02 · Does changing the grouping recommend the same places?</h2><p>All three arms hold balanced weights, a 60-minute commute cap and A normalization fixed. A→B tests supplementation; B→Subzone versus B→cluster tests aggregation of the same locations.</p><div class="three" id="spatial-arms"></div><div id="spatial-summary" class="notice"></div><p class="caption">Subzones use official boundaries. Cluster maps show planned sample locations and do not infer actual estate boundaries. The 150 m rule can form chains spanning several kilometres. Building counts refer to distinct candidate source records, not households. Extent is the projected bounding-box diagonal, not an exact diameter.</p></section>
<section><h2>03 · Which areas remain selected when weights change?</h2><div id="experiment-note"></div><img alt="Top-5 selection frequency in saved weight perturbation runs" src="@@FREQUENCY@@"><p>This frequency describes model outputs under the declared Dirichlet weight distribution. It is <b>not a resident choice probability</b> or a confidence level that a recommendation is correct.</p><img alt="Top-5 changes between adjacent one-at-a-time weight steps" src="@@OAT@@"><p class="caption">OAT changes one target weight and rescales the others proportionally. Adjacent-step Jaccard=1 means that the Top-5 set did not change at that step. Empty-set comparisons remain undefined. A switch lies within a tested interval; the exact critical weight has not been identified.</p><details><summary>Pairwise ranking comparisons of the four saved preference scenarios</summary><div class="table-wrap">@@PAIRWISE@@</div><p class="caption">Spearman/Kendall use candidates eligible in both runs. n_common is their count. Missing values mean undefined. Field names and scenario IDs retain their original machine-readable spelling.</p></details><details><summary>25% / 50% / 75% eligibility-rule comparisons (fixed 60-minute cap)</summary><div class="table-wrap">@@QUALIFICATION@@</div><p class="caption">Eligibility-rule tests and weight tests answer different questions. Unchanged outputs are reported as saved. left_threshold/right_threshold are the compared minimum verified-feasible shares; n_left/n_right count eligible areas in each run; top_k_jaccard compares their Top-5 sets.</p></details></section>
<section><h2>04 · Could indicators count similar conditions twice?</h2><div class="two"><div><p>This matrix calculates Spearman correlation from saved A raw indicators, using available pairs for missing measurements. Strong correlation can indicate that indicators describe similar urban conditions. Review their service functions and weight allocation.</p><p>Raw distance costs and supply benefits have different directions. Negative correlation can also mean that two indicators reward similar locations. Correlation alone cannot identify which indicator to remove. Normalization cannot repair an indicator that measures the wrong concept.</p><p class="caption">Bus supply is the number of stop points within 800 m, not routes, frequency or capacity. Supermarkets and clinics count service-address units. Parks measure geometric proximity, not entrance or network access.</p></div><img alt="Spearman correlation of the seven raw A indicators" src="@@CORRELATION@@"></div></section>
<section><h2>05 · Validation and limits of the evidence</h2><div class="notice">@@AUDIT@@</div><p>Commute time uses the duration of OneMap's first itinerary. It describes the returned itinerary and can include a walking-only journey. It may omit waiting from the requested departure time until that itinerary starts. The returned walkLimit flag does not certify that every walking leg satisfies the requested limit. These values do not replace observed commutes.</p><details><summary>Review items recorded during spatial preparation (source statements; later evidence may affect status)</summary><ul>@@BLOCKERS@@</ul></details></section>
<section><h2>06 · How should maps and an Agent use these results?</h2><p>Read one complete bundle with a common <code>result_id</code>. Do not combine tables from different scenarios. Preserve saved Top-5 rank order. Displayed scores can be rounded, but rounded display values must not be used to rank again.</p><div class="table-wrap"><table><thead><tr><th>File</th><th>Purpose</th><th>Required handling</th></tr></thead><tbody><tr><td>result_metadata.json</td><td>Status, weights, caps, versions and destination</td><td>Read status and result_id before the tables</td></tr><tr><td>point_scores.csv</td><td>Locations, raw/normalized values, feasibility and contributions</td><td>Retain failures and unknown values; do not fill with zero</td></tr><tr><td>area_scores.csv</td><td>All areas, eligibility and sample support</td><td>Show n_valid/n_planned separately from n_feasible/n_planned</td></tr><tr><td>top5.csv</td><td>Saved ranked selections</td><td>Show fewer than five when appropriate; do not fabricate empty results</td></tr><tr><td>indicator_matrix.csv</td><td>Shared raw-input snapshot</td><td>Join by location_id; do not describe B as A</td></tr><tr><td>selected_unit_support.csv</td><td>Spatial-arm candidate-record counts and extent</td><td>Do not call them household counts or verified estate boundaries</td></tr></tbody></table></div><p>Explain recommendations with their saved contributions and actual sample support. State sparse support, missing measurements and classification uncertainty directly. A new destination, indicator definition or normalization version requires a new bundle.</p><details><summary>Provenance and result IDs read by this page</summary><p class="caption">Raw metadata keys and source strings below are preserved. primary_result_id identifies the baseline bundle; dataset_version identifies the prepared data; departure is the routing scene; source_routes_sha256 binds the route snapshot; n_A/n_B count analysis locations; p05/p95 are fixed normalization limits; result_ids and spatial_result_ids bind each displayed view. generated_utc is this page's generation time, not a new routing time.</p><pre id="provenance"></pre></details></section>
<footer>Generated UTC: @@GENERATED@@<br>Dataset version: <code>@@VERSION@@</code><br>This page explains and hands over saved results. It is not the formal course report. Figures use actual saved inputs and outputs, with no demonstration scores mixed in. All images are embedded for offline sharing.</footer>
</main><script type="application/json" id="report-data">@@PAYLOAD@@</script><script>
'use strict';
const data=JSON.parse(document.getElementById('report-data').textContent);
const esc=value=>String(value??'Not recorded').replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const num=(value,digits=3)=>value===null||value===undefined?'Unknown':Number(value).toFixed(digits);
const pct=value=>value===null||value===undefined?'Unknown':`${(100*Number(value)).toFixed(1)}%`;
const bool=value=>value===true||String(value).toLowerCase()==='true';
const statuses={ok:'Candidate ranking generated',no_feasible_results:'No eligible areas',data_coverage_insufficient:'Insufficient measurement coverage',unsupported_destination:'Unsupported destination'};
function table(rows,spatial=false){if(!rows.length)return '<p class="empty">No eligible areas; the actual empty result is retained.</p>';return `<div class="table-wrap"><table><thead><tr><th>Rank / area</th><th>Score</th><th>Planned / valid / feasible</th><th>Valid coverage</th><th>Feasible / planned</th><th>Sample support</th>${spatial?'<th>Candidate records / extent</th>':''}</tr></thead><tbody>${rows.map(row=>`<tr><td>${esc(row.rank)} · ${esc(row.unit_name)}</td><td>${num(row.score)}</td><td>${esc(row.n_planned)} / ${esc(row.n_valid)} / ${esc(row.n_feasible)}</td><td>${pct(row.valid_share)}</td><td>${pct(row.verified_feasible_share)}</td><td>${bool(row.limited_support)?'<span class="tag">Limited: fewer than 3 valid locations</span>':'See actual sample counts'}</td>${spatial?`<td>${esc(row.n_building_records)} / ${num(row.extent_diagonal_m,0)} m</td>`:''}</tr>`).join('')}</tbody></table></div>`;}
function render(){const scenario=document.getElementById('scenario').value;const cap=document.getElementById('cap').value;const key=cap==='none'?`scenario_${scenario}`:`commute_cap_${cap}`;const view=data.views[key];const m=view.metadata;document.getElementById('result-view').innerHTML=`<p><b>${esc(statuses[m.status])}</b> · Sample ${esc(m.sample_set)} · ${view.eligible_count} / ${view.area_count} eligible Subzones</p><div class="weights">${Object.entries(m.applied_weights).map(([key,value])=>`<span>${esc(data.labels[key])} ${pct(value)}</span>`).join('')}</div>${table(view.top)}<p class="caption">Area scores and contributions average valid locations that satisfy the commute constraint. Valid coverage threshold: ${pct(m.min_valid_share)}; verified feasible/planned threshold: ${pct(m.min_feasible_share)}.</p><img src="${view.contributions}" alt="Seven mean contributions for the selected saved result"><img src="${view.map}" alt="Selected Top-5 official Subzones and planned locations"><p class="result-id">result_id: ${esc(m.result_id)}</p>`;}
document.getElementById('scenario').addEventListener('change',()=>{document.getElementById('cap').value='none';render();});document.getElementById('cap').addEventListener('change',()=>{if(document.getElementById('cap').value!=='none')document.getElementById('scenario').value='balanced';render();});render();
document.getElementById('spatial-arms').innerHTML=Object.values(data.arms).map(view=>`<div class="panel"><h3>${esc(view.label)}</h3><p>${esc(statuses[view.metadata.status])}</p>${table(view.top,true)}<img src="${view.map}" alt="${esc(view.label)} spatial locations"><details><summary>Show indicator contributions</summary><img src="${view.contributions}" alt="Mean contributions for this spatial arm"></details><p class="result-id">${esc(view.metadata.result_id)}</p></div>`).join('');
const s=data.spatial;const addition=s.supplementation_ranking_comparison||{};document.getElementById('spatial-summary').innerHTML=`<b>Supplementation:</b> A/B Subzone Top-5 Jaccard = ${num(addition.top_k_jaccard)}, with ${esc(addition.n_common)} common eligible candidates.<br><b>Aggregation:</b> Jaccard on common B locations = ${num(s.jaccard_positions)}; selected Subzones contain ${esc(s.n_subzone_positions)} planned locations and selected clusters contain ${esc(s.n_cluster_positions)}. Full candidate source-record counts are ${esc(s.n_subzone_building_records)} / ${esc(s.n_cluster_building_records)}.<br>The units differ in size. Lower overlap alone does not establish poor robustness or identify a better grouping.`;
document.getElementById('experiment-note').textContent=`${data.context.draws_saved} saved weight draws, seed=${data.context.seed}, κ=${data.context.kappa}; A/Subzone, no commute cap. Every weight vector and ranking can be traced.`;
document.getElementById('provenance').textContent=JSON.stringify({...data.context,result_ids:Object.fromEntries(Object.entries(data.views).map(([key,value])=>[key,value.metadata.result_id])),spatial_result_ids:Object.fromEntries(Object.entries(data.arms).map(([key,value])=>[key,value.metadata.result_id]))},null,2);
</script></body></html>'''
