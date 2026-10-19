"""Build annotated, offline SVG figures from the frozen handover tables."""

from __future__ import annotations

import html
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

FEATURES = (
    "campus_transit_min",
    "rail_exit_euclid_m",
    "bus_stops_800m",
    "supermarket_sites_800m",
    "library_euclid_m",
    "clinic_sites_1000m",
    "park_proximity_euclid_m",
)
COLORS = ("#166b91", "#e88631", "#359770", "#ba5a88", "#7758a6", "#a47b1f", "#4c8996")
LINE_COLORS = (*COLORS, "#a63935", "#323e57", "#645746")
LABELS = {
    "zh": ("校园通勤", "轨道出入口", "公交站数", "超市供给", "图书馆", "医疗供给", "公园邻近性"),
    "en": (
        "Campus trip",
        "Rail exits",
        "Bus stops",
        "Supermarkets",
        "Library",
        "Clinics",
        "Park proximity",
    ),
}
VISUAL_KEYS = (
    "measurement",
    "normalization",
    "contribution",
    "eligibility",
    "correlation",
    "scenarios",
    "monte_carlo",
    "oat",
    "spatial",
    "caps",
    "qualification",
)


def escape(value: object) -> str:
    return html.escape(str(value))


def text(
    x: float, y: float, value: object, size: int = 16, anchor: str = "start", color: str = "#183343"
) -> str:
    return f'<text x="{x:.2f}" y="{y:.2f}" font-size="{size}" text-anchor="{anchor}" fill="{color}">{escape(value)}</text>'


def line(
    x1: float, y1: float, x2: float, y2: float, color: str = "#b9ced5", dash: bool = False
) -> str:
    return (
        f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" stroke="{color}" stroke-width="1.5"'
        + (' stroke-dasharray="6 5"' if dash else "")
        + "/>"
    )


def rect(x: float, y: float, width: float, height: float, fill: str, radius: int = 0) -> str:
    return f'<rect x="{x:.2f}" y="{y:.2f}" width="{width:.2f}" height="{height:.2f}" rx="{radius}" fill="{fill}"/>'


def path(
    points: list[tuple[float, float]], color: str, width: float = 3, dash: bool = False
) -> str:
    coordinates = " ".join(f"{x:.2f},{y:.2f}" for x, y in points)
    return (
        f'<polyline points="{coordinates}" fill="none" stroke="{color}" stroke-width="{width}"'
        + (' stroke-dasharray="8 5"' if dash else "")
        + "/>"
    )


def svg(content: str, height: int, title: str) -> str:
    return f'<svg class="method-svg" role="img" aria-label="{escape(title)}" viewBox="0 0 960 {height}" font-family="Arial, Microsoft YaHei, sans-serif" xmlns="http://www.w3.org/2000/svg"><title>{escape(title)}</title>{rect(0, 0, 960, height, "#ffffff")}{content}</svg>'


def legend(items: list[tuple[str, str]]) -> str:
    return (
        '<ul class="figure-legend">'
        + "".join(
            f'<li><span style="background:{color}" class="legend-chip"></span>{escape(label)}</li>'
            for color, label in items
        )
        + "</ul>"
    )


def card(
    key: str,
    title: str,
    plot: str,
    legend_html: str,
    reading: str,
    source: str,
    language: str,
    teaching: bool = False,
) -> str:
    tag = (
        ("教学示意" if teaching else "冻结数据实算")
        if language == "zh"
        else ("Teaching example" if teaching else "Frozen computed results")
    )
    return f'<figure class="method-figure" id="visual-{key}" data-visual="{key}" data-language="{language}"><figcaption><span class="figure-tag">{tag}</span><h3>{escape(title)}</h3></figcaption>{plot}{legend_html}<div class="figure-reading"><b>{"怎样读" if language == "zh" else "How to read"}</b><p>{reading}</p></div><p class="figure-source">{"来源与固定条件" if language == "zh" else "Source and fixed conditions"}: {escape(source)}</p></figure>'


def feature_legend(language: str) -> str:
    return legend(list(zip(COLORS, LABELS[language], strict=True)))


def measurement(language: str) -> str:
    zh = language == "zh"
    content = text(
        80,
        33,
        "800 m 硬边界 vs 距离衰减（仅示意）"
        if zh
        else "800 m hard boundary vs distance decay (teaching only)",
        21,
    )
    for y, label in [(1.0, "1.0"), (0.5, "0.5"), (0, "0")]:
        py = 250 - 170 * y
        content += line(85, py, 880, py) + text(67, py + 5, label, 14, "end")
    for d in [0, 400, 800, 1200, 1600]:
        x = 85 + d / 1600 * 795
        content += text(x, 277, d, 14, "middle")
    content += path([(85, 80), (482.5, 80), (482.5, 250), (880, 250)], COLORS[0], 4)
    content += path(
        [(85 + d / 1600 * 795, 250 - 170 * math.exp(-d / 800)) for d in range(0, 1601, 20)],
        COLORS[1],
        4,
        True,
    )
    content += line(482.5, 63, 482.5, 250, "#5c7481", True) + text(
        482.5, 56, "r = 800 m", 15, "middle"
    )
    content += text(
        480,
        310,
        "与住宅的欧氏距离 d（m）" if zh else "Euclidean distance from the home d (m)",
        17,
        "middle",
    )
    content += text(90, 61, "单个设施的计分份额" if zh else "Contribution of one facility", 15)
    return card(
        "measurement",
        "距离、缓冲计数与衰减不是同一种指标"
        if zh
        else "Distance, buffer counts and decay measure different things",
        svg(content, 330, "Buffer versus decay"),
        legend(
            [
                (
                    COLORS[0],
                    "当前计数：d≤800 m 计 1；超出计 0"
                    if zh
                    else "Current count: 1 for d≤800 m; otherwise 0",
                ),
                (COLORS[1], "未实施示意：exp(−d/800)" if zh else "Not implemented: exp(−d/800)"),
            ]
        ),
        "实线表示一个站点或超市是否被数入。虚线只解释距离衰减：越远，份额越小。图中的 800 m 衰减尺度是教学假设，不是文献核准参数，也没有生成本次分数。当前医疗计数用 1,000 m。校园用 OneMap 分钟，轨道／图书馆用最近欧氏距离，公园用多边形邻近性；不是七项全用 buffer。"
        if zh
        else "The solid line shows whether one stop or supermarket is counted. The dashed line explains decay: a more distant facility contributes less. The 800 m decay scale is a teaching assumption. It is not a justified fitted parameter and was not used in the results. Clinics use a 1,000 m count. Campus uses OneMap minutes; rail/library use nearest Euclidean distance; parks use polygon proximity. The seven indicators do not all use buffers.",
        "config/indicator_dictionary.json; illustrative decay = exp(−d/800), not implemented",
        language,
        True,
    )


def normalization(root: Path, language: str) -> str:
    zh = language == "zh"
    params = json.loads((root / "outputs/normalization-v1.json").read_text())["parameters"]
    p = params["bus_stops_800m"]
    q = params["campus_transit_min"]
    content = ""
    for left, label, p5, p95, maximum, reverse in [
        (60, "公交站数（效益项）" if zh else "Bus stops (benefit)", p["p05"], p["p95"], 65, False),
        (
            530,
            "校园通勤分钟（成本项）" if zh else "Campus minutes (cost)",
            q["p05"],
            q["p95"],
            110,
            True,
        ),
    ]:
        x = lambda value, left=left, maximum=maximum: left + 360 * value / maximum
        y = lambda value: 230 - 150 * value
        content += text(left, 30, label, 19)
        content += rect(x(0), 70, x(p5) - left, 160, "#eaf1f4") + rect(
            x(p95), 70, x(maximum) - x(p95), 160, "#fff0de"
        )
        for value in [0, 0.5, 1]:
            content += line(left, y(value), left + 360, y(value)) + text(
                left - 8, y(value) + 4, value, 13, "end"
            )
        points = [
            (0, 1 if reverse else 0),
            (p5, 1 if reverse else 0),
            (p95, 0 if reverse else 1),
            (maximum, 0 if reverse else 1),
        ]
        content += path(
            [(x(a), y(b)) for a, b in points], COLORS[0] if not reverse else COLORS[1], 4
        )
        for raw, name in [(p5, "P5"), (p95, "P95")]:
            content += line(x(raw), 60, x(raw), 235, "#65808a", True) + text(
                x(raw), 258, f"{name}={raw:.2f}", 14, "middle"
            )
        content += text(
            left + 180,
            291,
            "原始值（保留在点表中）" if zh else "Raw value (retained in point table)",
            15,
            "middle",
        )
    content += text(
        480,
        323,
        "纵轴：标准化分数 z，越高越好"
        if zh
        else "Vertical axis: normalized score z; higher is better",
        17,
        "middle",
    )
    return card(
        "normalization",
        "先夹到参考范围，再映射到 0–1" if zh else "Clamp to reference limits, then map to 0–1",
        svg(content, 345, "P5/P95 normalization"),
        legend(
            [
                (
                    "#eaf1f4",
                    "低于 P5：只夹评分用值，不删除记录"
                    if zh
                    else "Below P5: clamp the scoring value; keep the record",
                ),
                (
                    "#fff0de",
                    "高于 P95：只夹评分用值，不删除记录"
                    if zh
                    else "Above P95: clamp the scoring value; keep the record",
                ),
                (COLORS[0], "效益项：多一些更好" if zh else "Benefit: more is better"),
                (
                    COLORS[1],
                    "成本项：少一些更好（反向）" if zh else "Cost: less is better (reversed)",
                ),
            ]
        ),
        "P5 是原基线样本中该指标的第 5 百分位，P95 是第 95 百分位；它们不是 5%／95% 的主观及格分。公交站数 57 超过 P95=48，评分用值夹为 48，所以 z=1，原表仍保留 57；30 站的 z=(30−11)/(48−11)=0.514。通勤 60 分钟的 z=1−(60−28.126)/(87.502−28.126)=0.463。浅色区是两端饱和区：其中再变好或变坏不会继续改变 z。所有情景沿用同一套 A 参数。"
        if zh
        else "P5 is the 5th percentile of this indicator in baseline A. P95 is the 95th percentile. These are not subjective pass marks. A count of 57 exceeds P95=48: the scoring value becomes 48 and z=1, while the raw table still stores 57. For 30 stops, z=(30−11)/(48−11)=0.514. For 60 campus minutes, z=1−(60−28.126)/(87.502−28.126)=0.463. The shaded ends are saturation zones: further changes there do not change z. All scenarios reuse the same A parameters.",
        "outputs/normalization-v1.json; outputs/score/point_scores.csv; actual fitted endpoints",
        language,
    )


def contribution(root: Path, language: str) -> str:
    zh = language == "zh"
    point = pd.read_csv(root / "outputs/score/point_scores.csv", low_memory=False).iloc[0]
    parts = [float(point[f"contribution_{feature}"]) for feature in FEATURES]
    content = text(60, 35, "WOODLANDS SOUTH · LOC_BLD_000d4f886a7311338eff", 19)
    left = 60.0
    for part, color in zip(parts, COLORS, strict=True):
        content += rect(left, 70, part * 800, 65, color)
        if part > 0.04:
            content += text(left + part * 400, 110, f"{part:.3f}", 14, "middle", "white")
        left += part * 800
    content += rect(left, 70, (1 - sum(parts)) * 800, 65, "#eef2f3")
    for value in [0, 0.25, 0.5, 0.75, 1]:
        content += text(60 + value * 800, 162, f"{value:g}", 15, "middle")
    content += text(
        60,
        200,
        ("总分 = 七块相加 = " if zh else "Score = sum of seven segments = ") + f"{sum(parts):.6f}",
        20,
    )
    rows = "".join(
        f"<tr><td>{escape(name)}</td><td>{point['z_' + feature]:.4f}</td><td>{part:.4f}</td></tr>"
        for name, feature, part in zip(LABELS[language], FEATURES, parts, strict=True)
    )
    table = (
        "<table><thead><tr><th>"
        + (
            "指标</th><th>标准化分数 z</th><th>分项贡献 w×z"
            if zh
            else "Indicator</th><th>Normalized z</th><th>Contribution w×z"
        )
        + f"</th></tr></thead><tbody>{rows}</tbody></table>"
    )
    return card(
        "contribution",
        "总分由什么组成：真实分析位置举例"
        if zh
        else "What makes a score: one real analysis location",
        svg(content, 225, "Actual score contributions"),
        feature_legend(language) + table,
        "每一种颜色是一项 w×z。灰色补到 1，只帮助比较，不是第八个指标。贡献小，可能是权重小，也可能是该点表现差；请同时看 z 和 w。这里公园贡献约 0.0102，公交约 0.1000。一个点的分数不等于整区每栋住宅的分数。"
        if zh
        else "Each colored segment is one w×z contribution. Grey fills the scale to 1; it is not an eighth indicator. A small contribution can mean a small weight or poor indicator performance. Check both z and w. Park proximity contributes about 0.0102 here; bus stops contribute 0.1000. This location's score does not describe every home in its Subzone.",
        "outputs/score/point_scores.csv; first saved baseline analysis location; balanced weights; no cap",
        language,
    )


def eligibility(language: str) -> str:
    zh = language == "zh"
    colors = ["#318569"] * 4 + ["#e8ae54"] * 5 + ["#9aaeb8"]
    content = "".join(
        rect(50 + i * 86, 60, 65, 65, color, 5)
        + text(82.5 + i * 86, 100, i + 1, 19, "middle", "white" if i < 4 else "#183343")
        for i, color in enumerate(colors)
    )
    content += text(
        50,
        38,
        "区域计划 N=10，完整有效 V=9，满足约束 F=4"
        if zh
        else "Planned N=10; complete valid V=9; feasible F=4",
        21,
    )
    content += text(50, 175, "V/N = 9/10 = 90%  ✓" if zh else "V/N = 9/10 = 90%  PASS", 22)
    content += text(
        50,
        213,
        "F/N = 4/10 = 40%  → 未达到 50%，该区不进入排名"
        if zh
        else "F/N = 4/10 = 40%  → below 50%; area is not ranked",
        20,
    )
    return card(
        "eligibility",
        "有效覆盖与已验证可行比例：分母都是计划样本"
        if zh
        else "Coverage and verified feasibility both use the planned denominator",
        svg(content, 240, "Eligibility example"),
        legend(
            [
                ("#318569", "有效且满足硬约束 F" if zh else "Valid and feasible F"),
                ("#e8ae54", "有效，但不满足硬约束" if zh else "Valid, but fails a hard constraint"),
                (
                    "#9aaeb8",
                    "缺少必要测量，不算已验证可行"
                    if zh
                    else "Missing a required measurement; not verified feasible",
                ),
            ]
        ),
        "这是教学例子，不是真实分区结果。10 个计划点中，9 个完整有效，4 个满足限制。有效覆盖达到 90%，可行比例只有 40%，所以不推荐整区；不能把缺测的第 10 个点删掉后换分母。通过资格的区域，只对有效且可行点的分数求均值。"
        if zh
        else "This is a teaching example, not an actual Subzone. Of 10 planned locations, 9 have complete measurements and 4 satisfy the constraints. Coverage reaches 90%, but verified feasibility is only 40%, so this area fails. Do not remove the missing tenth location from the denominator. An eligible area's score averages only valid and feasible locations.",
        "src/ge5219/mcda.py; default min_valid_share=.90, min_feasible_share=.50; hypothetical N/V/F",
        language,
        True,
    )


def correlation(root: Path, language: str) -> str:
    zh = language == "zh"
    frame = pd.read_csv(root / "outputs/score/point_scores.csv", low_memory=False)
    corr = frame[list(FEATURES)].corr(method="spearman")
    content = ""
    labels = LABELS[language]
    size, left, top = 60, 240, 72
    for i, label in enumerate(labels):
        content += text(left - 15, top + i * size + 36, label, 16, "end") + text(
            left + i * size + 30, 45, i + 1, 17, "middle"
        )
        for j in range(7):
            value = float(corr.iloc[i, j])
            rgb = np.array([239, 246, 247]) + abs(value) * (
                np.array([183, 65, 58] if value >= 0 else [38, 107, 163])
                - np.array([239, 246, 247])
            )
            color = "#" + "".join(f"{int(v):02x}" for v in rgb)
            content += rect(left + j * size, top + i * size, size - 2, size - 2, color)
            content += text(
                left + j * size + 29,
                top + i * size + 36,
                f"{value:.2f}",
                15,
                "middle",
                "white" if abs(value) > 0.65 else "#183343",
            )
    for k, value in enumerate(np.linspace(-1, 1, 101)):
        rgb = np.array([239, 246, 247]) + abs(value) * (
            np.array([183, 65, 58] if value >= 0 else [38, 107, 163]) - np.array([239, 246, 247])
        )
        content += rect(730, 72 + k * 3.6, 30, 3.8, "#" + "".join(f"{int(v):02x}" for v in rgb))
    content += text(775, 89, "−1", 17) + text(775, 261, "0", 17) + text(775, 443, "+1", 17)
    content += text(
        240, 535, "列号 1–7 与左侧指标顺序相同" if zh else "Columns 1–7 follow the row order", 17
    )
    return card(
        "correlation",
        "原始指标的 Spearman 相关矩阵" if zh else "Spearman correlation of raw indicators",
        svg(content, 560, "Indicator correlation heatmap"),
        legend(
            [
                (
                    "#266ba3",
                    "负相关：一项大时，另一项常小"
                    if zh
                    else "Negative: high values tend to pair with low values",
                ),
                (
                    "#eff6f7",
                    "接近 0：单调关联弱" if zh else "Near zero: weak monotonic association",
                ),
                (
                    "#b7413a",
                    "正相关：两项常同升同降" if zh else "Positive: values tend to rise together",
                ),
            ]
        ),
        "每格是两项原始指标在 A 位置上的秩相关，按可用成对观测计算。它不是排名稳定性图；蓝色也不自动表示坏。成本项与效益项的原始方向不同，正负号要连同指标含义阅读。高度相关提醒我们检查重复计量，但不能仅据一个数字删指标，也不能靠标准化消除相关。"
        if zh
        else "Each cell is the rank correlation of two raw indicators across A locations, using available pairs. This is not a ranking stability chart. Blue is not automatically bad. Raw cost and benefit directions differ, so interpret the sign with each indicator's meaning. Strong correlation prompts a redundancy review; it does not alone justify dropping an indicator. Normalization does not remove correlation.",
        "outputs/score/point_scores.csv; pandas corr(method='spearman'); raw indicators; A locations",
        language,
    )


def stacked_rows(rows: list[tuple[str, list[float]]], language: str, title: str) -> str:
    content = text(30, 30, title, 21)
    for row, (name, values) in enumerate(rows):
        y, x = 70 + row * 70, 210.0
        content += text(195, y + 26, name, 16, "end")
        for value, color in zip(values, COLORS, strict=True):
            content += rect(x, y, value * 670, 40, color)
            if value >= 0.075:
                content += text(x + value * 335, y + 26, f"{value:.0%}", 14, "middle", "white")
            x += value * 670
    for value in [0, 0.25, 0.5, 0.75, 1]:
        content += text(210 + value * 670, 90 + len(rows) * 70, f"{value:.0%}", 15, "middle")
    return svg(content, 120 + len(rows) * 70, title)


def scenarios(root: Path, language: str) -> str:
    zh = language == "zh"
    names = [
        ("campus_first", "校园优先" if zh else "Campus first"),
        ("transit_first", "交通优先" if zh else "Transit first"),
        ("lifestyle", "生活优先" if zh else "Lifestyle"),
        ("balanced", "均衡" if zh else "Balanced"),
    ]
    rows, tops = [], []
    for code, name in names:
        meta = json.loads(
            (root / f"outputs/experiments/scenario_{code}/result_metadata.json").read_text()
        )
        rows.append((name, [float(meta["applied_weights"][feature]) for feature in FEATURES]))
        top = pd.read_csv(root / f"outputs/experiments/scenario_{code}/top5.csv").sort_values(
            "rank"
        )
        tops.append(
            f"<tr><td>{escape(name)}</td><td>{' → '.join(escape(n) for n in top.unit_name)}</td></tr>"
        )
    table = (
        "<table><thead><tr><th>"
        + ("偏好</th><th>真实 Top 5 顺序" if zh else "Preference</th><th>Actual Top 5 order")
        + "</th></tr></thead><tbody>"
        + "".join(tops)
        + "</tbody></table>"
    )
    return card(
        "scenarios",
        "四种偏好：颜色是指标，块宽是权重"
        if zh
        else "Four preferences: colors identify indicators; widths show weights",
        stacked_rows(
            rows, language, "每行权重合计 100%" if zh else "Weights sum to 100% in each row"
        ),
        feature_legend(language) + table,
        "同一颜色在四行中代表同一指标；宽度表示该项在总分中的重要程度，不是设施数量。用户 importance 先除以总和，得到权重。四种偏好只是已声明的解释性方案，不是问卷统计或 AHP。固定数据、标准化、资格规则，只改变权重，因此名单差异可归因于这些偏好设定。"
        if zh
        else "A color means the same indicator in every row. Width shows its importance in the score, not a facility count. Divide each user importance by the total to obtain weights. These are declared illustrative preferences, not survey findings or AHP. Data, normalization and eligibility stay fixed, so differences isolate these weight choices.",
        "outputs/experiments/scenario_*/result_metadata.json and top5.csv; A/Subzone; no commute cap",
        language,
    )


def monte_carlo(root: Path, language: str) -> str:
    zh = language == "zh"
    table = (
        pd.read_csv(root / "outputs/experiments/monte_carlo_frequency.csv")
        .sort_values(["selection_frequency", "unit_id"], ascending=[False, True])
        .head(10)
    )
    areas = pd.read_csv(root / "outputs/score/area_scores.csv").set_index("unit_id")
    content = text(
        40,
        30,
        "每区在 1,000 次实验中进入 Top 5 的次数"
        if zh
        else "Times selected into Top 5 across 1,000 runs",
        21,
    )
    for index, row in enumerate(table.itertuples()):
        y = 62 + index * 34
        name = areas.loc[row.unit_id, "unit_name"]
        content += (
            text(260, y + 20, name, 15, "end")
            + rect(280, y, 540 * row.selection_frequency, 25, COLORS[0])
            + text(830, y + 20, f"{round(row.selection_frequency * 1000):,} / 1,000", 15)
        )
    for value in [0, 0.25, 0.5, 0.75, 1]:
        content += text(280 + 540 * value, 432, f"{value:.0%}", 14, "middle")
    content += text(
        280,
        467,
        "横轴：实验入选频率；纵轴：区域" if zh else "x: selection frequency; y: Subzone",
        17,
    )
    weights = pd.read_csv(root / "outputs/experiments/monte_carlo_weights.csv")
    content += text(
        40,
        522,
        "前 8 次真实抽样权重：各行仍合计 100%"
        if zh
        else "First 8 actual weight draws: each row still sums to 100%",
        20,
    )
    for index, row in weights.head(8).iterrows():
        y, left = 550 + index * 28, 180.0
        content += text(160, y + 16, f"#{index + 1}", 14, "end")
        for feature, color in zip(FEATURES, COLORS, strict=True):
            width = float(row[feature]) * 650
            content += rect(left, y, width, 19, color)
            left += width
    return card(
        "monte_carlo",
        "Monte Carlo：同时改变权重，重复问“谁还在 Top 5？”"
        if zh
        else "Monte Carlo: vary all weights and ask who stays in Top 5",
        svg(content, 800, "Monte Carlo selection frequency and sampled weights"),
        legend(
            [
                (
                    COLORS[0],
                    "上图蓝条：入选次数 / 1,000" if zh else "Upper blue bars: selections / 1,000",
                )
            ]
        )
        + feature_legend(language),
        "上图只列入选频率最高的 10 区，不是全部 241 区。PEOPLE'S PARK 与 CHINATOWN 都是 1,000/1,000；CHINA SQUARE 为 998/1,000，TANJONG PAGAR 为 901/1,000，BOAT QUAY 为 602/1,000。602/1,000 的意思是：在这套权重抽样下，602 次进入前五；不是 60.2% 的学生会选它，也不是客观适合概率。下图展示“变权重”实际是什么样。原始数据、标准化与约束都固定；只检验所声明的偏好不确定性，不能消除缺测、少样本或路线定义问题。"
        if zh
        else "The upper chart shows the 10 highest frequencies, not all 241 Subzones. PEOPLE'S PARK and CHINATOWN appear in 1,000/1,000 runs; CHINA SQUARE in 998; TANJONG PAGAR in 901; BOAT QUAY in 602. A count of 602 means selection in 602 runs under this weight distribution. It is not a 60.2% student choice probability or objective suitability probability. The lower chart shows what varying weights means. Measurements, normalization and constraints stay fixed. This tests the declared preference uncertainty; it does not resolve missing data, sparse samples or route definitions.",
        "outputs/experiments/monte_carlo_frequency.csv + monte_carlo_weights.csv; Dirichlet(50×balanced), seed=42; 1,000 draws; A/Subzone; no cap",
        language,
    )


def oat(root: Path, language: str) -> str:
    zh = language == "zh"
    ranks = pd.read_csv(root / "outputs/experiments/oat_ranks.csv")
    weights = pd.read_csv(root / "outputs/experiments/oat_weights.csv")
    intervals = pd.read_csv(root / "outputs/experiments/oat_switch_intervals.csv")
    joined = ranks.merge(
        weights[["run", "target_feature", "target_weight"]], on="run", validate="many_to_one"
    )
    plots = []
    for feature, feature_name in zip(FEATURES, LABELS[language], strict=True):
        data = joined[joined.target_feature == feature]
        chosen = data[data["rank"] <= 5].sort_values(["rank", "unit_id"]).drop_duplicates("unit_id")
        values = data[data.unit_id.isin(chosen.unit_id)]
        maximum = max(10, int(math.ceil(values["rank"].max() / 10) * 10))
        x = lambda value: 80 + (value - 0.05) / 0.55 * 800
        y = lambda value, maximum=maximum: 75 + (value - 1) / (maximum - 1) * 250
        content = text(40, 30, feature_name, 21)
        content += rect(80, 72, 800, y(5.5) - 72, "#e1efe6")
        for rank in sorted(set([1, 5, 10, maximum] + list(range(20, maximum, 20)))):
            content += line(80, y(rank), 880, y(rank)) + text(65, y(rank) + 5, rank, 14, "end")
        for value in [0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6]:
            content += text(x(value), 352, f"{value:.0%}", 14, "middle")
        local_legend = []
        for index, row in enumerate(chosen.itertuples()):
            series = values[values.unit_id == row.unit_id].sort_values("target_weight")
            color = LINE_COLORS[index]
            points = [
                (x(float(record.target_weight)), y(float(record.rank)))
                for record in series.itertuples()
            ]
            content += path(points, color, 2.4)
            for px, py in points:
                content += f'<circle cx="{px:.2f}" cy="{py:.2f}" r="3" fill="{color}"/>'
            local_legend.append((color, f"{row.unit_name} ({row.unit_id})"))
        changed = int(((intervals.target_feature == feature) & (intervals.top_k_jaccard < 1)).sum())
        content += text(
            480,
            386,
            "横轴：该项权重；纵轴：名次（越上越好）"
            if zh
            else "x: target weight; y: rank (higher on chart is better)",
            16,
            "middle",
        )
        content += text(
            480,
            416,
            f"11 个相邻测试区间中，{changed} 个 Top 5 改变"
            if zh
            else f"Top 5 changes in {changed} of 11 adjacent test intervals",
            16,
            "middle",
        )
        plots.append(
            '<div class="oat-panel">'
            + svg(content, 438, f"OAT {feature}")
            + legend(local_legend)
            + "</div>"
        )
    changed = int((intervals.top_k_jaccard < 1).sum())
    return card(
        "oat",
        "OAT：一次沿一个方向改变偏好，找出敏感来源"
        if zh
        else "OAT: move one weight at a time to identify sensitive preferences",
        "".join(plots),
        legend(
            [
                ("#e1efe6", "绿色背景：Top 5 名次带" if zh else "Green band: Top 5 ranks"),
                (
                    "#6c8290",
                    "圆点：真实测试设置；连线仅帮助阅读"
                    if zh
                    else "Dots: actual test settings; lines guide the eye",
                ),
            ]
        ),
        (
            f"七张小图分别改变一项权重；每条彩线是一名图例所列区域。只显示该项测试中至少一次进入前五的区域，纵轴覆盖这些区域的全部实际名次。横轴从 5% 到 60%，每次 5%；其余六项按原比例一起缩放，使总和仍为 1，并非六项数值都不变。数据、标准化、样本、无通勤上限和资格规则固定。7×12=84 个设置；每项 11 个相邻区间，共 77 个；其中 {changed} 个区间的前五集合改变。连线与切换区间不证明精确临界权重。"
            if zh
            else f"The seven panels vary one weight each. Each colored line is a named Subzone in its legend. A panel shows Subzones that reach Top 5 at least once; its y-axis covers all their actual tested ranks. Target weights run from 5% to 60% in 5-point steps. The other six weights are rescaled in their original proportions to keep the total at 1; their numeric values are not fixed. Data, normalization, samples, eligibility and the no-cap setting stay fixed. There are 7×12=84 settings and 7×11=77 adjacent intervals; Top 5 changes in {changed}. Lines and switch intervals do not identify an exact critical weight."
        ),
        "outputs/experiments/oat_ranks.csv + oat_weights.csv + oat_switch_intervals.csv; A/Subzone; no cap",
        language,
    )


def spatial(root: Path, language: str) -> str:
    zh = language == "zh"
    comparison = json.loads((root / "outputs/experiments/spatial_comparison.json").read_text())
    content = ""
    arms = [
        ("A / Subzone", "2,176", "241", "167"),
        ("B / Subzone", "2,196", "241", "167"),
        ("B / cluster", "2,196", "384", "276"),
    ]
    for index, (name, samples, units, eligible) in enumerate(arms):
        left = 35 + index * 315
        content += rect(left, 28, 275, 173, "#e6f0f2", 7) + text(left + 137, 61, name, 21, "middle")
        for offset, label, value in [
            (98, "位置" if zh else "Locations", samples),
            (133, "区域" if zh else "Units", units),
            (168, "合格" if zh else "Eligible", eligible),
        ]:
            content += text(left + 20, offset, label, 17) + text(
                left + 254, offset, value, 21, "end"
            )
    content += text(
        176, 239, "A → B：只补点" if zh else "A → B: supplement points", 18, "middle"
    ) + text(650, 239, "B → B：只改汇总单元" if zh else "B → B: change unit system", 18, "middle")
    nleft, nright, common = (
        comparison["n_subzone_positions"],
        comparison["n_cluster_positions"],
        comparison["n_common_positions"],
    )
    positions = [
        ("仅 Subzone" if zh else "Subzone only", nleft - common, COLORS[0]),
        ("共同位置" if zh else "Shared locations", common, COLORS[2]),
        ("仅 cluster" if zh else "Cluster only", nright - common, COLORS[1]),
    ]
    left = 100.0
    for name, count, color in positions:
        width = count / (nleft + nright - common) * 760
        content += rect(left, 295, width, 68, color) + text(
            left + width / 2, 335, count, 23, "middle", "white"
        )
        left += width
    content += text(
        480,
        400,
        f"共同 B 位置：交集 {common} / 并集 {nleft + nright - common} = {comparison['jaccard_positions']:.3f}"
        if zh
        else f"Common B locations: intersection {common} / union {nleft + nright - common} = {comparison['jaccard_positions']:.3f}",
        21,
        "middle",
    )
    return card(
        "spatial",
        "三臂对照：先分开补点效应与聚合效应"
        if zh
        else "Three arms separate supplementation from aggregation",
        svg(content, 425, "Spatial comparison arms and common-location overlap"),
        legend([(color, f"{name}: {count}") for name, count, color in positions]),
        "上面三张卡中的“合格数”不是 Top 5 数。A/B Subzone 的前五相同（Jaccard=1），共同合格区域名次 Spearman≈0.99948。cluster 与 Subzone 的 ID 属于不同实体，不能直接拿 ID 或名次跨类型比较。下图先把两份 B 的前五展开成共同分析位置：13 与 5 个位置，交集 4、并集 14；这才得到 4/14。全量候选来源记录另算为 16/65≈0.246。面积与成员数量不同，本身就会影响重叠；低重叠不能单独证明模型失败或哪个尺度更好。"
        if zh
        else "Eligible counts in the cards are not Top 5 counts. A/B Subzone Top 5 sets match (Jaccard=1); common eligible ranks have Spearman≈0.99948. Cluster IDs and Subzone IDs identify different entities, so do not compare their IDs or ranks directly. The lower chart expands both B Top 5 selections into common analysis locations: 13 and 5 locations, intersection 4 and union 14, giving 4/14. The separate full candidate-record overlap is 16/65≈0.246. Unit size and membership affect overlap; a low value alone does not prove model failure or identify the better scale.",
        "outputs/experiments/spatial_comparison.json; spatial_* result bundles; balanced; cap=60 min; fixed A normalization",
        language,
    )


def count_bars(root: Path, language: str, kind: str) -> str:
    zh = language == "zh"
    if kind == "caps":
        rows = [
            ("无上限" if zh else "No cap", root / "outputs/score"),
            ("40 min", root / "outputs/experiments/commute_cap_40"),
            ("60 min", root / "outputs/experiments/commute_cap_60"),
        ]
        labels = [
            (name, int(pd.read_csv(folder / "area_scores.csv").eligible.sum()))
            for name, folder in rows
        ]
        title = (
            "原始通勤分钟上限改变，合格区域随之改变"
            if zh
            else "Commute caps change the eligible areas"
        )
        reading = (
            "横轴是合格区域数，不是分数；蓝条长度对应数量。默认不设上限。40 分钟时只剩 51 区，60 分钟时 167 区；点位约束按原始分钟判断，标准化分数再高也无法补偿超时。只在通过所有约束的位置上计算区域均分，因此改变上限也可能改变均分的组成。"
            if zh
            else "The x-axis is an eligible-area count, not a score. Blue bar length shows the count. The default has no cap. A 40-minute cap leaves 51 areas; 60 minutes leaves 167. The constraint uses raw minutes, so high normalized scores cannot compensate for failing it. Area means use only feasible locations, so caps can also change which locations enter a mean."
        )
        source = "outputs/score/area_scores.csv; outputs/experiments/commute_cap_{40,60}/area_scores.csv; A/Subzone, balanced, fixed A normalization"
    else:
        rows = [
            ("25%", root / "outputs/experiments/qualification_25"),
            ("50%", root / "outputs/experiments/qualification_50"),
            ("75%", root / "outputs/experiments/qualification_75"),
        ]
        labels = [
            (name, int(pd.read_csv(folder / "area_scores.csv").eligible.sum()))
            for name, folder in rows
        ]
        title = (
            "区域 F/N 门槛改变：名单相同不等于候选集合相同"
            if zh
            else "Change the F/N rule: matching Top 5 does not mean matching eligibility"
        )
        reading = (
            "蓝条显示在不同 F/N 门槛下有多少区域合格。门槛从 25% 提高到 75%，合格集合从 178 缩到 152，虽然这三次的前五名单相同。此实验固定 60 分钟上限、90% 有效覆盖、均衡权重与 A 的标准化；只改变区域已验证可行比例的政策门槛。这三个百分比不是学生问卷接受比例。"
            if zh
            else "Bars show eligible-area counts under each F/N rule. Raising the rule from 25% to 75% reduces eligibility from 178 to 152, even though Top 5 stays the same in these three runs. The experiment fixes the 60-minute cap, 90% valid coverage, balanced weights and A normalization. Only the verified-feasible-share policy changes. These percentages are not survey acceptance rates."
        )
        source = "outputs/experiments/qualification_{25,50,75}/area_scores.csv; qualification_comparisons.csv; fixed cap=60 min"
    content = text(
        40,
        30,
        "纵轴：实验条件；横轴：合格区域数" if zh else "y: test setting; x: eligible area count",
        21,
    )
    for i, (name, count) in enumerate(labels):
        y = 70 + i * 75
        content += (
            text(175, y + 28, name, 20, "end")
            + rect(200, y, count / 241 * 650, 42, COLORS[0])
            + text(210 + count / 241 * 650, y + 28, count, 21)
        )
    for tick in [0, 50, 100, 150, 200, 241]:
        content += text(200 + tick / 241 * 650, 322, tick, 15, "middle")
    return card(
        kind,
        title,
        svg(content, 350, title),
        legend(
            [
                (
                    COLORS[0],
                    "通过全部资格规则的 Subzones"
                    if zh
                    else "Subzones passing all eligibility rules",
                )
            ]
        ),
        reading,
        source,
        language,
    )


def build_visuals(root: Path, language: str) -> dict[str, str]:
    return {
        "measurement": measurement(language),
        "normalization": normalization(root, language),
        "contribution": contribution(root, language),
        "eligibility": eligibility(language),
        "correlation": correlation(root, language),
        "scenarios": scenarios(root, language),
        "monte_carlo": monte_carlo(root, language),
        "oat": oat(root, language),
        "spatial": spatial(root, language),
        "caps": count_bars(root, language, "caps"),
        "qualification": count_bars(root, language, "qualification"),
    }
