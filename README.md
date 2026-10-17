# GE5219 residential GIS–MCDA

Python implementation of Xie Bingsheng's indicator framework, MCDA and
sensitivity analysis. The accepted specification is
[docs/implementation-plan.md](docs/implementation-plan.md).

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
precision remain flagged for review. AS8 endpoint review and OneMap routing
are outstanding. **No official seven-factor Top5 or real sensitivity results
have been generated.** The synthetic tests are never used as research data.

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

`config/destination.json` records the official AS8 address geocode. It remains
`reviewed:false`: an address point does not establish a reachable ground
arrival location. Review the map/route, record reviewer/date/point semantics in
`coordinate_evidence`, correct coordinates if necessary and explicitly set
`reviewed:true`. This is a data-validation step from the accepted plan.

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
