# Spatial preparation and interpretation

`ge5219.spatial.prepare_data(data_root, output_dir)` reads the delivered A GDB
and B handover without changing them. All measurements run in EPSG:3414;
latitude/longitude and the Subzone GeoJSON use EPSG:4326. Source data stay
outside the repository.

## Candidate records and identifiers

- The input is B's existing merged residential CSV. A residential records are
  **not appended again**. Their source object IDs, postal codes and checksums
  are mapped and checked one-to-one.
- `source_residential_id` preserves B's frozen `Residential_ID`. `building_id`
  hashes source layer, source object ID and six-digit postal code. This is a
  stable source-record identifier, not proof that the source describes one
  distinct building. The source mapping must remain with its input version.
- Both records in each unresolved cross-source postal conflict are held out;
  the input has 107 postal-code conflicts involving 214 source records. The
  conflict and held-out tables show their disposition. There is no preference
  for HDB or private-source coordinates without supporting evidence.
- HDB, Landed, Non-Landed and EC remain distinct attributes. Non-Landed is not
  silently renamed a verified condo. Source classification alone does not
  establish current residential use, completeness or rental availability.
- B's coordinates remain the analysis positions. Differences from A's point
  construction are recorded in `building_source_mapping.csv`; they are not
  overwritten while keeping B's former measurements.
- Different postal addresses at the same coordinates are retained. A point
  is a source building/address record, not a count of people or rentable units.

## Areas, components and samples

Invalid Subzone and park polygons are repaired only in derived copies. The
audit records source rows, geometry types and area before/after repair.
Subzone assignment first prefers strict interior. Boundary or overlap ties
are resolved by lexical official code and all intersecting codes are retained
in `subzone_assignments.csv`. Points outside all Subzones remain outside;
they are not assigned to the nearest polygon.

Clusters use all eligible residential records, within each Subzone. Edges
connect points at Euclidean distance <=150 m; undirected connected components
are the analysis clusters. Singletons remain. Cluster IDs hash sorted member
building IDs. Names refer to the official Subzone and analysis-cluster ID,
never an invented estate name. `extent_diagonal_m` is the diagonal of the
axis-aligned bounding box, an extent upper bound rather than an exact maximum
member distance or a real estate boundary. `housing_type_counts` records the
composition. Long chains can produce clusters spanning much more than150 m.

The grid has fixed origin (0, 0), cell size400 m, and floor-based cell IDs in
EPSG:3414. The baseline **A** selects the actual record nearest the grid centre
for every occupied cell x Subzone. Distance ties use stable building ID.

**B** is A plus one real member nearest the member-point centroid of each
cluster that A did not cover. This guarantees planned coverage of every
defined cluster; it does not make one point representative of a large cluster
or create population weighting. A remains separately marked by `sample_A`.
Supplementation does not depend on static scores or later route success.

## Six static indicators

| Field | Definition |
| --- | --- |
| `rail_exit_euclid_m` | Nearest retained MRT/LRT exit-point Euclidean distance after identified unopened-station exclusion |
| `bus_stops_800m` | Delivered bus-stop points within inclusive800 m Euclidean radius |
| `supermarket_sites_800m` | Standardised service-address sites within inclusive800 m |
| `library_euclid_m` | Nearest delivered library-point Euclidean distance |
| `clinic_sites_1000m` | Standardised service-address sites within inclusive1000 m |
| `park_proximity_euclid_m` | Distance to included park polygon; zero when inside |

Supermarket and clinic sites are grouped by normalised postal code, street
address, floor and unit. Multiple licences at the same full address become
one service address. Different units remain distinct sites even when their
source geocoding shares coordinates. Missing reliable address fields retain
separate source records and an uncertainty label. Every licence remains in
the source-to-site mapping. Address groups with coordinates spanning more
than20 m are flagged for review; the alphabetically first licence selects
the source point deterministically. This threshold is a review trigger, not
evidence of location accuracy. Supermarket `match_status` is retained. Missing
floor/unit, placeholder units and long numeric units that could reflect
spreadsheet conversion are flagged rather than guessed or repaired silently.

The source transport points do not contain an operation-status field. A partial
official-source review dated2026-10-17 identifies the four
`MARINA SOUTH MRT STATION` exits as not yet open: [LTA's Thomson-East Coast Line
page](https://www.lta.gov.sg/content/ltagov/en/upcoming_projects/rail_expansion/thomson_east_coast_line.html)
(updated2026-07-07) makes opening dependent on surrounding development and
does not announce a date. These four records remain in the source audit and
are excluded from nearest-exit measurement. `MARINA SOUTH PIER MRT STATION`
is a different station and remains included. [LTA's Circle Line6
page](https://www.lta.gov.sg/content/ltagov/en/upcoming_projects/rail_expansion/circle_line_6.html)
records the2026-07-12 opening of CC30/31/32, so those delivered exits remain.
The 613 source exits include LRT exits; do not filter them merely because a
station name lacks the letters MRT.

The remaining609 exits are **not individually certified operational**. Their
audit status says retained after partial review, with further station/exit
operation review outstanding. Distances/counts remain provisional. They do
not measure network walking time, routes or frequency. Removing the four known
unopened exits changes zero of the currently selected2,196 nearest distances;
this finding does not justify treating those exits as operating.

The frozen executable rule is `RAIL_OPERATION_REVIEW` in the spatial module.
`config/transit_operation.json` mirrors the full rule, review date, scope and
official evidence. Keeping an embedded copy makes the exclusion effective
after package installation; changing the reviewed rule requires updating its
tracked configuration mirror and code together. Preparation writes the actual
runtime rule snapshot to its output and hashes it into the source manifest,
so rule changes change `dataset_version`. The transit comparison audit keeps
both unfiltered613-exit and retained609-exit distances to separate reproduction
of B's historical calculation from the corrected indicator.

The seven `N_RESERVE=1` nature-reserve polygons are excluded. Other park and
corridor source records have a provisional inclusion list pending category
and public-access review. No centroid is called an entrance; polygon proximity
does not establish legal/physical access. Opening hours are unverified.

True zero counts stay zero. An empty facility source yields unknown values,
not zero service. Campus public-transit minutes are added by the routing
stage and are never estimated from Euclidean distance.

## Files and readiness

The output contract is in [interfaces.md](interfaces.md). Additional audits
include held-out residences, postal conflicts, source ID mapping, polygon
repairs, Subzone assignment, licence/site mapping, park category review,
transport operation review and Python-versus-B transit measurement differences.

`data_quality.json` records actual A/B and cluster counts plus unique routing
origins. These are initial request counts for one destination/time, before
retries; they are not an API speed or completion-time promise. Duplicate
positions can share cached routing even when separate records exist.
`source_manifest.json` hashes the source CSV, GDB files, transport GeoPackages
and the actual transit-operation rule snapshot; the combined manifest hash
supplies `dataset_version`.

Prepared values are real GIS measurements with review flags, not final
recommendations. `production_ready=false` and `readiness_blockers` are
intentional until source use, facility operation/category, destination and
route coverage checks are completed. A scoring program must propagate these
flags; successful preparation is not data certification.

## Verification

Public seam tests use labelled synthetic points/polygons to check:

1. 150 m chain connectivity, singleton supplementation and per-Subzone400 m
   coverage, including deterministic output under shuffled source order.
2. Boundary tie audit and retention of points outside the study polygons.
3. Inclusive radius counts, true zeros, missing-source handling and zero
   park distance inside a polygon.
4. Known unopened-station exclusion, separation of Marina South from Marina
   South Pier, retention of coded/LRT stations and honest unverified status.

The real preparation also compares Python-derived rail distances and bus
counts to the delivered B fields on the selected analysis positions.
