# GE5219 MCDA handover guide (English)

Document date: 19 October 2026. This guide is written for teammates who have not used MCDA before and can be read on its own. A complete [Chinese version](../handover_zh/README.md) is also available. “Actual result” means a value checked against the frozen files in this package. Invented teaching examples are explicitly labelled.

**The deliverable is a reproducible, explainable baseline for comparing residential locations.** It asks: under the delivered housing records, one specified NUS AS8 routing scenario, seven indicators and declared preferences, which official Subzones have the highest average score among verified feasible representative locations? It does not establish current rental availability, rent, household capacity or the operation of every facility. It therefore cannot directly answer which available dwelling a student should rent today.

## 0. Read the calculation in plain language

Measure seven conditions at each representative residential point. Put them on one fixed 0–1 scale. Add their weighted contributions. Exclude points that fail hard constraints. Aggregate the remaining points to official Subzones. Sensitivity analysis then asks how recommendations change when preferences, caps or spatial units change.

- **Does this version use distance decay?** No. Bus stops, supermarkets and clinics use fixed-radius counts. Rail/library indicators use nearest straight-line distance. Parks use straight-line distance to polygons. Campus uses the first OneMap itinerary duration. Decay remains a possible extension.
- **What are P5 and P95?** They are values near the 5% and 95% positions after one indicator's valid observations are sorted. They are percentiles of raw measurements, not preference weights or scores of 5 and 95.
- **What does clipping do?** For score calculation only, values beyond the two boundaries are treated as the boundary values. The bus P95 is 48, so 57 stops is treated as 48 for scaling and receives 1. The original 57 and its residential record remain available.
- **What does Monte Carlo ask?** Would the recommendations remain similar if people assigned somewhat different importance to the seven conditions? This experiment draws 1,000 legal weight vectors and reranks each. It does not resample residences or request new journeys.
- **What does OAT ask?** If campus importance increases step by step, which areas enter or leave the Top 5? The other six weights give up their share proportionally so that all weights still sum to 1.
- **How can the next developer call it?** Existing Python and command-line interfaces support scoring, custom importance and a commute cap. Python also exposes eligibility thresholds and Top k. See the [integration guide](interfaces.md). There is no deployed HTTP service or arbitrary facility-distance constraint.

Each figure now follows the paragraph it explains. Its caption distinguishes actual results from teaching examples and explains the legend, axes and reading limits.

## 1. Start here: files and the frozen baseline

Open the [actual results page in English](../../outputs/GE5219_MCDA_Actual_Results_EN.html), or the [Chinese results page](../../outputs/GE5219_MCDA_真实结果.html), then the [route desktop review page](../../outputs/route_audit_v2/route_audit.html). Both complete packages include both results pages and their charts. The English page translates the interface, explanations, chart titles, axes and legends while retaining the same saved scores, rankings and result IDs. Its selectors display saved scenarios without recalculating scores. The [Notebook directory](../../notebooks/) supports a step by step reading of the calculation, and the standard package's [documentation entry](../../doc.html) brings the reading links together. Source result tables are in the [baseline](../../outputs/score/), [experiments](../../outputs/experiments/) and [prepared data](../../outputs/prepared/) directories.

| Item | Frozen value and interpretation |
| --- | --- |
| Analysis version | `mcda-v1.0` |
| Preparation and route retrieval | 17 October 2026; this is not the update date of every original source layer |
| Requested journey scenario | `2026-10-19T08:00:00+08:00`, Asia/Singapore, `TRANSIT` query |
| Destination | `NUS_AS8`, latitude 1.296086762317243, longitude 103.7723482217768; building ground arrival proxy |
| Formal recommendation unit | Five distinct official Subzones; analysis clusters are an additional spatial comparison |
| Default sample and preferences | Original 400 m sample A, balanced weights, **no commute cap** |
| Default eligibility | At least 90% valid coverage, verified feasible/planned share at least 50%, and at least one feasible point |
| Dataset version | `4dd2fff167c585379bfdd69dd49989ab2b90503f0a78c8eabd5d2dbd282db864` |
| Route snapshot SHA256 | `737f54b62bd2ee3188027c418a5f12ad4b90c3d3865e960296bf9ab375cbb0f5` |
| Default result ID | `mcda-7541f705e66a7e1095a13b60` |

For example, the page's “60 minute” option is a separately saved scenario. Its Top 5 must not be combined with point scores from the uncapped baseline. Even once 19 October has arrived, the saved values remain scheduled itineraries retrieved on 17 October. **They are not observed commutes.**

## 2. What the original A and B deliveries contain

Contributor A supplied housing and facility GIS layers. Contributor B supplied an already merged housing table, rail exits, bus stops and a few routing demonstrations. These original A/B deliveries are different from the **sample A and sample B** created by this project later in the workflow.

A's Dwelling and HDB layers total 96,977 records. B's merged residential table also has 96,977 records and already contains those homes. Appending A's residences again would duplicate the input. The implementation starts from B's frozen table, maps A's layer, object ID, six digit postal code and checksum information, and retains B's coordinates. There are zero source mapping failures in the saved preparation.

| Source housing class | Original records | Included candidate records | Interpretation |
| --- | ---: | ---: | --- |
| HDB | 13,436 | 13,329 | HDB stays a distinct class; an HDB point or polygon is not automatically an estate |
| Landed | 73,041 | 72,934 | Many address records do not imply many student rental opportunities |
| Non-Landed | 9,897 | 9,897 | Not silently renamed fully verified condominiums |
| EC | 603 | 603 | Retained as a separate source class |
| Total | 96,977 | 96,763 | 214 records are held out pending conflict adjudication |

The 96,977 records have 96,870 unique postal codes. **107 postal code groups each contain two conflicting records across the housing sources, involving 214 records.** Both sides are held out until A/B can resolve them; the model does not assume that either source has the correct coordinate. Thus `96,977 − 214 = 96,763`. Holding a record out does not prove it is invalid. The actual disposition is recorded in [postal_conflicts.csv](../../outputs/prepared/audits/postal_conflicts.csv) and [held_out_residences.csv](../../outputs/prepared/audits/held_out_residences.csv).

**Coincident coordinates are not sufficient grounds for deletion.** Different postal addresses can share a geocoded building representative point; the real source includes a coincident group with 38 residential records. Such records can share a route cache entry without being declared one address, household or duplicate dwelling. An internal `building_id` identifies a versioned source record and `location_id` identifies an analysis location. Neither certifies a one to one relationship with distinct physical buildings.

A and B also used different point construction methods. Across the full source mapping, the coordinate difference has a P95 of about 9.08 m and a maximum of about 83.43 m. Overwriting B's positions with A's coordinates while retaining B's previous distances would mix measurement meanings within a row. This version retains B's positions, audits their differences and recalculates the static measures from source facilities. B's original campus examples cover only **five distinct residences to NUS AS8**, not an island wide commute matrix; additional export formats are not additional independent journeys.

Those five older demonstrations actually span 58.28–97.32 minutes, all above 40 minutes. They cannot establish that no residence anywhere can meet 40 minutes. The complete queries for the current 2,196 frozen origins support this version's commute column. Roughly three quarters of the source housing records are Landed, which does not imply three quarters of student rental supply.

Residential use still relies largely on the source classification. The project has not proved complete housing coverage, current occupation, student rental suitability or availability. It has not treated planned URA residential land as an existing dwelling inventory. Successful data processing does not certify all original sources.

## 3. Geometry, facilities and service addresses

All metric distances, radii and clustering use Singapore's projected **EPSG:3414** coordinates. Latitude/longitude and display GeoJSON use **EPSG:4326**. Differences in geographic degrees must not be interpreted as metres. Six invalid Subzone polygons and two invalid park polygons were repaired in derived copies, with before/after geometry and area audits. Residential assignment first prefers strict polygon interiors; boundary or overlapping ties use the lexical official code and retain every intersecting code in the audit. No current candidate lies outside all Subzones. The general rule retains an outside point as outside rather than attaching it to the nearest polygon.

Facility counts require a declared unit. The 1,192 source clinic licences become 1,186 service sites under the saved address rule; 440 supermarket source records remain 440 sites. A service site is a normalised **postal code + street address + floor + unit**, rather than a licence or a coordinate.

Teaching address example: two licences with the same complete `123456 / EXAMPLE ROAD / 02 / 03` address can represent one service address. Unit `02-04` is another address even if its map coordinate is identical. Missing floors/units, a placeholder unit `0`, or a suspicious long numeric unit cannot prove shared service identity. Those records remain separate, licence keyed unresolved sites; a building name is not used to guess a floor or unit. A group coordinate spread above 20 m triggers review. The lexically first licence supplies a deterministic representative coordinate; 20 m is a review threshold, not an accuracy certificate.

The frozen rule is `complete-service-address-v2`. There are 59 unresolved retained clinic sites and 99 unresolved retained supermarket sites. The 116 supermarket records flagged for address review count something different from unresolved sites. Retained ambiguous sites are not certified distinct, operating opportunities. A real static review corrected an unsupported hospital merge when floor information was missing, moving the older clinic calculation from 1,185 to the current 1,186. The frozen dataset version includes that repair. The [clinic mapping](../../outputs/prepared/audits/clinic_licence_site_mapping.csv) and [supermarket mapping](../../outputs/prepared/audits/supermarket_licence_site_mapping.csv) retain the original licences.

Transport sources do not provide complete operation status. From 613 MRT/LRT exits, the partial review dated 17 October excluded four MARINA SOUTH MRT STATION exits identified as not open, leaving 609. MARINA SOUTH PIER is a different station. This exclusion changes none of the 2,196 selected locations' nearest exit distances, which does not justify ignoring the operation rule. The retained 609 exits and 5,205 bus stop points have not each been certified operational; temporary exit closures, frequencies, crowding and capacity are unmeasured. The [operation snapshot](../../outputs/prepared/transit_operation.json) records the evidence used then, not a live certification of today's entire network.

The park source has 462 polygons. Seven with the source flag `N_RESERVE=1` are excluded under the frozen rule, leaving 455 provisionally included polygons. Seven is a **source flagged polygon count**, not seven legally distinct nature reserves. Categories, corridors and public opening still require review. Of the original 462 park centroids, 52 lie outside their own polygon. Even an interior centroid is not an entrance. This model measures polygon proximity, with zero distance inside, which does not establish an accessible gate, legal entry, walking route or opening time. See the [spatial data notes](../spatial-data-notes.md) for the preparation rules.

## 4. How 96,763 housing records become representative locations

Querying a specified journey for almost 100,000 records would be costly. This baseline uses a fixed spatial sampling rule, without preselecting places by amenity score. A 400 m grid has a fixed origin `(0,0)` in EPSG:3414. Within every occupied **grid cell × Subzone**, it selects the actual housing record nearest the cell centre, using stable `building_id` for ties. A cell crossing a boundary can therefore contribute separate representatives to both Subzones rather than losing the smaller area. Original sample A contains **2,176 locations** across 241 official Subzones with candidate residences.

Clusters are constructed from all 96,763 candidate housing records, separately within each Subzone. An undirected edge joins two points at Euclidean distance `≤150 m`; connected components become analysis clusters, including singletons. There are **384 clusters, of which 44 are singletons**. These are research components, not verified housing estates, neighbourhoods or property boundaries.

Teaching chain example: if A is 140 m from B and B is 140 m from C, all three belong to one cluster even when A is 280 m from C. A “150 m cluster” therefore does not mean every member lies within 150 m of a centre. Long chains can span much greater distances. `extent_diagonal_m` is the diagonal of the projected axis aligned bounding box. It is a useful scale diagnostic, not an exact maximum pairwise distance or an estate boundary.

The actual largest cluster by membership is FRANKEL `BDSZ05_C_0fe53e56a96e`: 6,124 candidate records, a bounding box diagonal of about 3,619.64 m, and 34 representative points in both A and B. Long chain extent is a real feature of these data; 150 m is not a guarantee of a small cluster footprint.

A misses 20 clusters. Sample B adds one actual member nearest the mean member point of each missing cluster, giving **2,196 locations**. Selection occurs independently of facility scores and route success. It does not create a fictitious centroid dwelling or copy a representative score onto every building. Planned coverage of each cluster does not prove adequate representation of its internal variation. [analysis_locations.csv](../../outputs/prepared/analysis_locations.csv) saves `sample_A` and the selection reason; [clusters.csv](../../outputs/prepared/clusters.csv) records full member support.

## 5. What the seven indicators mean

MCDA means Multi-Criteria Decision Analysis. Here, it converts seven measurements with different units into a common direction and scale, then combines them using declared importance weights. The measurement definition matters before any arithmetic does.

Let `p_i` be a residential location, `d(p,q)` be Euclidean distance in EPSG:3414, and `1[condition]` be 1 when the condition holds and 0 otherwise. Source point sets are prepared under the frozen rules, and radius counts include their boundary.

| Indicator and field | Definition and direction | Everyday meaning and limits |
| --- | --- | --- |
| Campus itinerary, `campus_transit_min` | `t_i = first OneMap itinerary.duration / 60`, minutes; lower is better (cost) | Provider's scheduled itinerary to AS8 in the stated scenario; can be walking only and may omit initial scheduling wait; see section 11 |
| Rail exit, `rail_exit_euclid_m` | `r_i = min_q d(p_i,q)` over retained MRT/LRT exit points, metres; cost | Exit proximity; not a walking path, walking minutes or a guarantee of operation |
| Bus stops, `bus_stops_800m` | `b_i = Σ_q 1[d(p_i,q) ≤ 800]`, stop point count; higher is better (benefit) | Nearby stop points; not distinct routes, frequency, capacity or services to campus |
| Supermarkets, `supermarket_sites_800m` | `s_i = Σ_q 1[d(p_i,q) ≤ 800]`, service address count; benefit | Nearby shopping options; no price, size, opening time or stock measurement |
| Library, `library_euclid_m` | `l_i = min_q d(p_i,q)` over delivered library points, metres; cost | Nearest library proximity; no seats, booking, opening hours or network walking distance |
| Clinics, `clinic_sites_1000m` | `c_i = Σ_q 1[d(p_i,q) ≤ 1000]`, service address count; benefit | Nearby healthcare choices; no quality, price, student suitability or emergency capacity measure |
| Park, `park_proximity_euclid_m` | `g_i = min_{q∈included park union} d(p_i,q)`, zero inside, metres; cost | Geometric proximity to provisionally included green space; not entrance distance, public access rights or opening status |

The 800 m bus/supermarket radius and 1,000 m clinic radius are approved working parameters defining the neighbourhood in which an option counts. They are not behaviour calibrated optima. No student survey establishes that these are the best radii, or that a 1,000 m clinic catchment is better than 800 m. A road barrier, wall or waterway may lie between two nearby coordinates. A circle does not guarantee a traversable route or a particular number of walking minutes.

Teaching boundary example: a supermarket at 799 m or exactly 800 m counts as one; one at 801 m counts as zero. The threshold is reproducible but can magnify small coordinate errors near its boundary. Multiple radii and distance decay could be compared in a later version; they have not been run as part of the frozen baseline. A true zero count remains zero. If the entire facility source is unavailable, the measurement is unknown, not evidence that no facilities exist nearby.

**Separate two questions:** Euclidean/network distance specifies how distance is measured. Buffer/decay specifies how a facility contributes as that distance increases. Decay can also use Euclidean distance. A hypothetical rule that halves contribution every 500 m is shown below; 500 m is only a teaching assumption and was not used in the frozen indicators or experiments.

<!-- VISUAL: measurement -->

The actual raw distributions in A are below. Each column uses its available measurements among all planned locations. Six unavailable campus routes remain missing, so campus N is six smaller than static indicator N:

| Indicator | Observed N | Minimum | Median | Maximum |
| --- | ---: | ---: | ---: | ---: |
| Campus minutes | 2,170 | 4.85 | 55.49 | 116.90 |
| Rail exit metres | 2,176 | 15.33 | 535.71 | 3,619.76 |
| Bus stop count | 2,176 | 0 | 30 | 60 |
| Supermarket address count | 2,176 | 0 | 3 | 12 |
| Library metres | 2,176 | 0.42 | 1,367.10 | 4,782.15 |
| Clinic address count | 2,176 | 0 | 12 | 48 |
| Park polygon metres | 2,176 | 4.98 | 298.26 | 2,318.87 |

For example, bus counts span 0–60 with a median of 30; locations do not all have similar transport surroundings. The 0.42 m minimum library distance means two representative coordinates almost coincide, not a measured half metre journey from a home doorway to a library seat. The 4.85 minute campus minimum can be a walking only itinerary. No selected A point happens to lie inside an included park polygon, explaining its 4.98 m minimum without changing the rule that an interior point receives zero distance.

## 6. Normalisation: keep the same ruler across experiments

Minutes, metres and site counts cannot sensibly be added directly. For each indicator j, P5 and P95 are fitted to its **observed, finite, nonnegative values in sample A**, giving `L_j` and `U_j`. Campus minutes are observed only for `Success` routes. Static indicators use their own available observations; fitting does not first restrict every column to the subset with complete seven dimensional rows. P5 is a percentile below which approximately 5% of observed values lie; P95 is defined similarly.

| Indicator | Fixed P5 | Fixed P95 | Direction |
| --- | ---: | ---: | --- |
| Campus minutes | 28.125833 | 87.501667 | cost |
| Rail exit metres | 117.219198 | 1,552.803871 | cost |
| Bus stop count | 11 | 48 | benefit |
| Supermarket address count | 0 | 7 | benefit |
| Library metres | 385.542751 | 3,036.189039 | cost |
| Clinic address count | 1 | 30 | benefit |
| Park polygon metres | 32.246482 | 965.581336 | cost |

First clip the raw measurement: `x*_ij = min(U_j, max(L_j, x_ij))`. Then calculate:

- benefit: `z_ij = (x*_ij − L_j)/(U_j − L_j)`;
- cost: `z_ij = 1 − (x*_ij − L_j)/(U_j − L_j)`.

Every `z` is now better when larger. P5/P95 clipping limits the effect of extremes on the scale. Benefits above P95 all receive 1, as do costs below P5, so this intentionally loses tail distinctions. **A value of 1 means saturation on this declared scale, not perfect service, 100% satisfaction or a probability.** Raw values remain available.

For example, the real location below has 57 bus stops, above P95=48, so its bus score is 1. A count of 48 receives the same bus score as 57. Its 65.95 campus minutes become `1 − (65.95 − 28.125833)/(87.501667 − 28.125833) = 0.362970`. Missing, negative or nonfinite observations remain unknown. A failed route never becomes zero minutes. Undefined or constant P5/P95 bounds cause an error rather than a silently invented score.

**Think of two ends of a ruler:** for bus counts, 11 maps to 0 and 48 to 1. Values between them scale proportionally. Below 11 remains 0; above 48 remains 1. Campus minutes run in the opposite direction: approximately 28.13 minutes or less saturates at 1; 87.50 or more at 0. Clipping removes no residential rows and does not alter raw minutes used for 40/60-minute constraints. Linear interpolation can produce a percentile that is not one observed value.

<!-- VISUAL: normalization -->

These parameters are fitted once on A and held fixed for the four preference scenarios, Monte Carlo, OAT, commute caps, qualification thresholds and three spatial arms. Refitting on B, each new scenario or only feasible observations would change the ruler while supposedly testing one other change. Full precision and provenance are in [normalization-v1.json](../../outputs/normalization-v1.json).

## 7. A real seven dimensional example and the meaning of weights

The following values are **actual frozen measurements and output**, not invented teaching data. The point is HDB source record `R001186`, postal code `730517`, in WOODLANDS SOUTH: `location_id=LOC_BLD_000d4f886a7311338eff`, latitude/longitude `(1.43382994983641, 103.791679801798)`. It is a housing source representative, not a verified available rental listing.

| Indicator | Actual raw value | Actual z | Balanced weight | Actual contribution `w×z` |
| --- | ---: | ---: | ---: | ---: |
| Campus itinerary | 65.950000 min | 0.362970 | 0.25 | 0.090743 |
| Rail exit | 308.201051 m | 0.866966 | 0.15 | 0.130045 |
| Bus stops | 57 | 1.000000 | 0.10 | 0.100000 |
| Supermarket addresses | 4 | 0.571429 | 0.15 | 0.085714 |
| Library | 545.438591 m | 0.939677 | 0.10 | 0.093968 |
| Clinic addresses | 18 | 0.586207 | 0.10 | 0.058621 |
| Park polygon | 901.974842 m | 0.068150 | 0.15 | 0.010222 |
| Total | Raw values in different units are not added | — | 1.00 | **0.569312554** |

The uncapped point is valid and feasible; its exact saved score is 0.5693125535586673, the sum of its seven contributions. With either a 60 or 40 minute cap, 65.95 minutes makes it infeasible. Nearby libraries and many bus stops cannot offset a hard constraint. Raw measurements remain, but its contributions and score for that recommendation are empty.

<!-- VISUAL: contribution -->

The four declared preference vectors below each sum to 1. They are interpretable demonstration/working assumptions. **No AHP pairwise comparison, consistency ratio, student survey fitting or empirical preference estimation was performed.**

| Scenario | Campus | Rail exit | Bus | Supermarket | Library | Clinic | Park |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| balanced | 0.25 | 0.15 | 0.10 | 0.15 | 0.10 | 0.10 | 0.15 |
| campus_first | 0.40 | 0.20 | 0.10 | 0.10 | 0.05 | 0.05 | 0.10 |
| transit_first | 0.15 | 0.35 | 0.25 | 0.10 | 0.05 | 0.05 | 0.05 |
| lifestyle | 0.10 | 0.10 | 0.10 | 0.20 | 0.15 | 0.15 | 0.20 |

For user supplied importance values `a_j`, the core checks seven finite, nonnegative values, rejects booleans and an all zero vector, then normalises `w_j = a_j / Σ_k a_k`. The implementation divides by the maximum first to avoid overflow; this is mathematically equivalent. Importance `(5,3,2,3,2,2,3)` sums to 20 and produces the balanced vector. Weights express tradeoffs after normalisation; they are not a monetary value for one minute of travel. This version still requires all seven measurements even when one indicator has zero weight.

The point score is `S_i = Σ_j w_j z_ij`, with contribution `C_ij = w_j z_ij`. The weighted sum allows compensation: when no hard constraint is triggered, strengths can offset weaknesses. Correlated transport or city centre amenity indicators may also count related advantages more than once. The saved correlation figure can flag this concern but does not resolve conceptual overlap automatically.

**Read the correlation plot carefully:** each cell compares two columns across shared representative positions. Positive correlation means values tend to rise together; negative correlation means one tends to rise as the other falls. The legend spans −1 to 1. A larger raw value is not always better: larger distances are worse. Colour alone does not justify removing an indicator.

<!-- VISUAL: correlation -->

**Separate invented teaching example:** reduce the problem to two normalised indicators, “campus convenience” and “local services”, with hypothetical profiles X=(0.9,0.3), Y=(0.4,0.8). Weights (0.7,0.3) give X=0.72 and Y=0.52. Weights (0.3,0.7) give X=0.48 and Y=0.68. Only preferences changed, yet the ordering reversed. This two indicator example is neither a real residence nor an output of the seven indicator pipeline. The table above is the real example. [Teaching values and full raw statistics](../handover_shared/teaching_examples.json) explicitly distinguish them.

## 8. From points to Subzones: eligibility, averaging and ties

A point is `valid` only when all seven measurements are complete and its destination is supported. It is `feasible` when valid and, if a cap is enabled, its **raw campus minutes** satisfy `t_i ≤ cap`. Unqueried points, NoRoute responses and technical failures are unverified. They do not count as zero minute or automatically feasible journeys.

For an area with `N` planned locations, `V` valid locations and `F` feasible locations:

- `valid_share = V/N` measures coverage;
- `conditional_feasible_share = F/V` describes feasibility among valid points, and is undefined when V=0;
- `verified_feasible_share = F/N` measures verified feasibility among all planned locations.

Eligibility requires `V/N ≥ 0.90`, `F/N ≥ 0.50` and `F>0`. **The denominator is planned N.** Removing failed rows and substituting F/V would reward incomplete coverage. Teaching example: 20 planned points, 18 valid and nine feasible have 90% valid coverage and 50% conditional feasibility, but only 45% verified feasibility. The area fails the default 50% rule.

<!-- VISUAL: eligibility -->

Eligible areas are ranked by the **equal mean of feasible point scores**, `S_area = (Σ_{i∈F} S_i)/F`. Each area contribution is also the mean across feasible points. There is no household, population, dwelling unit or full building membership weighting. Two feasible scores of 0.8 and 0.6 average to 0.7; a third failed point is not inserted as a zero into that mean, but still counts in the coverage and eligibility denominator. An ineligible area can have a calculable mean; that does not entitle it to a rank.

Ties are resolved by score descending, feasible points' mean raw campus minutes ascending, mean raw rail exit distance ascending, then lexical `unit_id`. Only eligible units receive ranks. The model returns up to five distinct units and reports fewer if necessary. `limited_support = n_valid < 3` is a small sample flag, not an automatic exclusion.

The actual baseline has 2,170/2,176 valid A locations and 239/241 eligible Subzones. ONE TREE HILL has 4/5=80% valid coverage and SENTOSA 10/15≈66.7%; both fail the 90% coverage rule. They are not “zero score areas”. The formal Top 5 is:

| Rank | Subzone | Score | Planned / valid / feasible | Limited support |
| ---: | --- | ---: | --- | --- |
| 1 | PEOPLE'S PARK | 0.913982 | 1 / 1 / 1 | Yes |
| 2 | CHINA SQUARE | 0.879429 | 1 / 1 / 1 | Yes |
| 3 | CHINATOWN | 0.867704 | 6 / 6 / 6 | No |
| 4 | TANJONG PAGAR | 0.844446 | 2 / 2 / 2 | Yes |
| 5 | BOAT QUAY | 0.831475 | 2 / 2 / 2 | Yes |

**Four of the five selected areas have only one or two valid samples.** PEOPLE'S PARK's mean is the score of its sole representative. This does not prove that every dwelling, resident or available rental in that area has equivalent conditions. Candidate support and sample counts should accompany the score.

## 9. Four preferences and Monte Carlo weight uncertainty

All four fixed preference comparisons use A/Subzone, no commute cap and the same normalisation:

| Scenario | Actual Top 5 in rank order |
| --- | --- |
| balanced | PEOPLE'S PARK / CHINA SQUARE / CHINATOWN / TANJONG PAGAR / BOAT QUAY |
| campus_first | PEOPLE'S PARK / TANJONG PAGAR / CHINATOWN / CHINA SQUARE / HOLLAND DRIVE |
| transit_first | CHINA SQUARE / PEOPLE'S PARK / CITY HALL / BUGIS / CHINATOWN |
| lifestyle | PEOPLE'S PARK / CHINA SQUARE / CHINATOWN / BOAT QUAY / CLARKE QUAY |

For comparable units, `Jaccard = |intersection|/|union|` compares Top 5 sets. Pairwise Jaccard across the four scenarios is 0.429–0.667, while Spearman rank correlation over 239 jointly eligible areas is 0.788–0.944. Campus and transit preference Top 5 sets share three areas, giving `3/7≈0.429`. A fairly correlated overall ranking can still produce a changed recommendation list. The six pairs in [scenario_comparisons.csv](../../outputs/experiments/scenario_comparisons.csv) do not support a claim of complete robustness.

<!-- VISUAL: scenarios -->

Monte Carlo explores **1,000** random preference vectors near balanced: `w^(b) ~ Dirichlet(κ w_balanced)`, with `κ=50` and `seed=42`. Its parameter vector is `(12.5,7.5,5,7.5,5,5,7.5)`. Each draw has nonnegative weights summing to 1, with expected weights equal to balanced. Larger κ generally concentrates draws more tightly. Neither κ nor this preference distribution was estimated from real students. The seed makes the random sequence reproducible.

Every draw recomputes all area rankings and saves its weights and results. A selection frequency is `Σ_b 1[rank_b≤5]/1000`; median, P5 and P95 ranks summarise defined ranks, where smaller is better. Undefined ranks remain empty. Areas that were ineligible stay ineligible in a weight only experiment, with zero selection frequency and no invented rank zero.

| Subzone | Actual Top 5 frequency | Median rank | Rank P5–P95 |
| --- | ---: | ---: | --- |
| PEOPLE'S PARK | 1.000 | 1 | 1–1 |
| CHINATOWN | 1.000 | 3 | 2–3 |
| CHINA SQUARE | 0.998 | 2 | 2–3 |
| TANJONG PAGAR | 0.901 | 4 | 4–6 |
| BOAT QUAY | 0.602 | 5 | 4–8 |
| PEARL'S HILL | 0.174 | 7 | 5–10 |
| CLARKE QUAY | 0.131 | 7 | 5–10 |
| CLEMENTI CENTRAL | 0.065 | 11 | 5–20 |
| CITY HALL | 0.064 | 9 | 5–13 |
| HOLLAND DRIVE | 0.046 | 14 | 6–30 |

For example, BOAT QUAY enters the Top 5 in 602 of the 1,000 declared weight draws and its P5–P95 ranks span 4–8, showing a recommendation near the list's edge. PEOPLE'S PARK has frequency 1.000, meaning it always enters the Top 5. Its saved ranks show 991 first places and nine second places. Its rank P5–P95 of 1–1 therefore does not imply first place in every draw: a few tail results fall outside that interval. CHINATOWN likewise has frequency 1.000 but ranks mainly second or third. Frequency 1 does not itself imply first place, and high frequency does not remove limited sampling or source uncertainty. **Weight uncertainty is not data confidence.** These frequencies are not tenant choice probabilities, probabilities of true optimality, route accuracy or small sample confidence intervals. They do not simulate coordinate error, missing source facilities, operation changes or variation between travel days. The [frequency table](../../outputs/experiments/monte_carlo_frequency.csv), [drawn weights](../../outputs/experiments/monte_carlo_weights.csv) and [full ranks](../../outputs/experiments/monte_carlo_ranks.csv) preserve the experiment.

**Purpose and limits:** one balanced vector gives one shortlist. Monte Carlo changes all seven weights together to test dependence on that declared tradeoff. A frequency of 602/1,000 identifies an area near the shortlist edge under the tested preferences; it does not mean 60.2% of students should live there. Rank P5–P95 uses ranks from these simulations, whereas Section 6 uses raw minutes/metres for its percentiles. It is not a 90% confidence interval for a true optimal rank.

<!-- VISUAL: monte_carlo -->

## 10. OAT: which tested weight intervals change the list

OAT means “one at a time”. It assigns one target indicator j a weight `t` and proportionally reallocates the remaining total across the other six: `w'_j=t`; for `k≠j`, `w'_k = w_k × (1−t)/(1−w_j)`. The sum remains 1 and the other six weights keep their original ratios. Increasing campus from 0.25 to 0.35 multiplies every other weight by `0.65/0.75`, so rail falls from 0.15 to 0.13. Simply adding campus importance without reallocating the rest would change the total.

Each of seven indicators takes 12 target values `0.05,0.10,…,0.60`: **84 settings**. Each series has 11 adjacent intervals: **77 intervals**. Of these, **17 have a changed Top 5 set**: four campus, one rail, four bus, three supermarket, two library, two clinic and one park intervals.

Actual example: at campus weight 0.30, BOAT QUAY is fifth with score 0.821331. At 0.35, CLEMENTI CENTRAL becomes fifth with score 0.818988; the first four selected names stay the same. The endpoint Top 5 Jaccard is `4/6=0.666667`. This locates a change within the tested 0.30–0.35 interval; it does **not** solve an exact critical weight or establish that only one switch occurs inside the interval. Another real change from 0.05 to 0.10 replaces CLARKE QUAY with TANJONG PAGAR.

OAT still uses A/Subzone, no cap and fixed normalisation. Its seven paths do not cover the entire preference simplex. Evidence is in [oat_switch_intervals.csv](../../outputs/experiments/oat_switch_intervals.csv), [OAT weights](../../outputs/experiments/oat_weights.csv) and [OAT ranks](../../outputs/experiments/oat_ranks.csv).

**How it differs from Monte Carlo:** Monte Carlo varies weights jointly at random. OAT follows a specified path to identify which importance changes can alter the shortlist. They answer different questions. Neither proves conceptual validity or measurement accuracy.

<!-- VISUAL: oat -->

## 11. Route minutes have specific limitations

All **2,196 distinct origins** have a saved query for the same scenario: 2,190 `Success` and six `NoRoute`. Sample A contains 2,170 successes and those six unavailable routes. NoRoute is never replaced by zero and does not prove that no real journey exists. Exact origin/destination coordinates, departure, mode and adapter version are checked and form the route cache context. B's old demonstrations or a different date cannot be silently substituted.

The indicator takes the **first itinerary's `duration/60`**. It does not independently search for a fastest alternative or discard inconvenient long walks. `TRANSIT` describes the request; it does not guarantee that the returned route boards public transport. Of the 20 valid itineraries in the separate AI desktop review, four contain a WALK leg only: Clementi Woods (403 m / 4.85 min), Pasir Panjang 1 landed (1,073 m / 12.88 min), the non-landed case there (736 m / 8.83 min), and Clementi West (2,072 m / 24.85 min). These explain some short campus values without supporting a claim that public transport was actually used.

Requests include `maxWalkDistance=1000`, yet five valid reviewed routes have a walking leg above 1,000 m and return `walkLimitExceeded=false`. Sentosa's first walk is 2,409.99 m / 32.30 min, with 2,753.68 m total walking. Neither the parameter nor the boolean guarantees a hard walking limit. A total walk above 1,000 m is also different from an individual leg above 1,000 m.

**Initial scheduling delay between 08:00 and itinerary start may be outside duration.** Reviewed transit itineraries begin 64–765 seconds after the requested time. The actual Sembawang Straits case starts 08:12:45 and arrives 10:03:31: its saved itinerary duration is 110.77 minutes, while 08:00 to arrival is 123.52 minutes. Sunset Way is 16.93 versus 23.17 minutes. A zero `waiting_min` therefore does not imply immediate departure at 08:00. The current 40/60 minute constraints apply to the frozen itinerary duration, not the entire requested time to doorway elapsed interval.

The AS8 point was desk reviewed using official information and returned routes, but remains a **building ground arrival proxy**. Final walking geometries in the review end about 12.44–13.38 m from the configured coordinate. This is not a surveyed door, accessible entrance, indoor route, lift delay or classroom arrival. Short modelled station connectors likewise do not measure actual platform transfers.

The saved review contains **21 cases: 20 valid itineraries and one unavailable response; 15 reviewed_acceptable and six reviewed_concern**. A separate AI context inspected full legs, times, geometry and duration components. Its data still came from OneMap: independence describes the review process, not an independent travel time provider. The unavailable case was retained and Sunset Way was appended to obtain 20 valid itineraries. No scenario matched alternative provider time comparison or human field timing was completed. This is not an accuracy rate or independent field validation. The [full desktop review](../route-desktop-review.md) and [AS8 endpoint review](../as8-endpoint-review.md) should travel with the results.

## 12. Commute caps and area feasibility thresholds

The 40/60 minute comparisons keep A, Subzone, balanced weights, 90% valid coverage, a 50% feasible/planned threshold and fixed normalisation:

| Raw itinerary cap | Feasible points | Eligible areas | Actual Top 5 in order |
| --- | ---: | ---: | --- |
| None, default | 2,170 | 239 | PEOPLE'S PARK / CHINA SQUARE / CHINATOWN / TANJONG PAGAR / BOAT QUAY |
| 40 minutes | 380 | 51 | PEOPLE'S PARK / TANJONG PAGAR / CLEMENTI CENTRAL / HOLLAND DRIVE / JURONG GATEWAY |
| 60 minutes | 1,304 | 167 | PEOPLE'S PARK / CHINA SQUARE / CHINATOWN / TANJONG PAGAR / BOAT QUAY |

CHINA SQUARE's sole location takes 45.13 minutes, so it fails the 40 minute cap and passes 60 minutes. Where only some locations pass, an area's score averages those feasible points; it may change with the cap even though the underlying housing conditions did not improve. A 40 minute cap is not a new normalisation and is not merely a penalty applied to longer journeys.

<!-- VISUAL: caps -->

The separate qualification experiment fixes the cap at **60 minutes** and changes only the minimum `F/N`:

| Minimum verified feasible share | Eligible areas | Top 5 |
| --- | ---: | --- |
| 25% | 178 | Same as the 60 minute main comparison |
| 50%, default rule | 167 | Same |
| 75% | 152 | Same |

An unchanged Top 5 means only that this shortlist is insensitive to these three tested thresholds. The eligible population still shrinks from 178 to 152, so the policy matters. These percentages are declared recommendation rules, not estimated student acceptance rates. See [cap 40](../../outputs/experiments/commute_cap_40/), [cap 60](../../outputs/experiments/commute_cap_60/) and the [qualification comparisons](../../outputs/experiments/qualification_comparisons.csv).

<!-- VISUAL: qualification -->

## 13. Three spatial arms: supplementation and unit scale

All spatial arms use **balanced weights, a 60 minute cap, A fitted normalisation and identical eligibility rules**. This makes each comparison interpretable.

| Arm | Planned locations | Units | Eligible units | What changes |
| --- | ---: | ---: | ---: | --- |
| A_subzone | 2,176 | 241 | 167 | Original sample and official units |
| B_subzone | 2,196 | 241 | 167 | Add 20 cluster coverage points, same units |
| B_cluster | 2,196 | 384 | 276 | Same B locations, cluster aggregation |

A_subzone and B_subzone use the same Subzone identities, so rank comparisons are valid. Their Top 5 is identical, Jaccard=1, with Spearman=0.999480 and Kendall=0.993363 across 167 jointly eligible areas. CHINATOWN's score nevertheless changes from 0.867704 to 0.869919. An unchanged shortlist does not mean every value is unchanged.

B_cluster's actual Top 5 consists of PEOPLE'S PARK `39fc69d26fca`, TANJONG PAGAR `df3846d8096e`, PEARL'S HILL `3f0b940407d7`, CHINATOWN `1064ecff3b71` and CHINATOWN `c03a99682846`. Those are five distinct analysis clusters, including two in CHINATOWN, not five distinct Subzones.

Subzone IDs and cluster IDs identify different kinds of objects. Cross type Spearman/Kendall ranks or ID Jaccard would not compare the same candidates. The implementation expands each selected Top 5 into a **common set of B locations** and separately into the **full candidate building/address source membership**:

- B_subzone selections cover 13 planned locations and B_cluster selections five; their intersection is four and union 14, so location Jaccard=`4/14=0.285714`.
- Full candidate record sets contain 64 and 17 records, with intersection 16 and union 65; building record Jaccard=`16/65=0.246154`.

This uses complete membership instead of labelling 13 or five samples as all housing. A count of 64 or 17 is still a source record count, not households, beds or rental capacity. Actual scale and support examples are:

| Selected unit | Planned locations | Full candidate records | Bounding box diagonal |
| --- | ---: | ---: | ---: |
| B_subzone CHINATOWN | 7 | 44 | 1,282.52 m |
| B_cluster CHINATOWN `c03a99682846` | 1 | 11 | 319.88 m |
| B_cluster CHINATOWN `1064ecff3b71` | 1 | 2 | 111.28 m |
| B_subzone CHINA SQUARE | 1 | 9 | 169.31 m |
| B_cluster PEOPLE'S PARK `39fc69d26fca` | 1 | 1 | 0 m |

All five selected clusters have only one valid sampled location. Smaller units can yield high scoring local selections with little sampled internal variation; a larger Subzone mean can hide internal differences. Low overlap means the geographic footprint of a recommendation changes with the unit definition. **Two scales do not establish which is better, and low Jaccard alone does not prove model failure.** Boundary effects, the 150 m threshold, 400 m grid, denser sampling and full routing remain possible extensions. The [spatial comparison JSON](../../outputs/experiments/spatial_comparison.json) and each arm's [support table](../../outputs/experiments/spatial_B_cluster/selected_unit_support.csv) retain the exact evidence.

<!-- VISUAL: spatial -->

## 14. Existing verification and correct reuse

The frozen implementation has a recorded 117 passing tests plus successful mypy and ruff checks, with standards/specification reviewed in separate contexts. Independent scalar arithmetic checked 2,170 valid A points and all 241 area support calculations, with maximum point and area discrepancies of 2.22e-16. Repeating the same inputs produced byte identical point scores, area scores, Top 5 and metadata. There are also 31 real static/cluster spot checks and independent checks of the 1,000 weight vectors and saved experiments. These are [existing verification records](../verification.md), not a claim that opening this document reruns them.

The evidence supports implementation consistency and reproducible arithmetic. It does not certify every housing use, facility operation, passenger journey or preference assumption. `production_ready=false` remains deliberate. Many decimal places in a score do not remove measurement or conceptual uncertainty.

A map, page or Agent must use `result_metadata.json`, `point_scores.csv`, `area_scores.csv` and `top5.csv` from the **same bundle**, checking the same `result_id`. The default lives in [outputs/score](../../outputs/score/); experiments have their own directories. Point tables retain every planned row, raw values, z values, status and contributions. Area tables retain coverage, feasible shares, support flags and ranks. Metadata binds weights, thresholds and versions. A Top 5 without those qualifications is incomplete.

The page selector switches among saved results. The saved 40/60 minute outputs use balanced weights. Unsupported destinations or combinations need an explicit “no computed result” response. New importance values, thresholds or campuses require a new core generated bundle; the frontend must not fill missing data, redefine the formula or present a score as a probability.

The complete standard package also contains [raw_data](../../raw_data/): 176 original delivery copy files totalling 625,191,511 bytes, including the A/B original ZIP archives and extracted contents, with copy integrity checked by file hashes. Notebooks default to this directory. The GitHub source repository excludes these original files. Teammates obtaining only the GitHub code need the complete package or matching original deliveries; older packages must not be assumed to contain the full sources. Keep derived `outputs/prepared` separate from original `raw_data`.

Notebooks support sequential explanation and recalculation from existing inputs. Rescoring saved measurements does not require a OneMap token; obtaining new scenario routes requires local credentials. For original preparation, use `raw_data` as the data root. Installation and commands are in the [root README](../../README.md), and field contracts in [interfaces.md](../interfaces.md). Preserve the current output and metadata before a new version.

## 15. Decisions to discuss next, in priority order

1. **Agree on the meaning of commute time.** The current value can accurately be described as first scheduled itinerary duration. If the user's decision concerns elapsed time from 08:00 to arrival, a new version can add requested time to arrival minutes. If boarding transport is required, retain a walking only flag or add a constraint. A strict walking limit requires inspecting returned legs and explicitly evaluating them. Compare new and old Top 5 using the saved long walk, walking only and initial wait cases instead of selecting convenient routes after seeing rankings.
2. **Address limited sampling support.** Options include retaining the current rules with prominent support counts, declaring a minimum valid sample requirement in advance, or adding locations in selected and borderline areas. These choices can change PEOPLE'S PARK's eligibility. High Monte Carlo frequency does not solve a one sample problem. Review residential use and rental suitability, especially in central units with very few source candidates.
3. **Resolve housing, service address and operation evidence.** Adjudicate the 107 postal conflicts with A/B. Review incomplete hospital/supermarket units, suspicious unit encodings and coincident records. Check the categories, access and entrances of 455 provisionally included park polygons. Complete retained transport point operation review. Decisions need record level audit evidence; writing “validated” in a report does not supply it. Rule revisions need a new data version and an appropriate normalisation basis.
4. **Collect genuinely independent travel evidence.** Freeze a sample and matching endpoints, date, time and mode first, then record a complete itinerary from another provider or conduct human timed journeys. Retain discrepancies and unavailable responses. Alternative providers, field observation and this AI assisted same provider desktop review must be identified separately.
5. **Confirm preferences and compensation.** User supplied importance can remain explicit; student surveys, AHP or another elicitation method require a real process and recorded results. Discuss correlated indicators, rental cost and housing supply. Adding a criterion changes the question and the data required.
6. **Extend spatial and measurement assumptions.** Register comparisons for 250/500 m sampling, multiple radii, distance decay, walking networks, park entrances, clustering thresholds and other campuses. Hold other conditions fixed for each comparison. Feasible work depends on route and source availability; the two existing unit scales do not replace these tests.

These are discussion options. **This handover does not replace the frozen scores, dataset version or route snapshot.** Any approved change should record the question, evidence, parameters, sample and version, save a complete new bundle in its own directory, and compare eligibility, Top 5, contributions and geographic support against the current baseline. Teammates can use the actual evidence here to write the final report and disclose AI assistance with code, figures, tests and desktop review.
