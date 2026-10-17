"""Standalone visual evidence of spatial preparation, without invented MCDA scores."""

import base64
import html
import io
import json
from pathlib import Path

import geopandas as gpd
import pandas as pd

from .artifacts import read_locations
from .settings import FEATURES


def _figure_data(figure) -> str:
    import matplotlib.pyplot as plt

    buffer = io.BytesIO()
    figure.savefig(buffer, format="png", dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(figure)
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def create_preparation_report(prepared: Path, output: Path) -> Path:
    """Show actual audit counts, frozen sample geography and outstanding evidence."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    quality = json.loads((prepared / "data_quality.json").read_text(encoding="utf-8"))
    locations = read_locations(prepared / "static_indicators.csv")
    clusters = pd.read_csv(prepared / "clusters.csv")
    subzones = gpd.read_file(prepared / "subzones.geojson").to_crs(3414)
    points = gpd.GeoDataFrame(locations, geometry=gpd.points_from_xy(
        locations.longitude, locations.latitude), crs=4326).to_crs(3414)
    figure, axis = plt.subplots(figsize=(13, 7))
    subzones.plot(ax=axis, facecolor="#edf2f6", edgecolor="#c6d1db", linewidth=.4)
    points.loc[points.sample_A].plot(ax=axis, color="#126a94", markersize=5, label="A: 400 m baseline")
    points.loc[~points.sample_A].plot(ax=axis, color="#db7047", markersize=27,
                                    marker="^", label="B supplements: uncovered clusters")
    axis.set(title="Frozen analysis locations — actual residential source points",
             xlabel="SVY21 easting (m)", ylabel="SVY21 northing (m)")
    axis.legend(loc="upper left", frameon=True)
    map_image = _figure_data(figure)
    figure, axes = plt.subplots(2, 3, figsize=(13, 7), constrained_layout=True)
    for axis, feature in zip(axes.flat, FEATURES[1:], strict=True):
        axis.hist(locations[feature].dropna(), bins=30, color="#237f9e", edgecolor="white")
        axis.set(title=feature, ylabel="Sample points")
    distributions = _figure_data(figure)
    cards = [("暂留住宅来源记录", quality["candidate_records"]),
             ("有候选的 Subzones", quality["area_count"]),
             ("分析簇", quality["cluster_count"]),
             ("原400 m样本 A", quality["sample_A_count"]),
             ("共同对照样本 B", quality["sample_B_count"]),
             ("簇覆盖补点", quality["supplement_count"])]
    cards_html = "".join(f'<div class="card"><b>{value:,}</b><span>{label}</span></div>'
                         for label, value in cards)
    largest = clusters.nlargest(5, "n_buildings")[["area_name", "n_buildings",
                                                  "extent_diagonal_m", "n_sample_B"]].copy()
    largest.columns = ["所属 Subzone", "住宅来源记录数", "包围盒对角线（m）", "B样本点数"]
    largest["包围盒对角线（m）"] = largest["包围盒对角线（m）"].round(0)
    blockers = "".join(f"<li>{html.escape(item)}</li>" for item in quality["readiness_blockers"])
    source_rows = [
        ("原始来源记录", quality["source_records"]),
        ("冲突邮编 / 隔离记录", f'{quality["conflict_postal_codes"]} / {quality["held_out_records"]}'),
        ("单栋分析簇", quality["singleton_clusters"]),
        ("暂纳入公园面 / 按源N_RESERVE旗标排除", f'{quality["park_candidate_records"]} / {quality["nature_reserves_excluded"]}'),
        ("诊所牌照 → 服务地址", f'{quality["clinic_source_records"]} → {quality["clinic_sites"]}'),
        ("超市牌照 → 服务地址单元", f'{quality["supermarket_source_records"]} → {quality["supermarket_sites"]}'),
        ("轨道出口来源 → 部分运营核查后纳入", f'{quality["rail_exit_source_records"]} → {quality["rail_exit_candidate_records"]}'),
    ]
    source_table = pd.DataFrame(source_rows, columns=["项目", "实际数量"]).to_html(index=False, border=0)
    document = f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>GE5219 · 实施进度与数据证据</title>
<style>
:root{{color-scheme:light}}*{{box-sizing:border-box}}body{{margin:0;background:#edf2f6;color:#183047;font:16px/1.75 'Microsoft YaHei',system-ui,sans-serif}}main{{max-width:1180px;margin:auto;padding:44px 24px}}header{{border-left:6px solid #d87650;padding:8px 26px;margin-bottom:32px}}h1{{font-size:36px;line-height:1.3;margin:8px 0}}h2{{font-size:23px}}.eyebrow{{color:#187d9b;letter-spacing:2px;font-weight:bold}}.sub{{color:#526678}}.cards{{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}}.card,section{{background:white;border-radius:14px;padding:23px;box-shadow:0 4px 22px #152c4110}}.card b{{display:block;font-size:32px;color:#136984}}.card span{{font-size:14px;color:#566d80}}section{{margin-top:24px}}.notice{{background:#fff3e6;border-left:5px solid #d87650;padding:18px 22px;margin:26px 0;border-radius:8px}}.flow{{display:flex;gap:12px;flex-wrap:wrap}}.flow div{{flex:1;min-width:170px;padding:15px;background:#edf7f8;border-radius:8px}}.flow .pending{{background:#fff3e6}}img{{width:100%;height:auto}}table{{border-collapse:collapse;width:100%;font-size:14px}}th,td{{padding:11px;text-align:left;border-bottom:1px solid #e0e8ee}}th{{color:#126a82}}code{{font-size:12px;overflow-wrap:anywhere}}details{{margin-top:20px}}footer{{margin-top:30px;color:#657687;font-size:13px}}@media(max-width:650px){{.cards{{grid-template-columns:repeat(2,1fr)}}h1{{font-size:28px}}main{{padding:22px 13px}}section{{padding:17px}}}}
</style><main><header><div class="eyebrow">GE5219 / XIE BINGSHENG / IMPLEMENTATION</div>
<h1>从住宅点到可复算的推荐</h1><div class="sub">真实空间准备的阶段性证据 · 2026-10-17</div></header>
<div class="notice"><strong>此页展示真实数据的空间准备与六项静态指标。</strong><br>通勤、七维排名、敏感性实验及路线复核状态另见结果交接页。下列数量是输入审计与采样结果，不能当作推荐效果。</div>
<div class="cards">{cards_html}</div>
<section><h2>实施链路</h2><div class="flow"><div><b>已运行</b><br>来源映射与冲突隔离<br>统一投影与空间分区</div><div><b>已运行</b><br>150 m连接簇<br>400 m采样＋漏簇补点</div><div><b>已运行</b><br>六项静态测量<br>与B交通字段交叉核对</div><div class="pending"><b>另行追溯</b><br>AS8终点、通勤与评分<br>实验和独立复核证据</div></div></section>
<section><h2>原样本与补点在哪里？</h2><p>蓝点为原样本A，橙色三角为20个漏簇补点。每个位置都是实际来源中的住宅点；周围全部建筑并未因此获得实测通勤。</p><img alt="住宅基线样本与簇覆盖补点地图" src="{map_image}"><p class="sub">三组对照固定为 A→Subzone、B→Subzone、B→cluster。后两组使用完全相同的位置与点级分数。</p></section>
<section><h2>数据处理有明确去向</h2>{source_table}<p>邮编冲突尚未裁决，因此两边记录暂隔离；这并不证明某一来源错误。共址但不同地址单元的记录保留。公园距离表示几何邻近，公交计数表示站点供给。</p></section>
<section><h2>六项真实静态指标的分布</h2><p>不同面板保留各自单位；距离以米计，供给以去重后的站点或服务地址计。真实零值与未知值分别处理。</p><img alt="六项静态指标分布直方图" src="{distributions}"></section>
<section><h2>150 m连接不等于150 m大小的小区</h2><p>住宅可以链式相连，因此大型分析簇可能横跨数公里。下表列出住宅记录最多的5个簇；它们不是已验证的真实小区，也不表示按住户人数加权。</p>{largest.to_html(index=False,border=0)}<p class="sub">包围盒对角线是空间尺度诊断，不是精确最大点间距离。单点簇保留，但会标记样本支持有限。</p></section>
<section><h2>后续结果应具备什么证据？</h2><ol><li>记录AS8地面到达代理点的核查依据；凭证只通过本机环境传入。</li><li>缓存查询{quality['unique_route_origins_B']:,}个独立起点，保留逐点状态；失败不补零。</li><li>冻结A的P5/P95，运行评分、四情景、OAT、1,000次权重扰动和三组空间对照。</li><li>保留至少20条独立路线核查证据，并复核住宅用途、设施类别、运营状态与地址标记。API成功不等于这些检查已完成。</li></ol><details><summary>查看静态准备记录的质量要求</summary><ul>{blockers}</ul></details></section>
<footer>数据版本 <code>{html.escape(quality.get('dataset_version','not recorded'))}</code><br>可视化来自本次实际空间准备输出。模型测试中的合成数据未混入此页。</footer></main></html>'''
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(document, encoding="utf-8")
    return output
