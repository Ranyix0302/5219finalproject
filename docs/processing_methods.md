# Processing methods / 处理方法

# English: from source deliveries to interpretable results

Revision: 19 October 2026. The main English handbook supplies full statistics, formulas and worked examples. This document follows the processing order and distinguishes successful computation from certification of the source data.

## 1. Preserve and audit the source deliveries

`raw_data/` retains all 176 original files, including ZIPs and extracted contents, totalling 625,191,511 bytes. Every file was SHA256-checked against the supplied originals. A's GDB and B's merged housing CSV are overlapping deliveries, not independent sets to concatenate again. Preserve leading-zero postcodes, source keys, stable internal building/location IDs and source housing categories. From 96,977 records, hold out 214 records in 107 unresolved cross-source postcode groups, leaving 96,763 source-classified candidate records. Do not deduplicate different postcodes solely by coordinate coincidence or assume a postcode establishes unique building identity.

## 2. Geometry, units and sampling

Repair invalid polygons in derived copies and measure distances/buffers in EPSG:3414. Use WGS84 for API requests and map exchange. Subzones do not substitute for a residential land-use mask. Within each Subzone, connected components of building pairs at most 150 m apart create 384 analysis clusters, including 44 singletons. Chaining is allowed; these are not certified housing-estate boundaries.

The grid has a fixed (0,0) origin and 400 m cells. For each occupied cell × Subzone intersection, select the actual residence nearest the cell centre, with stable-ID ties. A has 2,176 locations. Add one real residence to each of 20 uncovered clusters, making B=2,196. Sampling is not based on high amenity scores. Membership is retained for every candidate record, but campus routes are measured at the sampled locations only.

## 3. Define the facility units before calculating indicators

Four unopened Marina South exit records are excluded from 613 source rail exits, leaving 609; the remaining exits have not all been individually certified. Bus counts use distinct source stop units from 5,205 records. Evidence-based service-address rules consolidate supermarket/clinic licences while retaining licence-to-site mappings and unresolved units: 440 supermarket locations and 1,186 clinic locations. Seven of 462 park polygons are provisionally excluded using the source N_RESERVE flag; they must not be described as seven legally designated nature reserves. Fifty-two source centroids lie outside their own polygon, so the indicator uses polygon distance, zero inside. This avoids that centroid problem but still does not identify an entrance or prove public access.

Rail and library indicators are nearest straight-line metres. Bus and supermarket supply are counts within 800 m; clinic supply within 1,000 m; park proximity is minimum point-to-polygon distance. There is no measurement of service frequency, capacity, opening hours, actual walking networks or a complete rent indicator. Radius choices are explicit working assumptions that need behavioural justification.

## 4. OneMap: three special cases that must survive the handover

The scene is NUS AS8's reviewed ground-arrival proxy at 08:00 on 19 October 2026, Singapore time. A TRANSIT request is made, but the production variable is precisely the first returned `itinerary.duration/60`. Cache identity includes origin, destination, scene and adapter. Success, no route, authentication, rate-limit, parse and temporary failures have distinct states. The frozen batch has 2,190 Success and six NoRoute responses across 2,196 origins. NoRoute remains unknown; it does not prove real-world inaccessibility.

1. **A TRANSIT request may return walking only.** Four of the twenty valid reviewed cases do so. Clementi West is about 2,072 m and 24.85 minutes. A successful response does not establish that a bus or train is boarded.
2. **maxWalkDistance=1,000 does not guarantee a hard walking limit.** Five valid reviewed cases have a walking leg above 1,000 m while `walkLimitExceeded=false`. There are six overall concern cases, not six long-walk cases. A genuine product constraint needs explicit returned-leg checks and a separately declared version.
3. **Itinerary duration may omit the initial scheduled wait.** A Sembawang Straits itinerary starts at 08:12:45 and arrives at 10:03:31: itinerary duration is 110.77 minutes, but requested-08:00-to-arrival is 123.52. Sunset Way gives 16.93 versus 23.17 minutes. Do not relabel the current field as full elapsed time without recalculation.

The 21 AI-assisted desktop cases comprise twenty valid itineraries plus one unavailable response: fifteen acceptable and six retained concerns, with zero independent-provider records. AS8 is a building ground-arrival proxy, not a verified exact door, indoor route or field observation. Changes to timing or mode semantics require a new adapter/cache/data version and comparison, rather than overwriting the frozen scores. Tokens are supplied through the local environment only.

## 5. Assemble, normalize, score and experiment

Join on location ID, checking destination, time and version; preserve raw values and route statuses. Fit each indicator's P5/P95 on finite A observations, clip, and map benefits forward/costs in reverse to 0–1. Invalid/constant ranges raise an error; missing values stay missing. All preference and B comparisons use the frozen A parameters.

Normalize nonnegative importance inputs by their positive sum. The default is balanced weights with no commute cap. Optional hard constraints use raw minutes. Only seven-dimension-valid, constraint-satisfying points receive scores and seven contributions. Area eligibility needs at least 90% valid/planned and 50% verified-feasible/planned. Average feasible-point scores and contributions over the same points; flag fewer than three valid points. Sort by unrounded score, then mean raw commute, rail distance and stable ID.

Saved experiments include four scenarios, 1,000 Dirichlet(50×balanced) draws, 84 OAT settings, 40/60-minute caps, 25/50/75% qualification rules and three spatial arms. Spatial comparisons fix balanced weights, a 60-minute cap and A normalization. A/Subzone→B/Subzone isolates supplementary sampling; B/Subzone→B/cluster changes aggregation on the same locations. MC tests the selected preference distribution; OAT locates tested intervals; different units require common-location/building-set overlap. None establishes conceptual validity.

## 6. Outputs, acceptance and open decisions

Deliver all four bundle files, parameters, data/result IDs, planned denominators and sample warnings. The complete package includes clean-kernel notebook evidence; default execution analyses saved MC ranks instead of claiming to rerun all 1,000 scoring simulations. See the handbook for complete arithmetic and interpretation.

Priority discussions are sparse-sample exclusion/resampling, a new commute definition, park categories/access, the 107 postcode groups and unresolved addresses, behavioural radius evidence and redundancy, cluster chaining/display, and website/Agent acceptance. Other campuses, actual walking networks, park entrances, 250/500 m routing, distance decay, and independent/field route validation remain uncompleted extensions.


# 中文：从原始交付到可解释结果

更新：2026-10-19。详细定义、实际统计、公式与逐步算例见本语言主说明。这份文档用于按处理顺序检查交接，不把“程序跑通”当成“所有数据都已认证”。

## 1. 原始交付只读，先查来源

`raw_data/` 原样保留 176 文件，共 625,191,511 bytes；逐文件 SHA256 与交付源一致。A 的 GDB 与 B 已合并住宅表不是两套独立住宅，不能再次相加。保留邮编前导零、来源 ID、内部稳定 building/location ID 和住宅类别。96,977 条中 107 个跨源邮编冲突组涉及 214 条，暂不进入候选，留下 96,763 条来源分类记录。不同邮编共址不能仅凭坐标盲删；邮编也不是已验证的万能唯一键。

## 2. 几何、区域与采样

在派生副本修复无效面，统一 EPSG:3414 后测距/缓冲；API 和网页才使用 WGS84。Subzone 边界不是住宅掩膜。每个 Subzone 内，距离不超过 150 m 的建筑以连通分量组成分析簇，允许链式连接；384 簇、44 单点簇，不能叫真实小区。

固定网格原点 (0,0)、边长 400 m。每个有住宅的“网格×Subzone”选离格中心最近的真实住宅，稳定 ID 打破同距，得 A 的 2,176 点。为 20 个漏簇各补一个真实住宅点形成 B 的 2,196 点；不按想要的指标分数挑点。每栋住宅归属有记录，但通勤只对这些采样位置测量。

## 3. 设施规则先于指标

613 个轨道出口排除 Marina South 的 4 个未开放记录，保留 609；不声称其他出口逐项认证。公交按 5,205 个来源站点的稳定站点单位去重计数。超市/诊所按有证据的地址/服务位置规则分组，保留牌照与位置映射和未解决单元；得到 440 个超市位置、1,186 个诊所位置。462 个公园面暂排除 7 个 N_RESERVE 源标签面，保留 455；这不是“7 个法定自然保护区”。原中心点有 52 个在自身面外，实际用面距离，园内为零，仍不表示入口或可进入。

最近轨道/图书馆用直线米数；公交/超市取 800 m 内个数；诊所取 1,000 m；公园为点到面最短距离。没有线路频率、服务容量、开放时间、真实步行路网或完整租金指标。半径是明确工作假设，不能以设施密度或算分结果替代行为依据。

## 4. OneMap：三个必须保留的特殊情况

场景为 NUS AS8 的地面到达代理，2026-10-19 08:00 新加坡时间。请求为 `TRANSIT`；生产变量固定取第一条 `itinerary.duration/60`。同起终点/场景/适配器复用缓存，成功、无路线、鉴权/限流/解析/临时错误分别记录。2,196 次已有请求得 2,190 Success 和 6 NoRoute；NoRoute 保持未知，不能说真实世界没有交通。

1. **TRANSIT 也可能返回纯步行。** 20 个有效复核例中 4 个纯步行；Clementi West 约 2,072 m、24.85 分钟。不能将所有返回值称为乘公交/地铁分钟。
2. **maxWalkDistance=1,000 不保证返回行程符合硬上限。** 复核有 5 个有效个案出现单段步行超过 1,000 m 且 `walkLimitExceeded=false`；不是把 6 个关注个案都称长步行。若产品要硬约束，应另判返回步行段并明确新版本规则。
3. **duration 可能不包含初始排程等待。** Sembawang Straits 08:12:45 开始、10:03:31 到达，行程 110.77 分钟，但从请求 08:00 到到达是 123.52 分钟；Sunset Way 则为 16.93 与 23.17 分钟。应按变量真实定义解释，不能直接重命名为完整 elapsed time。

共 21 个 AI 辅助桌面个案为 20 有效+1 无行程，15 可接受、6 保留关注，独立提供者记录数为 0。AS8 是建筑地面到达代理，非精确门口/室内、非实地验证。改变通勤语义需要新适配器/缓存/数据版本和对照，不能覆盖冻结分数。新 token 仅由本机环境提供。

## 5. 矩阵、标准化、评分与实验

按 location_id 合并，核对目的地/时间/版本；六项静态值与路线状态保留原始证据。A 各指标有限观测拟合 P5/P95，截尾后益型正向、成本反向到 0–1。范围无效/常数报错复查，缺失不补零；情景/B 样本沿用 A 参数。

非负重要度除以总和得到权重，默认均衡、无通勤上限。可选硬约束在原始分钟上应用。只有七维有效且满足约束的点有分数与七项贡献。区域有效覆盖≥90%、已验证可行/计划≥50% 后，取可行点均分及同一批点平均贡献；有效点<3 显著提示。排序使用完整精度，之后依原始通勤、轨道距离和稳定 ID。

四情景、1,000 次 Dirichlet(50×均衡)、84 OAT、40/60 分钟、25/50/75% 资格及三臂空间已保存逐次结果。空间臂固定均衡、60 分钟和 A 参数，用 A/Subzone→B/Subzone 隔离补样，再用 B/Subzone→B/cluster 看聚合。MC 只测试偏好分布；OAT 只得到测试区间；跨单位用共同位置/建筑集合比较地理范围。它们都不能证明指标在概念上合理。

## 6. 输出、验收与待讨论

每次交付完整四件套、参数、数据/结果 ID、资格分母与样本警告。完整包有干净内核 notebook 运行记录；默认运行分析保存 MC 名次，不声称再次执行全部 1,000 次 MCDA。详细算例与如何解读结果见主说明。

优先决定：低样本是否补样/另设门槛；通勤语义是否另建版本；455 面类别/开放性、107 组邮编及未解决设施地址；指标相关性与半径依据；150 m 链式聚类的展示；网页/Agent 接口验收。多校园、网络步行、公园入口、250/500 m、distance decay 与独立/实地出行验证仍未完成。
