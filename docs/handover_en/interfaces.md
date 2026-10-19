# Interfaces for the next team member

**Scoring and a commute hard constraint are already implemented in Python.**
The current report switches saved scenario bundles. It has no HTTP service or
browser-side live scoring. No new OneMap request or token is required to
re-score existing measurements.

Read the [public contract](../interfaces.md) for the full schema and
[Chinese guide](../handover_zh/interfaces.md) for Chinese explanations.

## 1. Entry points and available parameters

| Interface | Use | Status |
|---|---|---|
| `ge5219.mcda.recommend` | New scores, custom weights, commute cap, eligibility thresholds, Top k, aggregation | Implemented |
| `python -m ge5219 score` | Save one reproducible scenario | Implemented; advanced thresholds/k are Python-only |
| Three CSVs + result_metadata.json | One recommendation shared by map, tables and Agent | Implemented |
| Website HTTP request | Server calls Python and returns JSON | **Not implemented; proposed in section 7** |

```python
recommend(frame, params, weights, group_by="area_id", max_commute_min=None,
          min_valid_share=0.9, min_feasible_share=0.5,
          metadata=None, k=5)
```

| Argument | Meaning/default | CLI option |
|---|---|---|
| frame | ALL planned positions, including failed/unknown routes; A=2,176, B=2,196 | --sample-set A (default) or B |
| params | Seven frozen P5/P95 objects and directions from normalization-v1.json["parameters"] | --normalization |
| weights | Seven finite nonnegative importance values, not all zero, sum-normalized internally; ordered vector or exact seven-key mapping | --weights; otherwise --scenario balanced |
| group_by | area_id default, or cluster_id | --group-by |
| max_commute_min | None default; finite nonnegative raw minutes; values ≤ cap pass | --max-commute-min |
| min_valid_share | n_valid/n_planned, default 0.9; range 0–1 | Python only |
| min_feasible_share | n_feasible/n_planned, default 0.5; range 0–1 | Python only |
| k | Positive nonboolean integer, default 5 | Python only |
| metadata | Mapping, default None; retain version, scene, sample and source hashes for handover | CLI builds context |

`top5` remains the return key/file name for any k and can contain fewer than k
rows. Presets are campus_first, transit_first, lifestyle and balanced; these are
declared preference scenarios, not survey estimates. Boolean, negative,
nonfinite and all-zero importance values are rejected. All seven dimensions
remain required even when one has zero weight.

Weights are not hard constraints. A poor commute score can be offset by other
indicators. A raw max_commute_min cap removes positions exceeding that duration
from feasible scoring. It does not compare normalized or clipped minutes.

For 10 planned positions, 9 valid and 4 feasible, valid coverage is 90% and
verified feasible share is 40%; the default model rejects the area. Do not
replace 4/10 with 4/9. The latter is conditional feasible share, separately
reported and unknown if n_valid=0. Eligibility also requires n_feasible>0.
limited_support means n_valid<3: a warning flag, not an extra eligibility rule.

Exact seven-feature order and units:

| Field | Unit | Direction |
|---|---|---|
| campus_transit_min | first OneMap itinerary duration, minutes | lower better |
| rail_exit_euclid_m | Euclidean metres to rail exit | lower better |
| bus_stops_800m | stop points within 800 m Euclidean radius | higher better |
| supermarket_sites_800m | service sites within 800 m Euclidean radius | higher better |
| library_euclid_m | Euclidean metres to library | lower better |
| clinic_sites_1000m | service sites within 1,000 m Euclidean radius | higher better |
| park_proximity_euclid_m | Euclidean polygon proximity; zero inside | lower better |

## 2. Minimal Python call

Install as described in [code_structure.md](code_structure.md). Run this from
the extracted complete package root, using the frozen joined B matrix:

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

The [complete executed example](../../examples/score_from_handover.py) additionally
checks dataset version, static/route hashes and A fingerprint, and rebuilds the
matrix through the public join boundary. Use that version during integration.

Custom importance and stricter eligibility use the same function:

```python
weights = {"campus_transit_min": 3, "rail_exit_euclid_m": 2,
           "bus_stops_800m": 1, "supermarket_sites_800m": 1,
           "library_euclid_m": 1, "clinic_sites_1000m": 1,
           "park_proximity_euclid_m": 1}
result = recommend(frame_A, params, weights, max_commute_min=60,
                   min_feasible_share=0.75, k=3, metadata=context)
```

Applied weights are [.3,.2,.1,.1,.1,.1,.1]. For B/cluster, use full frame,
group_by="cluster_id", and metadata sample_set="B". Re-aggregate through the
function; do not rename Subzone rows. Keep normalization fixed on A.

## 3. CLI commands

Run from the package root in Windows; always choose a fresh output directory:

```powershell
.\.venv\Scripts\python.exe -m ge5219 score --routes outputs/routes.csv --max-commute-min 40 --output outputs/interface_acceptance/cli_cap40
.\.venv\Scripts\python.exe -m ge5219 score --routes outputs/routes.csv --weights "3,2,1,1,1,1,1" --output outputs/interface_acceptance/cli_custom_weights
.\.venv\Scripts\python.exe -m ge5219 score --routes outputs/routes.csv --sample-set B --group-by cluster_id --max-commute-min 60 --output outputs/interface_acceptance/cli_B_cluster
.\.venv\Scripts\python.exe examples/score_from_handover.py
```

--weights overrides --scenario. CLI does not expose --min-valid-share,
--min-feasible-share or --k; use Python for these. Future CLI support would
only need argument parsing and forwarding, not a new scoring algorithm.
The CLI default output is outputs/score: it would replace baseline files.

## 4. Inputs, outputs, errors and identity

| Input | Content |
|---|---|
| outputs/prepared/static_indicators.csv | All planned B positions, IDs, names, coordinates, sample_A and six static indicators |
| outputs/routes.csv | Matching routes: IDs, origin/destination, scene/mode, status and minutes |
| outputs/normalization-v1.json | Frozen A bounds, dataset version and measurement fingerprint |
| config/destination.json | Reviewed NUS AS8 ground-arrival proxy |
| outputs/score/indicator_matrix.csv | Frozen joined B matrix for teaching; reconstruct/check during integration |

IDs/postal codes are strings. location_id is unique and each grouping ID has
one consistent name. Interchange uses EPSG:4326, distances use EPSG:3414 metres.
Do not drop failed/unknown positions: that would falsely reduce denominators.
assemble_matrix checks IDs, origin/destination, scene and mode, then left-joins
all planned positions. Only route_status=Success certifies observed minutes.

| Output | Main fields/use |
|---|---|
| point_scores.csv | Raw features, seven z_ scores, seven contribution_ values, is_valid/is_feasible, measurement/feasibility statuses, score, result_id; rejected/unknown rows retained |
| area_scores.csv | unit_id/name/type, planned/valid/feasible counts, valid_share, conditional_feasible_share, verified_feasible_share, eligible, limited_support, score/std/min/max, mean raw commute/rail distance, contribution means, rank, result_id |
| top5.csv | Up to k eligible rows in deterministic order |
| result_metadata.json | status, result_id, applied weights, cap, thresholds, dataset/method versions, destination/scene and source evidence |

The [public contract](../interfaces.md) and example outputs give exact names.
Rejected or unknown positions have no total score/contributions. Area scores
average feasible positions, not households or buildings. An ineligible area
can have a mean but cannot enter recommendations and has no rank.
Sort by unrounded score descending; exact ties use mean raw commute, mean rail
distance and stable ID ascending. Do not sort rounded display scores again.
Scores on 0–1 are model values, not probabilities.

All four files must share result_id. It incorporates input, parameters,
weights, caps, thresholds, k, grouping and supplied metadata. Metadata changes
can change it; keep separate dataset versions/hashes. The map, table and Agent
explanation must use the same result. save_result writes these four files.

Current hashing also preserves numeric representation: Python int 40 and
CLI-parsed float 40.0 give identical scores but different IDs. Standardize types
in integration and use the returned ID; never construct one from display
values. This is an identity limitation, not a scoring difference.
CLI score additionally writes the full B indicator_matrix.csv even when A was
scored; identify the actual sample through point_scores and sample_set.

| metadata.status | Meaning |
|---|---|
| ok | At least one eligible unit; can be fewer than k |
| data_coverage_insufficient | No unit reaches valid coverage |
| no_feasible_results | No complete eligibility passes, while coverage alone is not the explanation |
| unsupported_destination | Destination is not currently supported NUS_AS8 |

Invalid weights/caps/grouping, missing columns or duplicate IDs raise ValueError.
CLI prints invalid_parameters_or_inputs and exits 2. Valid no-result outcomes
exit 0: inspect metadata.status. Never substitute fabricated recommendations.
Missing/nonfinite pandas/NumPy values must become JSON null, never zero or a
nonstandard NaN literal. Use public write_json and display unknown values as such.

## 5. Executed acceptance evidence

The full example executed eight checks with no route-client call and preserved
all frozen input/baseline hashes. Outputs are in outputs/interface_acceptance/:

| Case | Sample/unit | Eligible | Check |
|---|---|---:|---|
| balanced, no cap | A/Subzone | 239 | Exact baseline mcda-7541f705e66a7e1095a13b60 reproduced |
| cap40 | A/Subzone | 51 | Top IDs/scores match saved experiment |
| cap60 | A/Subzone | 167 | Top IDs/scores match saved experiment |
| custom [3,2,1,1,1,1,1] | A/Subzone | 239 | Applied [.3,.2,.1,.1,.1,.1,.1] checked |
| cap60, 75% feasibility | A/Subzone | 152 | Matches saved qualification_75 |
| k=3 | A/Subzone | 239 | Exactly three returned rows |
| cap60, clusters | B/cluster | 276 | Matches saved spatial_B_cluster |
| cap0 | A/Subzone | 0 | no_feasible_results and empty Top table |

Baseline Top 5: PEOPLE'S PARK, CHINA SQUARE, CHINATOWN, TANJONG PAGAR,
BOAT QUAY. Cap40: PEOPLE'S PARK, TANJONG PAGAR, CLEMENTI CENTRAL,
HOLLAND DRIVE, JURONG GATEWAY. Constraints change qualifying points and areas.

[acceptance_summary.json](../../outputs/interface_acceptance/acceptance_summary.json)
records evidence. Each case includes four files and standards-compliant
response.json. Re-run during handover. This checks consistency with frozen
analysis, not correctness of every real-world measurement.

The three section 3 CLI commands were also executed and matched Python tables.
Replaying the CLI float cap type also reproduces its exact ID. Evidence:
[cli_acceptance_summary.json](../../outputs/interface_acceptance/cli_acceptance_summary.json).

## 6. Other stages and fixed versions

| Entry | Purpose |
|---|---|
| spatial.prepare_data / CLI prepare | Raw data to samples/static indicators/clusters/audits; no API |
| pipeline.assemble_matrix | Validate and join all planned measurements; no API |
| mcda.fit_normalization/normalize_indicators | Fit/apply percentiles; scenario changes only apply frozen parameters |
| routing.OneMapClient/SQLiteRouteCache/route_locations / CLI route | New routes and resumable scene-specific cache; token from local ONEMAP_TOKEN only |
| experiments.run_experiments / CLI experiments | Preferences, Monte Carlo, OAT, spatial/threshold comparisons; saved routes need no new request |
| CLI status | Prepared data, reviewed destination, routes and saved metadata |

Scene: 2026-10-19T08:00:00+08:00, Asia/Singapore; analysis mcda-v1.0;
destination NUS_AS8 ground-arrival proxy. First itinerary duration can be
walking-only and can omit initial waiting. A cap constrains that duration,
not a verified complete door-to-door commute. See
[processing_methods.md](processing_methods.md).

The public scoring function does not bind params to dataset hashes by itself;
the CLI/full example check dataset/A fingerprint binding. A server must also
check version, route/static hashes and scene. Do not refit P5/P95 when weights,
caps, A/B or grouping change. Changed measurements or indicator meaning require
an explicitly new parameter/analysis version.

## 7. Proposed web interface — not implemented

There is no current POST /recommendations endpoint. This is a proposed request:

```json
{
  "analysis_version": "mcda-v1.0", "destination_id": "NUS_AS8",
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

The next developer should:

1. Validate fields, types/ranges and supported version/destination/scene,
   sample and grouping. Reject unknown fields; do not silently ignore constraints.
2. Load verified data/parameters from fixed server-owned paths. Do not accept
   browser-supplied local paths, percentile files, tokens or executable code.
3. Call recommend and save a complete bundle. Record request/actual parameters,
   including k, which current core metadata does not separately return.
4. Return result_id, metadata, top5 and result-specific map/detail references.
   Retrieve point/area tables through that same ID. Keep low-support flags,
   coverage, caps, applied weights, statuses and source version in explanations.
5. Convert NaN/NA/nonfinite values to null. Proposed mapping: HTTP 422 for invalid
   parameters; HTTP 200 with domain status for a valid no-result request. Keep
   service failures distinct. This HTTP mapping still needs implementation.

The Agent converts language to structured choices and explains returned
evidence. It must not generate temporary scoring code, fill missing
measurements or independently assign ranks.

Acceptance: section 5 requests should reproduce weights, eligible counts,
Top IDs/scores and provenance through the wrapper; map/table IDs must align.
Exact old IDs require matching metadata too. Adding request IDs into hashed
metadata legitimately changes the core ID.

## 8. Unsupported requests and next work

| Request | Gap | Required work |
|---|---|---|
| Rail exit within 500 m | Only commute cap exists | Approve raw-field constraint/units; extend core feasibility/reason/version; test boundary/missing/planned denominator cases. Do not pre-filter points |
| Distance decay | Not calculated | Define function/beta and facility meaning; recompute measures, version normalization and repeat redundancy/robustness checks |
| NTU/SMU | Only NUS_AS8 supported | Review endpoint, collect new routes, agree normalization/versioning and extend support; never relabel NUS times |
| Different grid/cluster radius | Not recommend arguments | Version spatial preparation, regenerate points/measures, route new positions and rerun comparisons |
| Live weight sliders | Core available; HTTP absent | Implement section 7 or precompute finite selectable bundles |

Discuss: commute-only versus extra hard constraints; live server versus saved
scenarios; low-support minimum eligibility; whether commute should include
initial waiting. Agree research/product meaning before changing the next version.
