# Processing methods: from source deliveries to interpretable results

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
