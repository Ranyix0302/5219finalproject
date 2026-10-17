# NUS AS8 destination endpoint review

Review date: 2026-10-17. Scope: official-source address/access evidence and existing authenticated OneMap route-response inspection. No additional authenticated requests were made by this reviewer. No credentials are included.

## Decision

The configured coordinate **1.296086762317243, 103.7723482217768** can be used for the first version as a **route-network-connected AS8 ground-arrival proxy**. It must not be described as a surveyed entrance, a verified exact door, an indoor room arrival, or a guarantee of barrier-free access. This is an evidence-based desk review of a proxy point, not a physical site inspection.

Retain the coordinate rather than replacing it with an arbitrary entrance-looking point. The official map supplies an AS8 department marker, and OneMap supplies the address point plus a connected final walking route. The available official sources do not publish an independently georeferenced door coordinate.

## Evidence

1. **Official building identity and postal address**: NUS SCALE contact page identifies Block AS8, 10 Kent Ridge Crescent, #03-01, Singapore 119260.
   https://scale.nus.edu.sg/contact/contact-us

2. **Independent official campus-map landmark**: NUS campus-map live JSON, queried with qword=SCALE, has faculty record id=485, Block AS8, 10 Kent Ridge Crescent, postal 119260, department location #03-01, latitude 1.2961592865754692, longitude 103.77224213451768. This is a department/building location marker, not an entrance dataset.
   https://map.nus.edu.sg/search/ajax_auto?qword=SCALE&maxrows=100
   https://map.nus.edu.sg/#page=detail&type=faculty&id=485

3. **Official ground-access directions and photos**: NUS Economics conference roadmap, PDF pages 3-6 (1-based), directs visitors arriving at Central Library to enter Block AS8 and use its lift. Page 5 names AS8 and the same address, with a street-side building photo. Page 6 shows the AS8 lift and first-storey directory. This supports public pedestrian arrival to the building followed by a lift; it does not georeference a particular door. The 2022 document is used for the existence and meaning of physical access, not for current bus timetables.
   https://fass.nus.edu.sg/ecs/wp-content/uploads/sites/4/2022/03/Roadmap-for-Conference-Venue.pdf

4. **Existing OneMap route-response inspection**: outputs/endpoint_probe_response.json contains a successful actual transit/walk response for departure 2026-10-19 08:00 Asia/Singapore. Its final leg is WALK from INFORMATION TECHNOLOGY stop 16189, (1.297361, 103.772848), to Destination (1.2960868, 103.7723482). Final walking distance is 189.25 m; duration 182 s. The decoded 20-vertex walking geometry ends at (1.29618, 103.77241), 12.44 m from the configured address point. This is a small routing attachment / destination connector, not an exact traced walk to the address marker. The response labels the address point as Destination and reports a final walking leg, supporting a building-level ground-arrival proxy. The 12.44 m connector is not independently verified. Route-model connectivity is not physical entrance verification.

## Spatial checks

- OneMap point to official NUS AS8/SCALE department marker: 14.3 m (haversine).
- Final decoded walking-polyline vertex: (1.29618, 103.77241); distance to configured point: 12.44 m.

## Recommended metadata semantics

- coordinate_precision: official AS8 address geocode; route-network-connected building ground-arrival proxy; exact entrance not verified.
- reviewer: official-source and route-response desk review (2026-10-17).
- A reviewed flag is defensible only if it means that this stated proxy has undergone a desk review. It must not be interpreted as exact-door verification.
- Include final walking legs in route validation. Indoor walking, lift waiting, classroom access, and any omitted private NUS shuttle services are outside what this endpoint review establishes.
- No change to destination.json was made by this reviewer.
