# 代码结构与运行说明

把程序理解为一条分段流水线：原始图层 → 住宅/采样与静态指标 → 路由缓存 → 七维矩阵 → 标准化与评分 → 实验 → 网页与解释。Python 负责算分；网页展示已保存结果；语言模型不另算一套分数。

## 1. 文件夹各管什么

| 位置 | 内容与用途 |
|---|---|
| `raw_data/` | A/B 的 176 个原始交付副本，含 ZIP 与解压内容；保持只读 |
| `config/` | 目的地、七指标字典、交通运营及设施地址规则；更改要记录版本并重算相关结果 |
| `src/ge5219/` | 下表十三个应用模块 |
| `notebooks/` | 中英各一份完整流程；从解压后的包运行 |
| `outputs/prepared/` | 派生住宅、簇归属、代表点、六项静态指标、质量与来源哈希 |
| `outputs/routes.csv`、`routes.sqlite` | 固定场景的通勤测量与断点续跑缓存 |
| `outputs/score/` | 正式 A/Subzone、均衡、无上限基线，保持冻结 |
| `outputs/experiments/` | 四情景、每次权重/名次、OAT、空间与门槛对照 |
| `outputs/audits/` | 独立算术、原始文件复制、notebook 与交接核查；有范围限制 |
| `docs/` | 通俗说明、处理方法、接口、决策、方法稿及进度；旧计划看日期，不当当前结果 |
| `tests/` | 合成测试输入，不能当研究观测 |

GitHub 只提供源码、文档和 notebook；`raw_data/`、已计算数据和缓存在完整交接 ZIP。不要在代码或 notebook 单元格粘贴 token；新增请求从本机 `ONEMAP_TOKEN` 读取。

## 2. 从哪个模块读起

| 模块 | 只负责什么 |
|---|---|
| `spatial.py` | 读 A/B、来源映射和冲突隔离、投影/几何、150 m 簇、400 m 代表点、六项静态指标及审计 |
| `routing.py` | OneMap 请求、目的地核准、本机 token、响应分类、第一行程、SQLite 缓存与重试 |
| `pipeline.py` | 按稳定位置 ID 合并指标和路线，核对时段/目的地，保留未知 |
| `mcda.py` | 固定 P5/P95、标准化、偏好/约束校验、可行点贡献、区域资格与排名 |
| `experiments.py` | 四情景、Dirichlet、OAT、上限/资格及三组空间对照，保存逐次参数和结果 |
| `artifacts.py` | 表格读取、确定性结果包与版本元数据 |
| `settings.py` | 七指标顺序、方向、四权重、出发时刻、方法版本 |
| `cli.py` | 分段命令及错误状态 |
| `report.py` | 数据准备证据页 |
| `result_report.py` | 从保存结果生成中英文离线结果页，图内文字随语言切换 |
| `route_audit.py` | 路线复核计划、证据绑定及摘要 |
| `__main__.py`、`__init__.py` | 包入口与初始化 |

先看懂公式，再读 `mcda.py`；要核计数/采样看 `spatial.py`；改路由前先读处理文档的特殊情况。

用 `.\.venv\Scripts\python.exe scripts/render_result_pages.py` 重新生成两种语言的真实结果页。该命令只读取冻结的准备数据、正式评分与实验结果，绘制图表并写入 HTML，不新增路由请求、不重算 MCDA。中文文件为 `outputs/GE5219_MCDA_真实结果.html`，英文文件为 `outputs/GE5219_MCDA_Actual_Results_EN.html`；二者均已包含在完整交接包内，可离线打开。

## 3. 安装与默认完整运行

Python 3.11 以上；在**解压后的完整包根目录**执行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pip install jupyterlab ipykernel nbclient nbformat
.\.venv\Scripts\python.exe -m ipykernel install --user --name ge5219 --display-name "GE5219"
.\.venv\Scripts\python.exe -m jupyterlab
```

打开中文 `_zh.ipynb` 或英文 `_en.ipynb`，选择对应环境。macOS/Linux 的执行文件是 `.venv/bin/python`。已装全依赖的 GIS 环境也可使用；核验日志记录实际 Python 版本。库版本不同可能影响哈希或绘图，应保留原快照并解释差异。

三个开关默认均为 False：`RUN_PREPARE`、`RUN_API`、`RUN_FULL_EXPERIMENTS`。默认 Run All 仍会读取真实原始 GIS/CSV 与来源哈希，重组七维矩阵，重拟合并核对 A 标准化，重算正式基线、四情景、三空间臂、40/60 分钟和三资格门槛，共核对十三份已保存结果包。Monte Carlo 重生 1,000 组权重、从 241,000 行保存名次重算频率/分位数；**默认没有重跑 1,000 次全部 MCDA**。OAT 核对 84 组权重和 77 个相邻区间。末尾检查冻结文件未被改写。

执行 `scripts/execute_handover_notebooks.py` 可用两个干净内核运行并保存输出与 `outputs/audits/notebook_execution_check.json`。只克隆 GitHub 而没有完整数据时，不可能凭空重算。

## 4. 有意识地开展新运行

```powershell
.\.venv\Scripts\python.exe -m ge5219 prepare --data-root raw_data --output outputs/new_version/prepared
.\.venv\Scripts\python.exe -m ge5219 status --prepared outputs/prepared --routes outputs/routes.csv
.\.venv\Scripts\python.exe -m ge5219 score --prepared outputs/prepared --routes outputs/routes.csv --normalization outputs/normalization-v1.json --scenario balanced --output outputs/new_score
.\.venv\Scripts\python.exe -m ge5219 experiments --prepared outputs/prepared --routes outputs/routes.csv --normalization outputs/normalization-v1.json --output outputs/new_experiments
```

`score` 可额外接收 `--weights`（七项非负重要度，逗号分隔）、`--max-commute-min`、`--sample-set A|B` 和 `--group-by area_id|cluster_id`。具体以 `--help` 为准；数据变化时不要绕过标准化版本检查。

打开可选 prepare 会写到 `outputs/notebook_recomputed/prepared`；可选 API 分支只查**一个试点**，不是全量路由，会另存 pilot 缓存。完整新批次需用 `route` 命令显式传准备目录、目的地、缓存、输出和请求预算。历史日期之后可能不能查询；改日期就另建场景，不偷偷替换旧快照。可选完整实验写到 `outputs/notebook_recomputed/experiments`，可能需数分钟；默认执行审计不能证明这些关闭分支已运行。

## 5. 下游交接四件套

`point_scores.csv`、`area_scores.csv`、`top5.csv`、`result_metadata.json` 要一起取；用位置/区域 ID 关联，核对同一 `result_id`、数据版本、目的地、时段和实际权重。原值/标准化值在点表，不全在 Top 5 汇总表。

无路线、覆盖不足、没有合格区域、非法输入都要显示，不能补零或自动放宽。网站/Agent 的端到端联调与接收组员在另一环境的复现，仍是后续验收。
