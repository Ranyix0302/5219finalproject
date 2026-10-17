# Route desktop-validation interface

This tool is separate from production routing. It does not modify the production
SQLite cache, route CSV, scores, destination or departure scenario. The public
interfaces live in `ge5219.route_audit`; its separate module command supports
`plan`, `collect`, and `report`.

## What counts as validation

Requerying OneMap provides **same-provider reproducibility evidence** and raw legs
for geometry/time/plausibility inspection. It does not provide independent travel
times or field truth. Automatic checks do not sign off routes. A separate reviewer
must inspect the actual legs and evidence, record a name, time, reviewer type and
notes, and identify the method used. A separate AI-assisted reviewer is allowed
when clearly labeled `AI_assisted_desktop`; a human desktop reviewer uses
`human_desktop`. Neither is a field visit or passenger observation. Google Maps
or another source is independent only when
its actual result and matching scenario are recorded. An unopened link is not a
cross-check. Report same-provider desktop review and external comparisons
separately; do not label either as observed passenger travel time.

The 20-case minimum is an audit sample, not a statistical accuracy estimate. A
problematic route stays in the audit and production snapshot until an explicitly
documented version change is justified. Do not replace a case because its route
looks awkward. A reviewed concern is still a concern, not a passing measurement.

## 1. Freeze the audit plan

After the complete production route snapshot and balanced/no-cap baseline exist,
but before examining selected raw legs, run:

```powershell
.\.venv\Scripts\python.exe -m ge5219.route_audit plan `
  --static outputs/prepared/static_indicators.csv `
  --routes outputs/routes.csv `
  --scores outputs/score/point_scores.csv `
  --output outputs/route_audit
```

`--scores` is optional when only a partial prototype exists; use it for the final
course audit to cover low and high MCDA scores. Supply the balanced, no-cap point
scores from the formal A baseline. B supplements without a formal score are kept
and tagged `score:unknown`. This option only stratifies an audit; it does not fit
normalization or alter recommendation inputs.

The deterministic selection rule is fixed in `route-desktop-audit-v1`:

1. Select northernmost, southernmost, easternmost, westernmost, closest-to-AS8 and
   furthest-from-AS8 origins, with stable location-ID ties and duplicates removed.
2. Greedily cover observed strata: eight bearings from AS8; source housing types;
   A versus B supplements; commute ≤40, (40,60], >60 minutes and unknown; all route
   statuses, including failures; and optional lower/middle/upper score thirds and
   unknown scores. Choose the point adding the most uncovered tags.
3. Break ties and fill to 20 using SHA-256 of `42:location_id`. Input row order
   cannot change the result.

Every selected case remains in `audit_plan.csv`, including failed/pending
production observations. The manifest records input/plan hashes, creation time,
algorithm version, observed strata, selected strata and any uncovered strata.
Twenty cases need not cover every possible combination. Inspect and report the
coverage; do not silently reselect until a result looks good. Existing plans are
never overwritten. Use an explicitly versioned new directory if a new snapshot
requires a new audit, keeping the original manifest.

The planned 2026-10-19 08:00 Asia/Singapore, `TRANSIT`, `NUS_AS8` scene and production
measurements are frozen in the table. Any available production provenance columns
must agree with this scenario and the actual static origins.

## 2. Explicitly collect evidence

Only this command uses a token. The caller must configure `ONEMAP_TOKEN` in its
process environment; no authentication/account request is generated. Do not put
the token in command arguments, files, documents, tests or source control.

```powershell
.\.venv\Scripts\python.exe -m ge5219.route_audit collect `
  --plan outputs/route_audit/audit_plan.csv `
  --output outputs/route_audit
```

Alternatively the parent process that already holds a credential can call
`main(["collect", "--plan", ..., "--output", ...])` in that process. The function
`collect_route_evidence(plan, destination, evidence_dir, token_env="ONEMAP_TOKEN")`
is the corresponding public Python boundary.

Collection makes one HTTP attempt per uncollected case with the exact frozen
origin, destination, date, mode and time, `maxWalkDistance=1000`, and first itinerary.
Requests start at least one second apart. Existing evidence is reused rather than
overwritten. Auth or rate-limit failure stops new requests, preserving prior
evidence. For an explicit retry or later comparison, use a new versioned evidence
directory; failed evidence is never silently removed.

Each JSON stores only an allowlist: non-secret scenario, retrieval time, numeric
HTTP status, first-itinerary times/distances/transfers, leg modes/routes/times,
stop names/coordinates and encoded geometry. Provider errors, debug data,
arbitrary request parameters, agency URLs, headers and exception text are omitted.
The files remain under ignored `outputs/`; raw evidence is not committed.

## 3. Inspect and record separate reviews

`collect` also writes a report; `report` can run offline at any time:

```powershell
.\.venv\Scripts\python.exe -m ge5219.route_audit report `
  --plan outputs/route_audit/audit_plan.csv `
  --output outputs/route_audit
```

Outputs:

| File | Meaning |
|---|---|
| `evidence/<location_id>.json` | Allowlisted real response or explicit collection failure |
| `route_checks.csv`, `route_checks.json` | Production differences, timing/geometry checks and flags |
| `route_audit.html` | Per-case route schematic, leg table, evidence notes, external links |
| `audit_review.csv` | Editable separate-review template copied from the frozen plan |
| `route_review.json` | Dashboard-compatible separate-review and structural-audit counts |

The HTML includes local SVG geometry schematics and NUS official AS8 access
sources. It has no third-party scripts or base-map dependency. Its geometry is not
a walkability map. Google Maps links carry the same origin and destination, but
the universal URL does not freeze transit departure: set **2026-10-19 08:00**
manually, record the observed query, route and time, and explain mismatches.

Keep `audit_plan.csv` immutable. The `plan` command also creates `audit_review.csv`;
let the separate reviewer fill `review_status` (`pending`, `reviewed_acceptable`,
or `reviewed_concern`), `reviewer`, `reviewer_type` (`AI_assisted_desktop` or
`human_desktop`), `reviewed_at`, and substantive per-case `review_notes`.
For external checks also fill `external_source_url`, `external_observed_min`, and
`external_departure_confirmed`. Re-run `report --plan .../audit_review.csv` after
review. Only a recognized reviewed status and reviewer type with nonempty reviewer,
timestamp and notes increments `reviewed_count`. It is a recorded sign-off, not machine proof
that the person performed it. `external_source_records_count` counts supplied
source records, not automatically verified agreement.

The report rejects missing, blank or duplicate location IDs. When the output
directory contains `audit_plan.csv`, the review must contain exactly its positions
and preserve every non-review field, including original coordinates, scenario,
production route key and measurements. Only the named review fields may change.
A sign-off additionally needs a collected evidence file with the matching
location ID, timezone-aware retrieval time and complete frozen request signature.
Missing evidence or a different scenario cannot increment review/audit counts.
A recorded failed query such as `NoRoute` may be reviewed as a concern; it cannot
receive an acceptable-route sign-off or be counted as successful structural evidence.

`route_review.json` initially has `status: "pending"`, `reviewed_count: 0`,
`required_count: 20`. `audited_count` counts successfully obtained first-itinerary
evidence, independently of separate approval. The summary includes reviewer-type
counts, limitations and reviewed-concern count. It may be copied unchanged into a downstream score or
experiment bundle; do not substitute `audited_count` for `reviewed_count`.

The summary also carries `source_routes_sha256` from the frozen plan manifest,
the actual frozen-file `plan_sha256`, a hash of the manifest, and
`review_table_sha256` for review contents (canonical UTF-8/LF CSV, sorted location
IDs and column names, empty missing values). It exports the unique destination
ID/coordinates, departure, mode and adapter version. `binding_status` is `bound`
only when the manifest supplies a valid source-route hash, its frozen-plan hash
matches the actual plan file, and the scenario is unique. Missing provenance,
mixed scenarios or plan-hash mismatch produce `unbound` plus `binding_issues`;
unknown hashes stay null. Review counts still describe the recorded desktop cases,
but an unbound summary cannot certify the current result snapshot. A downstream
page must compare the source-route hash and scene to its own result metadata;
copying a previously bound summary does not establish a match to new data.

## Automated checks and interpretation

Checks compare requery first-itinerary duration, walking/transit/waiting components
and walk distance against the frozen production values. A changed response does
not replace production input. The tool checks leg endpoint continuity, geometry
attachment, final AS8 connector, leg and itinerary timing, component sums, time
overlaps and walking ranges. The declared desktop flags use 2 seconds for time
sums, 100 metres for connector/gap review, 1,000 metres per walking leg, 2,000 metres
total walking, 0.5–2 m/s walking speed and 15 minutes initial scheduling delay.
These are transparent review heuristics, not empirically validated service
thresholds or rejection rules. `maxWalkDistance` is not assumed to be a guarantee
on the whole journey; a flag does not automatically invalidate a route.

The production indicator is itinerary `duration/60`. The tool separately exposes
initial scheduling delay (first-leg start minus requested 08:00) and requested
time to arrival. A provider's itinerary duration may omit initial scheduling
delay. Do not silently change this established indicator; record that limitation
and any materially different interpretation as a separate method experiment.

AS8 is an official address point connected to the route network, used as a
building ground-arrival proxy. It is not a surveyed entrance or indoor room.
The [NUS arrival guide](https://fass.nus.edu.sg/ecs/wp-content/uploads/sites/4/2022/03/Roadmap-for-Conference-Venue.pdf)
supports building access and lift directions (pages 3–6), not current transit
frequencies. The [NUS official address](https://scale.nus.edu.sg/contact/contact-us)
and [OneMap routing documentation](https://www.onemap.gov.sg/apidocs/routing)
provide endpoint/API context; neither establishes passenger-observed accuracy.
