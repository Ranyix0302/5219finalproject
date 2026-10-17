# Implementation contracts

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
