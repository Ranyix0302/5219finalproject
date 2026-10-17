# GE5219 MCDA 实施结果与交接

日期：2026-10-17。此文是运行与结果笔记，供你和组员核查、联调与自行撰写报告。

## 先打开什么

- `GE5219_MCDA_真实结果.html`：四偏好情景、40/60分钟、七项贡献、地图、1,000次扰动、OAT和三组空间对照，离线可用。
- `GE5219_MCDA_路线桌面复核.html`：逐例路线、时刻、几何和关注事项。
- `GE5219_MCDA_交接包.zip`：代码、已计算数据快照、路由缓存、正式结果及全部实验记录。

本地源码：`C:/Users/SatelluS/dev/5219finalproject`。仓库当前分支为main；交接包附本地提交版本。原始A/B文件未修改，API凭证不在包中。

## 正式基线

NUS AS8地面到达代理，2026-10-19 08:00 Asia/Singapore；原400 m样本A；Subzone；均衡权重；默认无通勤上限。2,196个起点已全部查询，2,190条成功、6条NoRoute；A中2,170/2,176点有效。239/241个Subzones达到90%有效覆盖与50%计划样本已验证可行门槛。

|   排名 | Subzone       |     分数 |   计划样本 |   有效样本 | 支持有限   |
|-------:|:--------------|---------:|-----------:|-----------:|:-----------|
|      1 | PEOPLE'S PARK | 0.913982 |          1 |          1 | True       |
|      2 | CHINA SQUARE  | 0.879429 |          1 |          1 | True       |
|      3 | CHINATOWN     | 0.867704 |          6 |          6 | False      |
|      4 | TANJONG PAGAR | 0.844446 |          2 |          2 | True       |
|      5 | BOAT QUAY     | 0.831475 |          2 |          2 | True       |

**4/5个入选区域只有1–2个有效样本。** 这些结果符合已批准规则，但不能解释为全区每栋住宅都优越或高置信结论。无路线/技术失败从未补零；ONE TREE HILL和SENTOSA因有效覆盖不足未进入基线候选排名。

数据版本：`4dd2fff167c585379bfdd69dd49989ab2b90503f0a78c8eabd5d2dbd282db864`。
默认结果ID：`mcda-7541f705e66a7e1095a13b60`。
路线快照SHA256：`737f54b62bd2ee3188027c418a5f12ad4b90c3d3865e960296bf9ab375cbb0f5`。

## 实际完成的实验

- 四种偏好情景，均A/Subzone、无上限；成对Top5 Jaccard为0.429–0.667，全239个共同合格区域Spearman为0.788–0.944。权重会改变排名，不能笼统称完全稳健。
- **1000次**Dirichlet权重扰动，seed=42、κ=50.0；每次7个权重与全部区域排名均保存。
- 84组OAT目标权重，0.05–0.60步长0.05，另存77个相邻切换区间；它们不是精确临界点。
- 40/60分钟功能检查，固定60分钟下25/50/75%计划样本可行门槛对照。
- 三组空间臂固定均衡、60分钟和A标准化参数：

| 方案      |   区域总数 |   合格区域 | Top5                                                                                                                                                                                                                                 |
|:----------|-----------:|-----------:|:-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| A_subzone |        241 |        167 | PEOPLE'S PARK / CHINA SQUARE / CHINATOWN / TANJONG PAGAR / BOAT QUAY                                                                                                                                                                 |
| B_subzone |        241 |        167 | PEOPLE'S PARK / CHINA SQUARE / CHINATOWN / TANJONG PAGAR / BOAT QUAY                                                                                                                                                                 |
| B_cluster |        384 |        276 | PEOPLE'S PARK · analysis cluster 39fc69d26fca / TANJONG PAGAR · analysis cluster df3846d8096e / PEARL'S HILL · analysis cluster 3f0b940407d7 / CHINATOWN · analysis cluster 1064ecff3b71 / CHINATOWN · analysis cluster c03a99682846 |

A/B Subzone补点比较Top5 Jaccard：1.000。
B按Subzone/cluster推荐的共同位置集合Jaccard：0.286；两者分别覆盖13和5个计划位置。单位尺度不同，位置/建筑重叠低不能单独证明模型不稳健或cluster更好。

### 扰动中最常入选的区域

| Subzone          |   selection_frequency |   rank_median |   rank_p05 |   rank_p95 |
|:-----------------|----------------------:|--------------:|-----------:|-----------:|
| PEOPLE'S PARK    |                 1.000 |         1.000 |      1.000 |      1.000 |
| CHINATOWN        |                 1.000 |         3.000 |      2.000 |      3.000 |
| CHINA SQUARE     |                 0.998 |         2.000 |      2.000 |      3.000 |
| TANJONG PAGAR    |                 0.901 |         4.000 |      4.000 |      6.000 |
| BOAT QUAY        |                 0.602 |         5.000 |      4.000 |      8.000 |
| PEARL'S HILL     |                 0.174 |         7.000 |      5.000 |     10.000 |
| CLARKE QUAY      |                 0.131 |         7.000 |      5.000 |     10.000 |
| CLEMENTI CENTRAL |                 0.065 |        11.000 |      5.000 |     20.000 |
| CITY HALL        |                 0.064 |         9.000 |      5.000 |     13.000 |
| HOLLAND DRIVE    |                 0.046 |        14.000 |      6.000 |     30.000 |

频率仅针对已声明的权重扰动分布，不是居民选择概率、数据准确率或少样本置信度。原本不合格区域的入选频率为0，未知名次仍保留空值。

## 证据与边界

117项测试、mypy、ruff通过；Standards与Spec独立审查最终0未解决问题。2,170个有效点及241个区域的独立算术核对最大差2.22e-16；同输入重跑四份核心结果逐字节一致。

31个真实静态/聚类个案已抽查，并修复医院两项服务缺楼层字段时被合并的问题。诊所位置1,185→1,186，30点计数+1；规则进入数据版本。详见`docs/static-data-spot-check.md`。

21例独立AI辅助桌面路线审阅包括20条有效路径和1无行程响应；15可接受、6保留关注。同一OneMap提供者重查和独立桌面检查，不是独立提供者时间比较或实地计时。每条审阅、生产快照、冻结计划及摘要均可用hash关联。

**通勤变量是OneMap首条行程duration。** 它可能返回纯步行方案，可能不含08:00至行程开始的初始排程等待；maxWalkDistance=1000不保证每条返回步行段都≤1000 m。没有在看到结果后默默替换路线、删掉长步行案例或改变变量。AS8是地面到达代理，不是测绘入口或室内终点。

住宅用途、107对邮编冲突、设施地址、交通运营和绿地类别/开放仍需组员核准。`production_ready=false`保留；分数可解释和算术正确不等于来源已全部认证。候选不是当前租房供应清单；模型没有测量租金、真实步行网络、公园入口、公交频率或室内到达。

## 给地图与Agent组员的接口

每次推荐只用同一bundle的`result_metadata.json`、`point_scores.csv`、`area_scores.csv`、`top5.csv`，以result_id关联；主结果在`outputs/score`，其他情景在`outputs/experiments`。不能混用不同权重或上限的表。

网页选择器只切换已保存情景；40/60分钟仅有均衡版本。前端不得自行补缺失、重定义公式、把分数当概率或编造其他校园结果。新权重通过Python核心重新生成独立bundle：

```powershell
.\.venv\Scripts\python.exe -m ge5219 score --routes outputs/routes.csv --scenario campus_first --output outputs/custom-campus
.\.venv\Scripts\python.exe -m ge5219 score --routes outputs/routes.csv --max-commute-min 60 --output outputs/custom-cap60
```

解压交接包后从包根目录安装`pip install -e ".[dev]"`，已有输出可直接查看。重算评分不需要token；新增路线才需要本机环境变量。重跑原始prepare还需本项目原始data目录。CLI与数据契约见README、`docs/interfaces.md`。

## 你的下一步

1. 与A核准107对邮编、医院与异常超市单元、455个暂纳入绿地的类别；与B核准保留站点运营和通勤语义。
2. 用真实网页和图表与组员联调result_id、低样本警示、覆盖/可行比例及未支持校园提示。
3. 据这些结果自行撰写最终报告与个人贡献，披露AI用于代码、图表、测试和桌面复核的范围；不要把桌面检查改写为人工实地验证。
4. 优先讨论小样本推荐、初始等待和纯步行方案对解释的影响；若要改方法，另建版本与对照，不覆盖当前冻结基线。
