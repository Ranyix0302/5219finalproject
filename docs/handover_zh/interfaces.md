# 接口交接：下一位能直接调用什么

**已经有“计算评分”和“加通勤限制”的接口。** 推荐核心在 Python 中。现有网页读取已保存的情景结果。当前没有供网页直接访问的 HTTP 服务，也没有任意距离限制接口。

“接口”就是约定好的入口：你交给它参数，它返回结果。下一位不需要重写 MCDA，也不需要再次请求 OneMap，便能改变权重或通勤上限。

## 1. 四种交接入口

| 入口 | 怎样使用 | 当前状态 |
|---|---|---|
| Python 函数 | `ge5219.mcda.recommend(...)`；重新算分、加通勤限制 | 已实现 |
| 命令行 | `python -m ge5219 score ...`；保存一个可复现的情景 | 已实现；部分高级参数仅 Python 支持 |
| 四文件结果包 | 三个 CSV + `result_metadata.json`；地图、表格、解释读取同一份结果 | 已实现 |
| HTTP/网页实时请求 | 浏览器提交选择，服务端调用 Python，再返回 JSON | **尚未实现，见第 8 节** |

还有空间准备、路线缓存、实验和质量状态入口，见第 7 节。[英文公共契约](../interfaces.md)记录底层约定。

## 2. 已实现的评分参数

```python
recommend(frame, params, weights, group_by="area_id", max_commute_min=None,
          min_valid_share=0.9, min_feasible_share=0.5,
          metadata=None, k=5)
```

| 参数 | 通俗解释 | 默认值与单位 | CLI 是否可改 |
|---|---|---|---|
| `frame` | 本次全部计划分析位置；包括失败、未知和不合格位置 | A 为 2,176 点；B 为 2,196 点 | `--sample-set A` 或 `B` |
| `params` | 冻结的七项 P5/P95 及方向 | `outputs/normalization-v1.json` 的 `parameters` | `--normalization` 路径 |
| `weights` | 七项“重要程度”；函数自动除以总和 | Python 必填；CLI 默认 balanced | `--weights` 或 `--scenario` |
| `group_by` | 汇总到哪一种区域 | `area_id`；可换 `cluster_id` | `--group-by` |
| `max_commute_min` | 最多接受多少分钟；原始时间 ≤ 上限才通过 | `None` 即不上限；可设 40、60 等非负分钟 | `--max-commute-min` |
| `min_valid_share` | 该区有效测量点数/计划点数至少多少 | `0.9` 即 90%；取值 0–1 | 未暴露；用 Python |
| `min_feasible_share` | 该区已验证可行点数/计划点数至少多少 | `0.5` 即 50%；取值 0–1 | 未暴露；用 Python |
| `k` | 最多推荐多少个合格区域 | `5`，正整数 | 未暴露；用 Python |
| `metadata` | 数据版本、校园、时段、样本、来源哈希等证据 | 可传字典；交接应保留原上下文 | CLI 自动建立 |

**权重不是硬约束。** 降低校园通勤权重仍可能推荐通勤很久的位置。设 `max_commute_min=40` 才会把超过 40 分钟的位置排除在可行评分外。

**区域门槛不是点的距离限制。** 一个区计划 10 个点，9 个测量完整，4 个满足通勤上限：有效测量覆盖 = 90%，已验证可行比例 = 40%，因此默认不能推荐整个区。不能用 4/9 替换 4/10。

`limited_support=True` 表示 `n_valid<3`。它是“证据较少”的标记，不会自动禁止该区，也不是居民覆盖率。当前许多 Top 5 有此标记，应继续展示。

七项权重顺序固定；字段名字典更不容易填错：

| 顺序 | 字段名 | 单位 | 方向 |
|---|---|---|---|
| 1 | `campus_transit_min` | 第一条 OneMap itinerary 的分钟数 | 越小越好 |
| 2 | `rail_exit_euclid_m` | 到轨道出口的欧氏距离，米 | 越小越好 |
| 3 | `bus_stops_800m` | 800 米欧氏半径内公交站点数 | 越大越好 |
| 4 | `supermarket_sites_800m` | 800 米欧氏半径内超市服务地点数 | 越大越好 |
| 5 | `library_euclid_m` | 到图书馆的欧氏距离，米 | 越小越好 |
| 6 | `clinic_sites_1000m` | 1,000 米欧氏半径内医疗服务地点数 | 越大越好 |
| 7 | `park_proximity_euclid_m` | 到公园多边形的欧氏邻近距离，米；内部为 0 | 越小越好 |

四套预设权重为 `campus_first`、`transit_first`、`lifestyle`、`balanced`，是声明的偏好情景，不是调查估计。不得少传一项；零权重也仍要求该指标有效。布尔值、负数、非有限值和全零权重会被拒绝。

## 3. 最简 Python 调用

按[代码结构文档](code_structure.md)安装环境。从完整包根目录运行，不需要 token：

```python
import json
from pathlib import Path
from ge5219.artifacts import read_locations, save_result
from ge5219.mcda import recommend
from ge5219.settings import SCENARIOS

root = Path.cwd()
frame = read_locations(root / "outputs/score/indicator_matrix.csv")
frame_A = frame.loc[frame.sample_A].copy()
params = json.loads((root / "outputs/normalization-v1.json").read_text(
    encoding="utf-8"))["parameters"]
stored = json.loads((root / "outputs/score/result_metadata.json").read_text(
    encoding="utf-8"))
output_keys = {"result_id", "status", "applied_weights", "group_by",
               "max_commute_min", "min_valid_share", "min_feasible_share"}
context = {key: value for key, value in stored.items() if key not in output_keys}
result = recommend(frame_A, params, SCENARIOS["balanced"],
                   max_commute_min=40, metadata=context)
save_result(result, root / "outputs/interface_acceptance/my_cap40")
print(result["metadata"]["status"])
print(result["top5"][["unit_name", "score", "n_planned", "n_feasible"]])
```

这是最短示意。正式联调用[完整可运行示例](../../examples/score_from_handover.py)：它还检查数据版本、静态指标/路线哈希、A 样本指纹，并重建矩阵，避免新旧数据混用。

要改变偏好及资格门槛：

```python
weights = {"campus_transit_min": 3, "rail_exit_euclid_m": 2,
           "bus_stops_800m": 1, "supermarket_sites_800m": 1,
           "library_euclid_m": 1, "clinic_sites_1000m": 1,
           "park_proximity_euclid_m": 1}
result = recommend(frame_A, params, weights, max_commute_min=60,
                   min_feasible_share=0.75, k=3, metadata=context)
```

实际使用权重为 `[0.3,0.2,0.1,0.1,0.1,0.1,0.1]`。返回键仍叫 `top5`，但这次最多 3 行；不要按文件名补成五行。

比较住宅簇：用完整 B 表 `frame`，设 `group_by="cluster_id"`，metadata 的 `sample_set` 标为 `B`。不能只把 A 的 Subzone 名称换成 cluster 名称。重新聚合仍用固定 A 标准化参数。

## 4. 命令行

在完整包根目录运行。**用新输出目录，保留正式基线**：

```powershell
.\.venv\Scripts\python.exe -m ge5219 score --routes outputs/routes.csv --max-commute-min 40 --output outputs/interface_acceptance/cli_cap40
.\.venv\Scripts\python.exe -m ge5219 score --routes outputs/routes.csv --weights "3,2,1,1,1,1,1" --output outputs/interface_acceptance/cli_custom_weights
.\.venv\Scripts\python.exe -m ge5219 score --routes outputs/routes.csv --sample-set B --group-by cluster_id --max-commute-min 60 --output outputs/interface_acceptance/cli_B_cluster
.\.venv\Scripts\python.exe examples/score_from_handover.py
```

`--weights` 覆盖 `--scenario`。CLI 没有 `--min-feasible-share`、`--min-valid-share` 或 `--k`；这些能力已在 Python 中，需要时直接调用函数。若以后也要在 CLI 暴露，只需解析这些参数并传给 `recommend`，不必修改公式。

## 5. 输入、输出与结果标识

### 输入

| 文件 | 内容 |
|---|---|
| `outputs/prepared/static_indicators.csv` | 全部 B 计划点，ID、Subzone/cluster、经纬度、sample_A 和六项静态指标 |
| `outputs/routes.csv` | 同一位置、校园和时段的路线状态/分钟及起终点证据 |
| `outputs/normalization-v1.json` | 固定 A 的七项 P5/P95、数据版本及 A 测量指纹 |
| `config/destination.json` | 核准的 NUS AS8 地面到达代理点 |
| `outputs/score/indicator_matrix.csv` | 已合并的 B 七维表；教学方便，正式联调优先重建并核对 |

`location_id` 唯一；区域 ID 对应一致名称；ID/邮编是字符串，不能丢前导 0。经纬度为 EPSG:4326，距离计算用 EPSG:3414。不要先删失败路线，否则分母变小，会高估区域资格。

`assemble_matrix` 校验唯一 ID、起点、校园终点、时刻和 TRANSIT 模式，再左连接全部计划点。失败/未查询时间保留未知；`Success` 才能作为有效原始分钟。

### 四文件结果包

| 文件 | 关键字段与用途 |
|---|---|
| `point_scores.csv` | 原始指标，七项 `z_` 分数、七项 `contribution_` 贡献，`is_valid/is_feasible`，测量/可行状态，总分与 `result_id`；被拒绝和未知点仍保留 |
| `area_scores.csv` | `unit_id/name/type`，`n_planned/n_valid/n_feasible`，有效/条件可行/已验证可行三种比例，`eligible/limited_support`，均分、标准差/最小/最大，原始通勤/轨道距离均值，贡献均值、rank、result_id |
| `top5.csv` | 最多 k 个合格区域；已完成确定排序 |
| `result_metadata.json` | status、result_id、实际权重、限制、资格门槛、数据/方法版本、校园/时段和测量来源 |

字段全名见[公共契约](../interfaces.md)与示例输出。点只有测量完整并满足约束后才获总分/贡献。区域分数是可行点平均，不按建筑数或人口加权。区域有分也可能因门槛不足不合格。不合格区域没有 rank。

排序按完整精度总分降序；完全相同再比较原始平均通勤、轨道距离和稳定 ID。网页不能按四舍五入的显示值重新排序。score 是 0–1 模型分，不是满意率或概率。

四部分的 `result_id` 必须一致。它由输入、参数、权重、限制、k 和 metadata 一起生成。改 metadata 也可能改 ID；它不代替数据版本和哈希。地图、表格和 Agent 必须引用同一 ID。

当前哈希还保留数字写法：Python 传整数 `40`，CLI 解析成浮点 `40.0`，分数相同但 ID 不同。联调应固定参数类型，并使用函数返回的 ID，不从界面显示值自行拼 ID。这是结果标识的限制，不是评分差异。

`save_result` 写上述四文件；CLI score 另外写全 B 的 `indicator_matrix.csv`。即使选 A，这份额外矩阵仍是 B；实际评分点以 point_scores 和 sample_set 为准。

### 无结果和缺失

| metadata.status | 含义 | 网页展示 |
|---|---|---|
| `ok` | 至少一个合格区域；可能不足 k 个 | 实际数量及证据标记 |
| `data_coverage_insufficient` | 没有任何区达到有效测量覆盖门槛 | “现有完整测量不足，不能推荐” |
| `no_feasible_results` | 覆盖不是唯一原因，但没有区域通过完整资格规则 | “没有区域满足当前条件，可调整限制” |
| `unsupported_destination` | 目的地不是目前支持的 NUS_AS8 | “该校园尚未完成通勤测量” |

非法参数、缺列、重复 ID 等抛 `ValueError`。CLI 记录 `invalid_parameters_or_inputs`，退出码 2。合法但无结果仍退出 0，必须读 status。

CSV 空白可能读成 NaN/NA；JSON 必须变成 `null`，页面显示“未知”，不能替换 0。用公开 `write_json`，避免非标准 `NaN` JSON。

## 6. 本次实际验收

完整示例已执行八项，无路线客户端调用，正式基线及输入哈希未改变：

| 情景 | 样本/单位 | 合格数 | 核对 |
|---|---|---:|---|
| balanced，无上限 | A/Subzone | 239 | 精确复现正式 mcda-7541f705e66a7e1095a13b60 |
| 40 分钟 | A/Subzone | 51 | Top ID、分数与保存实验一致 |
| 60 分钟 | A/Subzone | 167 | Top ID、分数与保存实验一致 |
| 自定义 [3,2,1,1,1,1,1] | A/Subzone | 239 | 实际规范为 [.3,.2,.1,.1,.1,.1,.1] |
| 60 分钟、75% 可行门槛 | A/Subzone | 152 | 与保存 qualification_75 一致 |
| k=3 | A/Subzone | 239 | 只返回三行 |
| 60 分钟住宅簇 | B/cluster | 276 | 与保存空间对照一致 |
| 0 分钟上限 | A/Subzone | 0 | no_feasible_results，Top 表空 |

默认 Top 5：PEOPLE'S PARK、CHINA SQUARE、CHINATOWN、TANJONG PAGAR、BOAT QUAY。40 分钟 Top 5：PEOPLE'S PARK、TANJONG PAGAR、CLEMENTI CENTRAL、HOLLAND DRIVE、JURONG GATEWAY。

证据：[acceptance_summary.json](../../outputs/interface_acceptance/acceptance_summary.json)。各情景目录有四文件及标准 JSON `response.json`，都位于 `outputs/interface_acceptance/`。下一位应复跑；这证明与冻结成果一致，不证明每条现实测量已准确。

第 4 节的三条 CLI 也已执行，与相同数值的 Python 结果一致；按 CLI 的浮点上限类型重放时 ID 精确一致。见 [cli_acceptance_summary.json](../../outputs/interface_acceptance/cli_acceptance_summary.json)。

## 7. 其他流水线接口与固定版本

| 入口 | 作用 |
|---|---|
| `spatial.prepare_data(data_root, output_dir)` / CLI prepare | 原始图层到代表点、静态指标、住宅簇及审计；不需 API |
| `pipeline.assemble_matrix` | 验证并连接全部计划位置和路线；不需 API |
| `mcda.fit_normalization/normalize_indicators` | 拟合/应用 P5/P95；当前情景只应用冻结参数 |
| `routing.OneMapClient/SQLiteRouteCache/route_locations` / CLI route | 新路由、断点续跑和场景缓存；需本机 ONEMAP_TOKEN，仅在测量变化时用 |
| `experiments.run_experiments` / CLI experiments | 四情景、Monte Carlo、OAT、空间/门槛对照；现有路线无需新请求 |
| CLI status | 准备数据、校园核准、路由和结果元数据状态 |

场景固定 `2026-10-19T08:00:00+08:00`（新加坡时区），方法 `mcda-v1.0`。校园为 NUS_AS8 地面到达代理点。第一 itinerary 可能纯步行，也可能不含请求时刻到真正出发的等待；通勤上限约束的是这个特定时长，不能宣传为完整门到门时间。见[处理方法](processing_methods.md)。

公开评分函数不自行检查标准化属于哪份 A；CLI 和完整示例会查数据版本、A 指纹。服务端也必须检查并固定路线/静态哈希。改权重、上限、A/B 或聚合不能重拟合 P5/P95。数据、时段或指标含义变化时显式创建新分析/参数版本。

## 8. 网页实时评分怎样接：以下尚未实现

目前没有 `POST /recommendations` 地址。下面是拟议请求契约，不能当现成接口调用：

```json
{
  "analysis_version": "mcda-v1.0",
  "destination_id": "NUS_AS8",
  "departure": "2026-10-19T08:00:00+08:00",
  "sample_set": "A", "group_by": "area_id",
  "weights": {
    "campus_transit_min": 3, "rail_exit_euclid_m": 2,
    "bus_stops_800m": 1, "supermarket_sites_800m": 1,
    "library_euclid_m": 1, "clinic_sites_1000m": 1,
    "park_proximity_euclid_m": 1
  },
  "max_commute_min": 40, "min_valid_share": 0.9,
  "min_feasible_share": 0.5, "k": 5
}
```

下一位依次实现：

1. 只接受已声明字段与支持的版本、校园、时段、样本和聚合；按第 2 节校验类型/范围。未知字段报错，不能悄悄忽略用户想要的限制。
2. 从服务端固定目录加载核对后的 A/B、路线和参数。网页不能传本地路径、归一化文件、token 或代码。
3. 调用现有 recommend 并保存完整结果包。记录请求和实际参数，包括 k；当前核心 metadata 不单独返回 k。
4. 返回 result_id、metadata、top5 及同一 ID 的地图/详情引用；详情从该 ID 的 point/area 表读取。保留门槛、实际权重、低样本标记、来源版本和状态。
5. NaN/NA/非有限值转 null。建议非法参数返回 HTTP 422；合法无结果返回 HTTP 200 和领域 status；服务错误单列。HTTP 状态映射仍需实现。

Agent 只把自然语言转换为结构化字段，再解释函数返回证据；不临时写代码、补测量或自行排名。

联调验收：同第 6 节参数得到相同实际权重、资格数量、Top ID/分数及来源证据；地图表格 result_id 一致。只有 metadata 也完全一致时才要求旧 ID 一样，不能加请求流水号后还要求旧 ID 不变。

## 9. 当前不支持的新要求与实施方法

| 新要求 | 当前缺口 | 下一位要补 |
|---|---|---|
| MRT 必须在 500 米内 | 仅通勤硬约束；距离目前只评分 | 先批准原始字段/单位，再扩展核心可行判定、原因状态和版本；测边界、未知和计划分母；不能先删点再评分 |
| 公园使用 distance decay | 没有计算 decay | 定义函数/β 和设施含义，重算指标、新版本标准化及相关性/稳健性对照 |
| 改到 NTU/SMU | 只支持 NUS_AS8 | 核准终点、查新路线、议定跨校园标准化/版本并扩展支持；不能复用 NUS 时间 |
| 250/500 米网格或不同簇半径 | 不是 recommend 参数 | 版本化准备阶段，重建位置/指标，新位置补路由后重做对照 |
| 网页拖动权重实时算分 | 核心可算，HTTP 未封装 | 实现第 8 节，或预先生成有限情景供选择 |

待商讨：继续只支持通勤硬约束还是增加距离条件；实时评分还是保存情景；是否给低样本区域设置额外资格；通勤是否改含初始等待。先明确研究和产品含义，再进入新版本。
