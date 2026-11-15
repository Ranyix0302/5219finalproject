# GE5219 residential GIS–MCDA

Python implementation of Xie Bingsheng's indicator framework, MCDA and
sensitivity analysis. The accepted specification is
[docs/implementation-plan.md](docs/implementation-plan.md).

## Submission guide

This repository implements residential sampling, seven accessibility measurements, public-transport routing to NUS AS8, weighted MCDA, and sensitivity analysis. The command-line entry is `python -m ge5219 <command>` or the installed `ge5219` command. The companion [Area Ranking Audit toolbox](https://github.com/Satelius/area-ranking-audit) provides a reusable ArcGIS Pro interface for building indicators and auditing regional rankings.

The interface reference below describes the executable code in this repository. The archived counts and findings in the handover sections belong to the dated public-transport analysis.

- [Input arguments and file schemas](#input-arguments-and-file-schemas)
- [Output formats and interpretation](#output-formats-and-interpretation)
- [Source comments and function documentation](#source-comments-and-function-documentation)

## Complete handover — 19 October 2026

Start with [the documentation entry](doc.html), the complete
[English handbook](docs/handover_en/README.md) or
[中文详细说明](docs/handover_zh/README.md). These cover the raw-data audit,
seven-indicator worked examples, normalization, weights, Monte Carlo, OAT,
spatial aggregation, OneMap timing/walking caveats and open decisions.
The [full-workflow notebooks](notebooks/) recalculate the saved-data workflow
offline by default. Read [code structure](docs/handover_en/code_structure.md)
for setup and optional full reruns.

The GitHub repository contains source, documentation and executed notebooks.
The separate Chinese and English complete ZIP packages additionally include
all 176 original A/B delivery files in `raw_data/`, prepared layers, cached
routes and saved experiment outputs. Extract the full package to reproduce
the frozen analysis; cloning GitHub alone does not supply those datasets.
Both packages also include the Chinese and fully translated English actual-results
pages, with embedded offline charts and selectors for the saved scenarios.
See [current progress and next tasks](docs/project-progress-2026-10-19.md) and
the [report methodology](docs/methodology_report_en.md).

## Current evidence — 2026-10-17

Real spatial preparation has run successfully. These are measured input and
sampling counts, **not recommendation results**:

| Item | Observed count |
| --- | ---: |
| Delivered residential source records |96,977|
| Records held out for107 unresolved cross-source postal conflicts |214|
| Remaining source-classified residential candidates |96,763|
| Subzones containing candidates |241|
|150 m connected analysis clusters |384|
| Original400 m sample A |2,176|
| Cluster-coverage supplements |20|
| Common comparison sample B / unique initial route origins |2,196|

Six static measurements have been computed. Python bus counts match B's fields
on every selected position; rail distance differences are below0.000001 m.
Four unopened Marina South exits are excluded by a dated LTA-backed rule;
the remaining609 exits have not all received individual operation review.
Residential use, transport operation, park categories and facility address
precision remain flagged for review. AS8 has received an official-source and
real-route desktop review as a building ground-arrival proxy; its exact door
has not been verified. All2,196 origins were queried:2,190 successful first
itineraries and6 explicit no-route responses. The A/Subzone balanced baseline
has239 eligible areas out of241; its Top5 includes four areas with fewer than
three valid samples. Keep the visible limited-support flags. All registered
experiments have completed:1,000 weight draws,84 OAT settings, three spatial
arms,40/60 minute caps and25/50/75% qualification checks. The portable results
page and prepared data are included in the local handover package. See
[handover.md](docs/handover.md) for actual findings and the next group tasks.
Synthetic tests are never research data.

The [static spot check](docs/static-data-spot-check.md) covers31 real cases and
corrected an unsupported clinic-address merge:1,192 licences now yield1,186
grouped/retained positions. The [route desktop review](docs/route-desktop-review.md)
records20 valid itineraries plus one unavailable case:15 acceptable desktop
reviews and6 concerns. These are independently conducted AI-assisted checks of
the same provider, not independent-source travel times or physical observation.

## Install

Python3.11+ is required. On Windows:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

The original A/B deliveries remain outside Git. `data/`, `outputs/`, tokens,
and route caches are ignored. The expected external input structure is:

```text
DATA_ROOT/
  GE5219_Indicators.gdb/
  GE5219_B_Handover/
    01_Data/Residential_Accessibility_API.csv
    03_GIS/BusStop_Points.gpkg
    03_GIS/MRT_Station_Exits.gpkg
```

## Run in restartable stages

###1. Prepare the real data

```powershell
.\.venv\Scripts\python.exe -m ge5219 prepare --data-root "PATH_TO_DATA_ROOT"
```

Outputs in `outputs/prepared/` include building/source mappings, Subzone and
cluster membership, original/supplementary sampling flags, static indicators,
source hashes, and explicit data quality/audit tables. Source files are never
modified. The107 conflict postcodes are held out pending adjudication;
exclusion is not a finding that either source is wrong.

See [spatial-data-notes.md](docs/spatial-data-notes.md) for address-based
facility grouping, boundary ties, retained point coordinates and park rules.
Source types do not prove current residential use or rental availability.

###2. Review endpoint and request routes

`config/destination.json` records the official AS8 address geocode, now
`reviewed:true` following [the recorded desktop review](docs/as8-endpoint-review.md).
The point is a route-network-connected building ground-arrival proxy. The final
walking geometry ends 12.44 m from the geocode; the connector and exact door
have not been independently surveyed. Indoor walking and lift access are outside
the travel-time measurement. Recheck and version the scenario if this endpoint
meaning changes.

Configure `ONEMAP_TOKEN` in the local process environment. Never commit it or
send it in a chat. With a valid token and reviewed endpoint, first run a pilot:

```powershell
.\.venv\Scripts\python.exe -m ge5219 route --max-requests 20
.\.venv\Scripts\python.exe -m ge5219 route
```

Both use `outputs/routes.sqlite` and export `outputs/routes.csv`. The second
command reuses successful cached origins. Initial unique origins are2,196;
retries add requests. The one-second interval alone would be about36.6minutes;
this is not a quota or completion forecast. Date/time is fixed to
**2026-10-19 08:00 Asia/Singapore**. Unavailable dates require an explicitly
versioned scenario change, not a silent substitution. See
[routing.md](docs/routing.md) for response statuses and checkpoint semantics.

###3. Score the frozen A/Subzone baseline

```powershell
.\.venv\Scripts\python.exe -m ge5219 score --routes outputs/routes.csv
.\.venv\Scripts\python.exe -m ge5219 score --routes outputs/routes.csv --max-commute-min 60 --output outputs/score-cap60
```

The first run fits A-only P5/P95 into `outputs/normalization-v1.json`. Later
runs refuse silently changed baseline measurements or dataset versions.
Original measurements remain in `indicator_matrix.csv`; missing/failed routes
remain unknown. Constant or undefined bounds raise an error for review.

Default weights are balanced; use `--scenario campus_first`, `transit_first`
or `lifestyle`, or `--weights` followed by seven comma-separated importances
in the order Campus,Rail,Bus,Shopping,Library,Healthcare,Green. The actual
normalized weights are exposed in result metadata. Allzero, negative and
nonfinite weights are rejected. Zero weights do not remove missing-data checks.

The default imposes no commute cap. An area must have >=90% seven-dimensional
measurement coverage and >=50% verified feasible share of **planned** points.
Area scores and contributions use the same feasible point means. Ranking
uses full precision, then mean raw commute, mean rail distance, and unit ID.
Fewer thanfive results remain fewer thanfive. `n_valid<3` is visibly flagged.

###4. Run the registered experiments

```powershell
.\.venv\Scripts\python.exe -m ge5219 experiments --routes outputs/routes.csv
```

This executes four preference scenarios,84 OAT settings,1,000 Dirichlet
perturbations (`kappa=50, seed=42`),40/60minute functional checks, and25/50/75%
qualification comparisons at60minutes. It saves every weight and area ranking,
selection frequencies, rank distributions, comparable-unit correlations,
OAT switching intervals, charts, and the three required spatial arms:

1. **A -> Subzone**: original baseline samples.
2. **B -> Subzone**: identifies supplementation effects.
3. **B -> cluster**: compares grouping on identical B positions.

All spatial arms use balanced weights and a60minute cap; normalization stays
fixed. Subzone/cluster ID lists are not directly correlated: spatial overlap
is calculated on the common B positions. Different Top5 unit sizes can produce
different footprint overlap without proving failure.150m chain connectivity
can create kilometre-wide analysis clusters; they are not verified estates.

The independently checked20routes and facility samples require actual review
evidence. Running an experiment or passing tests does not perform that review.

###5. Inspect the saved results and review evidence

After the score and experiments stages finish, generate a portable offline page:

```powershell
.\.venv\Scripts\python.exe -c "from pathlib import Path; from ge5219.result_report import create_result_report; create_result_report(Path('outputs/prepared'), Path('outputs/score'), Path('outputs/experiments'), Path('outputs/GE5219_MCDA_results.html'))"
```

The page reads saved bundles and checks dataset, result IDs, sample sets,
weights, qualification rules and route snapshot provenance. Scenario and cap
selectors choose registered results; they do not recompute scores in the browser.
See [route-validation.md](docs/route-validation.md) for the separate evidence
workflow. A review summary must bind the current route file and frozen scene;
an old or unbound summary is visibly excluded from current review completion.

## Interfaces and result status

[interfaces.md](docs/interfaces.md) defines stable DataFrame boundaries.
`ge5219.mcda.recommend` returns point scores, all area scores, Top5 and
metadata with one deterministic `result_id`. Raw, normalized and contribution
values are retained. The map, Agent and tables must use that result bundle.
The Agent must not change formulas, fill missing values, or invent rankings.

Parameter errors raise `ValueError`; the CLI returns exit2 and a readable
JSON error. Result metadata distinguishes `ok`, `data_coverage_insufficient`,
`no_feasible_results`, and `unsupported_destination`. Source readiness flags
travel with the bundle: a mathematically valid score is not data certification.

```powershell
.\.venv\Scripts\python.exe -m ge5219 status
.\.venv\Scripts\python.exe -m ge5219 report
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m mypy src/ge5219
.\.venv\Scripts\python.exe -m ruff check src tests
```

## Research and handover limits

Current candidates are delivered housing records, not all URA planned housing
or live rental listings. Euclidean distance is not network walk time; stop
count is not route/frequency supply; park boundary proximity is not an entrance.
Four preference vectors and parameter hypotheses are declared, not student
behavior calibration. Sensitivity tests show conditional robustness, not
conceptual validity or resident choice probabilities.

Code assistance used Codex for implementation, tests and documentation.
Students must verify sources, endpoints, facilities and reported results, and
write the final report from actual evidence with the required AI disclosure.

## Input arguments and file schemas

Run commands from the repository root. Paths containing spaces must be quoted. Paths below are filesystem paths, CSV files contain a header row, and JSON files use named keys. Use `python -m ge5219 <command> --help` to inspect a command's syntax.

| Command | Function | Main output |
| --- | --- | --- |
| `prepare` | Read delivered GIS data, construct samples, and calculate six static measurements | Prepared CSV and GIS layers |
| `route` | Request and cache OneMap itineraries for planned locations | SQLite cache and route CSV |
| `score` | Apply fixed normalization, weights, eligibility, and ranking | Point/area scores and selected regions |
| `experiments` | Evaluate preference, weight, qualification, and spatial assumptions | Saved scenarios and sensitivity tables |
| `status` | Inspect available preparation, route, and result metadata | JSON printed to standard output |
| `report` | Render the spatial-preparation evidence | HTML preparation report |

### Complete command-line argument reference

| Argument | Commands | Syntax and default | Meaning |
| --- | --- | --- | --- |
| `--data-root` | `prepare` | Required directory path | Root containing the A geodatabase and B handover, as laid out under Install |
| `--output` | `prepare` | Directory, `outputs/prepared` | Destination for prepared layers, measurements, and audits |
| `--prepared` | `route`, `score`, `experiments`, `status`, `report` | Directory, `outputs/prepared` | Existing prepared data consumed by the selected stage |
| `--destination` | `route`, `score`, `experiments`, `status` | JSON path, `config/destination.json` | Destination identity, coordinates, and review evidence |
| `--cache` | `route` | SQLite path, `outputs/routes.sqlite` | Persistent requests and responses used for resumption |
| `--output` | `route` | CSV path, `outputs/routes.csv` | Route measurement export |
| `--max-requests` | `route` | Optional integer, omitted by default | Maximum requests issued in this run, useful for a pilot |
| `--retry-no-route` | `route` | Boolean flag, off by default | Request cached no-route cases again |
| `--routes` | `score`, `experiments`, `status` | CSV path, required for `score` and `experiments`, optional for `status` | Route measurements and routing provenance |
| `--normalization` | `score`, `experiments` | JSON path, `outputs/normalization-v1.json` | Fixed A-sample percentile reference. First use creates the file, later runs validate its dataset and measurement binding |
| `--output` | `score`, `experiments` | Directory, `outputs/score` or `outputs/experiments` | Destination for the selected result bundle |
| `--scenario` | `score` | `balanced`, `campus_first`, `transit_first`, or `lifestyle`; default `balanced` | Preset importance vector |
| `--weights` | `score` | Seven comma-separated finite nonnegative numbers, e.g. `3,2,1,1,1,1,1` | Overrides the preset. Values are normalized to sum to one and must include a positive value |
| `--max-commute-min` | `score` | Optional nonnegative number in minutes, default no cap | Inclusive upper bound on raw campus commute minutes |
| `--sample-set` | `score` | `A` or `B`, default `A` | Original 400 m sample or the sample with cluster supplements |
| `--group-by` | `score` | `area_id` or `cluster_id`, default `area_id` | Unit over which feasible-point scores are averaged |
| `--result` | `status` | JSON path, `outputs/score/result_metadata.json` | Saved result metadata to inspect |
| `--output` | `report` | HTML path, `outputs/preparation_report.html` | Preparation report filename |
| `-h`, `--help` | All commands | Flag | Display command syntax and defaults |

`ONEMAP_TOKEN` is a local environment variable used by `route` for authentication. The fixed routing scene is `2026-10-19T08:00:00+08:00`, mode `TRANSIT`. Date, mode, and destination support follow the versioned implementation in `settings.py` and the routing adapter.

The destination JSON requires `destination_id` (string), `name` (string), `latitude` and `longitude` (decimal-degree numbers), `reviewed` (Boolean), and `coordinate_evidence` (string). The supplied file also records address, sources, coordinate precision, and review history. The supported destination is `NUS_AS8`.

### Measurement inputs

Every planned point has a unique string `location_id`, building/region/cluster identifiers, decimal-degree `latitude` and `longitude`, and Boolean `sample_A`. Preserve leading zeroes in identifiers. B comprises the complete analysis-location table. A selects the rows whose `sample_A` value is true.

The seven weight positions and measurement columns are fixed in this order.

| Position | Column | Type and unit | Interpretation and direction |
| --- | --- | --- | --- |
| 1 | `campus_transit_min` | Nonnegative number, minutes | First returned campus itinerary duration, lower is preferred |
| 2 | `rail_exit_euclid_m` | Nonnegative number, metres | Nearest rail-exit straight-line distance, lower is preferred |
| 3 | `bus_stops_800m` | Nonnegative count | Bus stops within 800 m, higher is preferred |
| 4 | `supermarket_sites_800m` | Nonnegative count | Grouped supermarket locations within 800 m, higher is preferred |
| 5 | `library_euclid_m` | Nonnegative number, metres | Nearest library straight-line distance, lower is preferred |
| 6 | `clinic_sites_1000m` | Nonnegative count | Grouped clinic locations within 1,000 m, higher is preferred |
| 7 | `park_proximity_euclid_m` | Nonnegative number, metres | Park proximity under the documented source-geometry rules, lower is preferred |

`static_indicators.csv` contains the six static columns and point identifiers. The route CSV requires `location_id`, `origin_lat`, `origin_lon`, `destination_id`, `destination_lat`, `destination_lon`, `departure`, `mode`, `route_status`, and `campus_transit_min`. `assemble_matrix` validates the routing scene and joins routes to all planned points. A missing route leaves campus minutes unknown. Blank measurements remain missing throughout eligibility calculations.

### Python scoring interface

```python
recommend(frame, params, weights, group_by="area_id", max_commute_min=None,
          min_valid_share=0.9, min_feasible_share=0.5, metadata=None, k=5)
```

| Argument | Python type and default | Meaning |
| --- | --- | --- |
| `frame` | `pandas.DataFrame`, required | All planned points for the chosen sample, identifiers, seven measurements, and `route_status` |
| `params` | `dict`, required | Per-indicator bounds returned by `fit_normalization(frame_A)` |
| `weights` | Seven-item numeric sequence or mapping of the seven feature names, required | Relative importances, normalized internally |
| `group_by` | String, `area_id` | Grouping field, `area_id` or `cluster_id` |
| `max_commute_min` | Number or `None`, `None` | Inclusive raw commute cap in minutes |
| `min_valid_share` | Number in `[0,1]`, `0.9` | Minimum complete-point count divided by planned count |
| `min_feasible_share` | Number in `[0,1]`, `0.5` | Minimum complete, constraint-satisfying count divided by planned count |
| `metadata` | `dict` or `None`, `None` | Dataset, destination, sample, and provenance carried into the result |
| `k` | Positive integer, `5` | Number of eligible regions selected |

The last two share thresholds and `k` are available through Python. The CLI uses their defaults. Complete points require all seven measurements. Normalization clips each value to its fixed P5/P95 interval, rescales it to `[0,1]`, and reverses cost indicators. The weighted point score is `sum(weight_j * normalized_j)`. Eligible regions must meet both share thresholds and contain a feasible point. Their scores average feasible-point scores. The public-transport implementation flags `n_valid < 3` as limited support.

## Output formats and interpretation

| Stage/file | Format and structure | Meaning |
| --- | --- | --- |
| `prepared/analysis_locations.csv` | One row per planned location with sample flags and IDs | Common point catalogue for routing and scoring |
| `prepared/static_indicators.csv` | Location identifiers plus six raw measurements | Static scoring inputs |
| `prepared/buildings.gpkg`, `analysis_locations.gpkg`, `subzones.geojson` | Vector GIS datasets | Buildings, sample locations, and region boundaries |
| `prepared/cluster_membership.csv`, `clusters.csv` | Membership and cluster summary tables | Building-to-cluster relationships |
| `prepared/data_quality.json` and audit tables | JSON and CSV | Data versions, counts, and preparation checks |
| `routes.sqlite`, `routes.csv` | SQLite cache and point-level CSV | Saved itinerary status, duration, and provenance |
| `normalization-v1.json` | JSON with `parameters`, dataset identity, and A-measurement fingerprint | Reusable normalization reference |
| `point_scores.csv` | One row per planned point, raw values, `z_` values, weighted contributions, and result identity | Point-level explanation and qualification |
| `area_scores.csv` | One row per regional unit | Planned/valid/feasible counts and shares, `eligible`, `limited_support`, score, and rank |
| `top5.csv` | Up to `k` eligible rows ordered by rank | Selected regions. The filename remains `top5.csv` when Python callers change `k` |
| `result_metadata.json` | JSON with `result_id`, `status`, applied weights, thresholds, and provenance | Run settings and state shared by result tables |
| `indicator_matrix.csv` | Full assembled B measurement table | Measurement record retained by CLI scoring, including when the scoring sample is A |
| `experiments/` | Scenario bundles, simulation weights/ranks, OAT tables, spatial comparisons, charts, and `experiment_manifest.json` | Results under the registered alternative assumptions |
| Preparation/results HTML | Standalone report pages | Visual inspection of saved data and result bundles |

`recommend` returns a dictionary containing `point_scores`, `area_scores`, and `top5` DataFrames plus a `metadata` dictionary. `save_result` writes these four components. Scores lie in `[0,1]` when defined. Unknown values are empty CSV cells or JSON `null`. Rank is assigned to eligible units. `limited_support` identifies a small supporting sample. Point and area contributions expose how indicators form the score.

Metadata status is `ok`, `data_coverage_insufficient`, `no_feasible_results`, or `unsupported_destination`. A successfully executed command returns exit code 0, including valid runs with no selected regions. Read `metadata.status` together with the tables. Handled parameter/input errors return exit code 2 and JSON containing `status` and `message`.

## Source comments and function documentation

The course submission also requests line-level comments and docstrings for user-defined functions. The current source contains module descriptions, selected inline comments, and function docstrings. Coverage is partial. Completing a line-by-line explanation and adding docstrings to all user-defined functions remain source-documentation tasks for submission. Function and module interfaces are documented above and in [the interface guide](docs/interfaces.md).
