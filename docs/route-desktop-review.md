# Route desktop plausibility review

Review date: 2026-10-17. Reviewer: **Codex / review_real_routes**, a separate AI
reviewer context. Recorded reviewer type: `AI_assisted_desktop`.

This is **same-provider reproduction plus an independently conducted AI-assisted
desktop plausibility review**. Independence describes the review process, not the
travel-time data source. It supplies neither an independent route-time estimate
nor field truth, and it is not a human site visit or passenger observation.

## Frozen sample and evidence

The reviewed sample is `outputs/route_audit_v2/audit_plan.csv`, with 21 distinct
origins. Its first 20 cases retain the original v1 selection and include the
production `NoRoute` case. The manifest documents appending the next deterministic
case, Sunset Way `LOC_BLD_b688b8a2fb1b83cbbaac`, to obtain at least 20 valid
itineraries. The failed case was retained. All observed bearing, housing, A/B,
commute, score-third and production-status strata are covered; this does not cover
every combination or establish a statistical accuracy rate.

The scenario is **2026-10-19 08:00 Asia/Singapore, TRANSIT, NUS_AS8** at
`1.296086762317243, 103.7723482217768`. The reviewer read all 21 allowlisted raw
JSON files, including the empty response, and examined all legs of each of the 20
valid itineraries: names, modes, route numbers, coordinates, decoded geometry,
start/end times, walking connections, transfer order and duration components.
The decoded paths were also visually inspected in the locally generated
`outputs/route_audit_v2/desktop_review_geometry.png`. This schematic has no street
basemap and does not establish pedestrian access rights, crossings or terrain.

The recorded outcome in `outputs/route_audit_v2/audit_review.csv` is **21 reviewed
cases: 15 reviewed_acceptable and 6 reviewed_concern**. Twenty have valid,
distinct complete leg sequences; the remaining case has no itinerary to inspect.
An acceptable status means desktop plausibility within the limitations below.
It does not certify real-world duration or exact access.

## Findings

All 20 valid requery itineraries reproduce the frozen production duration,
walking/transit/waiting components and walking distance, within numerical
rounding. Independent arithmetic on the raw evidence found consistent itinerary
start/end duration, component sums and leg time spans, with no reversed leg times
or overlaps. Adjacent leg endpoint coordinates join exactly. These results are
same-provider consistency evidence; sharing a provider can reproduce the same
systematic omission.

The decoded geometry broadly follows the named route chains. For example,
Sembawang Straits uses 882, NS to Choa Chu Kang, and 188; the northern NS routes
connect through Jurong East to EW and Clementi; the northeastern NE routes
connect through Serangoon to CC and Buona Vista. The Marine Parade case takes
the southern CC arc from Dakota to Buona Vista, while the Geylang East case
takes the northern arc from Paya Lebar. These different directions are visible
in the actual geometries. LTA states that CCL6 opened on **12 July 2026**, before
the frozen journey date, so the southern connection is geographically plausible
under the published network. This checks network context, not that itinerary's
32-minute rail time. [LTA CCL6](https://www.lta.gov.sg/content/ltagov/en/upcoming_projects/rail_expansion/circle_line_6.html)

NUS's Central Library directions identify bus 95 from Buona Vista, bus 96 from
Clementi, and bus 151 as campus access options, with stops at Central Library or
opposite it near Information Technology. This supports the building-access
context of the repeated final connections. It does not independently verify the
specific 96A service, bus departures, frequencies or recorded travel times.
[NUS Central Library directions](https://www.nus.edu.sg/nuslibraries/spaces/our-libraries/central-library)

### Retained concerns

| Case | Origin | Concern retained after reading the actual legs |
|---|---|---|
| 2 | Sentosa | Initial walk to OPP VILLAGE HOTEL is 2,409.99 m / 32.30 min; total walking is 2,753.68 m. The subsequent 123 → EW → 95 chain is connected in the returned model. |
| 6 | One Tree Hill | HTTP 200 with `NoItineraryOrParseError` and an empty payload. No legs, geometry or time can be reviewed. This does not prove real-world transit absence. |
| 9 | Pasir Panjang 1, landed | TRANSIT query returns one WALK leg of 1,073 m / 12.88 min. |
| 13 | Clementi West | TRANSIT query returns one WALK leg of 2,072 m / 24.85 min. |
| 17 | Woodlands East | Initial walk to Admiralty is 1,312.44 m / 22.17 min; total walking is 1,785.10 m before/after the NS → EW → 183 chain. |
| 20 | Anchorvale | Initial walk to Sengkang is 1,313.33 m / 19.82 min, with an 86.62 m origin-to-geometry attachment difference; total walking is 1,592.23 m. |

There are **five**, rather than six, valid cases with a walking leg above
1,000 m; the sixth reviewed concern is the missing itinerary. The collector sends
`maxWalkDistance=1000`, yet all five returned itineraries have
`walkLimitExceeded=false`. The observed response therefore does not support
treating the parameter or this boolean as a strict compliance guarantee. The
review retains these concerns without changing the frozen production values.
The 1,061.19 m Sembawang Springs and 1,086 m Sembawang Hills totals are split
across shorter walking legs; a total above 1,000 m alone was not treated as a
per-leg violation.

Four valid TRANSIT responses are walking only: Clementi Woods (403 m / 4.85 min),
Pasir Panjang 1 landed (1,073 m / 12.88 min), Pasir Panjang 1 non-landed
(736 m / 8.83 min), and Clementi West (2,072 m / 24.85 min). Zero transit and zero
waiting components are internally consistent for these responses. Their
production indicator represents the provider's returned itinerary, including
the walking-only option, rather than a guarantee of boarding public transport.

### Time interpretation

The established production indicator is itinerary `duration/60`. Every transit
itinerary starts later than the requested 08:00, by **64 to 765 seconds**. This
initial scheduling delay is outside the returned itinerary duration. The
Sembawang Straits case, for example, starts at 08:12:45 and arrives at 10:03:31:
its stored duration is 110.77 min, while 08:00-to-arrival is 123.52 min. Sunset
Way's appended case starts at 08:06:14 and arrives at 08:23:10, giving 16.93 min
of itinerary duration and 23.17 min from the requested departure. A zero waiting
component for bus 151 in Sunset Way or Swiss Club therefore does not mean zero
elapsed time before leaving at 08:00. No indicator was redefined during review.

Short station connectors also have limited semantics. In Marine Parade, the
Dakota stop-to-station WALK leg is 8.63 m / 7 s, followed by 171 s before the
train starts. It must not be read as a measured seven-second trip from bus to
train platform. Jurong East's NS-to-EW connections use the same station
coordinate and a 140 s gap without a separate WALK leg. These are modelled
connections, without verified platform paths, gates, stairs or congestion.

### Origin and AS8 connections

Geometry attachment differences are present despite continuous named leg
endpoints. The largest is the 86.62 m Anchorvale origin attachment; the Changi
bus 109 geometry ends approximately 83.2 m from its declared alighting stop.
Neither exceeds the declared 100 m review heuristic, but both remain visible in
the per-case notes. A threshold is not proof of exact access. Walking-leg speeds
from the reported distance and duration range from 0.77 to 1.39 m/s; these do
not account for a person's mobility, gradients, queues or crossing delays.

Final walking geometries terminate approximately **12.44–13.38 m** from the
configured AS8 address point. The returned final walks include Central Library
(85.42 m), Information Technology (189.25 m), Before Kent Ridge Terminal
(379.49 m), and the four walking-only paths. AS8 remains a building-level
ground-arrival proxy, as documented in [the endpoint review](as8-endpoint-review.md).
These connections do not establish a surveyed door, barrier-free entrance,
indoor route, lift delay or classroom arrival.

## Limits of the evidence

The separate review did not make authenticated API requests, read credentials,
replace production route values or recompute frozen scores. The evidence is
scheduled provider output for a future Monday, not observed travel. Only the
first returned itinerary was reviewed; optimality, missing private campus
shuttles, service disruptions, current footpath conditions and comparative
accuracy against another journey planner remain unverified. Official NUS/LTA
pages were consulted for access and network context only; **no independent
scenario-matched travel-time result was recorded**, so all external observed
time fields remain empty. An unopened Google Maps link is not evidence.

The review supports using the recorded model outputs with these explicitly
retained limitations and concerns. It cannot support claims of passenger-time
accuracy, a validated maximum walking allowance, or a verified exact entrance.
