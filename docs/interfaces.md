# Implementation contracts

Practical handover guides: [中文](handover_zh/interfaces.md) and
[English](handover_en/interfaces.md). They include executable examples, parameter
defaults, schemas, failure states, verified calls and proposed web integration.
Use [examples/score_from_handover.py](../examples/score_from_handover.py) to run
the implemented scoring interface against the frozen real snapshot. It writes
only `outputs/interface_acceptance/`, and makes no routing requests.

**Available:** Python re-scoring, seven custom importance values, a raw commute
cap, coverage/verified-feasibility thresholds, Top k, A/B sample selection and
Subzone/cluster aggregation. **Absent:** HTTP endpoints, arbitrary distance hard
constraints, other campuses, distance-decay indicators and browser-side live
scoring. The current report switches saved result bundles.

The accepted Chinese implementation plan in `docs/implementation-plan.md` is the
specification. Test seams are the public preparation, recommendation, routing,
and experiment entry points named in that approved plan's acceptance checks.
Synthetic fixtures are labelled test data and never mixed with GIS outputs.

## Shared point schema

`location_id`, `building_id`, `area_id`, `area_name`, `cluster_id`, `cluster_name`,
`latitude`, `longitude`, `sample_A` (boolean). B is the entire analysis location
table; A is its `sample_A` subset. IDs and postal codes are strings.
Raw indicators use the seven ordered names in `ge5219.settings.FEATURES`.
`route_status=Success` is required for observed transit minutes; missing/failed
routes stay missing. Normalized columns use `z_` and contributions `contribution_`.

## Spatial preparation

`ge5219.spatial.prepare_data(data_root: Path, output_dir: Path) -> dict`
reads the unchanged A GDB and B handover, emits `analysis_locations.csv`,
`static_indicators.csv` (location schema plus six static features),
`buildings.gpkg`, `analysis_locations.gpkg`, `subzones.geojson`,
`cluster_membership.csv`, `clusters.csv`, `data_quality.json`, and audit tables.
Coordinates use EPSG:3414 for calculations and EPSG:4326 for interchange.
Unresolved source conflicts and category/operation review are recorded, never
silently certified. A subzone receives a sample for each occupied grid cell.

## Deterministic recommendation

`fit_normalization(frame_A) -> dict` fits P5/P95 on valid observed nonnegative
values, separately per indicator. Undefined or constant bounds raise ValueError.
`normalize_indicators(frame, params) -> DataFrame` retains raw values and creates
`z_<feature>` columns. Cost columns are reversed after clipping.
`recommend(frame, params, weights, group_by='area_id', max_commute_min=None,
min_valid_share=0.9, min_feasible_share=0.5, metadata=None, k=5) -> dict`
returns `point_scores`, `area_scores`, `top5` DataFrames and `metadata` dict.
The input contains ALL planned points, including failures. Parameters do not
change with weights, caps, sampling, or grouping. All seven dimensions are
required even when some weights are zero. Invalid caller parameters raise
ValueError. Metadata uses `status`: ok, data_coverage_insufficient,
no_feasible_results, or unsupported_destination. Areas expose `unit_id`,
`unit_name`, `unit_type`, `n_planned`, `n_valid`, `n_feasible`, all three shares,
`eligible`, `limited_support`, `score`, contribution means, mean commute and MRT
distance, and rank. Rank uses unrounded score, then raw commute, MRT and unit ID.
One result_id joins tables and metadata; deterministic input/config produces
the same result_id.

Weights may be a seven-item vector in FEATURES order or a mapping with exactly
the seven feature keys. Finite nonnegative values, not all zero, are normalized
to sum to one. Booleans are rejected. A commute cap is inclusive and uses raw
minutes. Both share arguments use [0,1]; k is a positive nonboolean integer.
`limited_support` means n_valid<3 and is a flag, not an additional eligibility
filter. `top5` is still the return key/file name for any k. A unit can have a
score but be ineligible; only eligible units receive ranks and enter top5.

Result IDs include the planned input, complete configuration and supplied
metadata. Arbitrary metadata changes can change the ID. Retain data versions
and hashes separately. Python callers must verify normalization dataset/A
fingerprint binding; recommend does not itself load or validate the surrounding
normalization-file provenance. The CLI and runnable example enforce that check.

Current identity hashing preserves numeric representation: a Python cap of int
40 and a CLI-parsed float 40.0 produce identical scores but different IDs.
Standardize argument types in an integration and use the returned ID; never
construct it from displayed parameters. Exact replay requires matching numeric
types and metadata as well as values. This is an identity limitation, not a
scoring difference.

`assemble_matrix(static, routes, destination, departure=DEPARTURE)` validates
IDs, coordinates, destination, departure and mode, then left-joins every planned
position. `read_locations(path)` preserves string IDs/leading postal zeroes,
round-trip floats and explicit sample_A booleans. `save_result(result, output)`
writes point_scores.csv, area_scores.csv, top5.csv and result_metadata.json.
`write_json(path, payload)` serializes unknown/nonfinite pandas/NumPy values as
JSON null, never zero or a nonstandard NaN literal.

## Routing

`ge5219.routing` supplies a OneMap client and resumable SQLite cache. Route keys
include exact origin/destination coordinates, destination ID, departure, mode,
and adapter version. Identical positions share one request across sample sets.
The adapter selects the first itinerary; absent components remain unknown.
HTTP/auth/rate-limit/parse/no-route failures are separate, cached and retryable.
Tokens come only from ONEMAP_TOKEN environment variable, never persisted/logged.
Official endpoint and payload semantics are checked against OneMap docs.
Production routing requires a destination config whose reviewed flag and
coordinate evidence are explicit; provisional handover coordinates alone do
not count as review.

## Parent-owned integration

CLI commands prepare, route, score, experiments and status keep local source
paths external. Experiment outputs include all weights/ranks, reproducible
seeds, common candidate counts, and A/Subzone, B/Subzone, B/cluster comparisons.
Incomplete real data returns documented status and never becomes demo scores.

CLI `score` exposes --scenario (balanced default), --weights (overrides scenario;
seven comma-separated numbers), --max-commute-min (default none), --sample-set
A|B (A default), --group-by area_id|cluster_id (area_id default), --prepared,
--destination, --routes, --normalization and --output. It does not expose
min_valid_share, min_feasible_share or k; use Python for those. --routes is
required. Use a fresh output directory to preserve the frozen baseline.
CLI score additionally writes indicator_matrix.csv for full B, even when A is
scored; the four-file bundle identifies the actual scoring sample.

Valid domain no-result states return normally (CLI exit 0); clients must read
metadata.status. Invalid inputs raise ValueError; CLI prints status
invalid_parameters_or_inputs and returns 2. Argparse syntax errors also return
nonzero. An empty top table must never be replaced with invented recommendations.

Current scene: NUS_AS8, 2026-10-19T08:00:00+08:00, analysis mcda-v1.0.
First-itinerary duration can be walking-only and may omit initial waiting.
Changing weights/caps/sample/grouping reuses saved routes and fixed A bounds;
new measurement data or indicator meanings require explicit versioning.

Eight executed cases in outputs/interface_acceptance/ cover exact baseline
identity, 40/60-minute caps, custom weights, 75% feasibility, Top 3, B/cluster
and a valid zero-result case. See the practical guides for inputs, counts and
the proposed HTTP request/response policy. The HTTP contract is **not yet
implemented**. A future server must call this deterministic core from fixed
server-owned data and return one result_id across map, tables and Agent evidence.

`run_experiments` requires full `building_membership` with building_id,
area_id, cluster_id and EPSG:3414 x_3414/y_3414. Each spatial arm exports selected
units' full candidate-record counts, bounding-box extent and planned/valid/
feasible sample support. Source-record counts are not household estimates.
