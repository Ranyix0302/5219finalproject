# Public-transit routing and resume contract

## Destination and scenario

The accepted scene is `NUS_AS8`, departure **2026-10-19 08:00 Asia/Singapore**.
`config/destination.json` currently remains **reviewed: false**. On 2026-10-17,
official OneMap search for AS8 returned the building address **10 Kent Ridge
Crescent, Singapore 119260**, latitude `1.296086762317243`, longitude
`103.7723482217768`. This verifies address identity, not an entrance or reachable
ground arrival position. The search response also contained an authentication
notice. No authenticated route or map access review has been completed.

The NUS official address supports the building identity. Neither it nor the
handover provisional coordinate `1.29604, 103.77229` establishes a usable
arrival point. A reviewer must verify the destination on the official map and a
route, record point semantics/reviewer/date in `coordinate_evidence`, update
coordinates if needed, and explicitly set `reviewed` to true. Production
`load_destination` and all route calls reject an unreviewed point. There is no
fallback to provisional coordinates.

## Public Python interface

```python
from ge5219.routing import (
    load_destination, OneMapClient, SQLiteRouteCache, route_locations,
)

destination = load_destination("config/destination.json")
client = OneMapClient()  # Reads ONEMAP_TOKEN from the process environment.
with SQLiteRouteCache("outputs/routes.sqlite") as cache:
    routes = route_locations(locations, destination, cache, client)
```

`locations` is a DataFrame with unique `location_id` and WGS84 `latitude`,
`longitude`. All input columns and every planned row survive, including pending
and failed rows. Returned columns add exact origin/destination coordinates,
destination ID, canonical departure, mode, adapter version, route key, status,
minutes, optional component values, HTTP code, attempt count, retrieval time,
and whether the value was reused.

`Destination(destination_id, latitude, longitude, reviewed=False,
coordinate_evidence='', name='')` is the immutable endpoint object.

`route_locations(..., max_requests=None, min_interval_seconds=1.0,
retry_no_route=False)` supports a bounded first batch and subsequent resume.
The request budget counts unique `client.route` calls; each call can perform up
to three HTTP attempts. It does not count duplicated planned locations or cache
hits. The one-second default is a conservative scheduling assumption inherited
from handover, **not a documented quota entitlement**.

## Official adapter semantics

Checked against [OneMap routing documentation](https://www.onemap.gov.sg/apidocs/routing)
and its official page bundle on 2026-10-17:

- GET `https://www.onemap.gov.sg/api/public/routingsvc/route`.
- Header `Authorization` carries the API token as in the official examples;
  the token comes only from `ONEMAP_TOKEN`, never an input notebook or CSV.
- WGS84 `start`/`end`, `routeType=pt`, date `MM-DD-YYYY`, time `HH:MM:SS`,
  `mode=TRANSIT`, `maxWalkDistance=1000`, `numItineraries=1`.
- The adapter takes `plan.itineraries[0].duration` in **seconds**, divides by60,
  and never substitutes another itinerary or a straight-line estimate.
- `walkTime`, `transitTime`, `waitingTime` are separately converted when
  supplied. Missing components/transfers/distance remain unknown, not zero.
- HTTP401/403 are authentication/authorization failures; HTTP429 is quota
  exhaustion. The docs explicitly describe HTTP404 as no route/no bus route.
  HTTP5xx, timeouts, network errors and malformed success payloads remain
  separate technical outcomes. Empty itinerary lists mean `NoRoute`; malformed
  payloads with no itinerary schema mean `ParseError`.

The only supported public-transport modes are TRANSIT/BUS/RAIL. Departures
require an explicit UTC offset and canonicalize to +08:00. Naive timestamps are
rejected rather than interpreted using the host machine's timezone.

## Cache, interruption, and retries

Cache keys include **exact floating-point origin/destination values**, destination
ID, canonical departure, mode and adapter version. Coordinate rounding does not
merge neighboring buildings. Fixed max-walk-distance and itinerary selection
belong to the adapter version; changing those policies requires a new version.
Identical positions in sample A and augmented B share one request even if their
location IDs differ.

Each completed request commits immediately into SQLite. Cache rows retain only
the public request scenario and allowlisted numeric/status outputs. Raw provider
bodies, headers, tokens and exception messages are never persisted or printed.

Statuses:

| Status | Meaning | Resume behavior |
|---|---|---|
| Success | First itinerary has a valid nonnegative duration | Reuse |
| NoRoute | Explicit no route or empty itinerary list | Reuse; retry only with `retry_no_route=True` |
| InvalidRequest | Other non-success HTTP4xx | Reuse; fix input/scenario before rerunning |
| AuthError | Missing credential or HTTP401/403 | Stop new calls; retry on a later invocation after credential correction |
| RateLimited | HTTP429 remains after bounded retries | Stop new calls; retry on a later invocation |
| ServiceError | HTTP5xx remains after retries | Retry on next invocation |
| Timeout / NetworkError | Transport failure | Retry on next invocation |
| ParseError | Incompatible/malformed response | Retry on next invocation; inspect adapter/source if persistent |
| Pending | No call due to request budget or halted batch | Attempt next invocation |

Retries use bounded exponential delays, honor numeric or HTTP-date Retry-After
up to a60-second cap, and have explicit connect/read timeouts (5/30seconds).
Each position retries at most once through the bounded client in an invocation;
duplicate location rows cannot produce a retry loop. A batch can be interrupted
and rerun; successful previously committed routes remain intact. Failed route
minutes stay missing and cannot satisfy an observed transit constraint.

## Source links and verification scope

- [NUS AS8 official address](https://scale.nus.edu.sg/contact/contact-us).
- [OneMap AS8 address lookup](https://www.onemap.gov.sg/api/common/elastic/search?searchVal=AS8&returnGeom=Y&getAddrDetails=Y&pageNum=1).
- [OneMap routing documentation](https://www.onemap.gov.sg/apidocs/routing).

Automated tests use synthetic HTTP responses at the external API boundary and
temporary SQLite databases. Passing them verifies adapter/cache behavior. It
does not certify live API quota, service dates, destination accessibility, or
the validity of actual routes; those require the separately recorded live pilot
and at least20 independent route reviews in the implementation plan.
