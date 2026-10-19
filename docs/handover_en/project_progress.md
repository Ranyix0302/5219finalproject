# Progress and next work plan

Updated 19 October 2026. Computations were frozen on 17 October for the planned 19 October 08:00 Singapore routing scene.

## Completed

- Source audit, 96,763 candidate records, 241 Subzones, 384 analysis clusters, A=2,176 and B=2,196 representative locations.
- Six static indicators and all 2,196 route requests: 2,190 Success and six NoRoute; unknowns were not filled with zero.
- Frozen P5/P95, weight validation, raw-value caps, contributions, eligibility and deterministic result bundles.
- Four scenarios, 1,000 Dirichlet draws, 84 OAT settings, cap/qualification tests and all three spatial arms.
- 117 implementation tests, independent arithmetic/reproduction checks, 31 static/cluster cases and 21 AI-assisted same-provider desktop route cases. No field or independent-provider validation is claimed.
- Original-source copies, complete bilingual handbooks, processing/code guides and full-workflow notebooks. The execution audit and package manifest specify what was actually checked.

The formal Top 5 are PEOPLE'S PARK, CHINA SQUARE, CHINATOWN, TANJONG PAGAR and BOAT QUAY. Four have only one or two valid locations. The recommendation concerns sampled feasible locations under the declared specification, not every building or available rentals. OneMap's first itinerary can be walking-only, exceed requested walking parameters and omit initial schedule waiting.

## Next actions, in order

| Suggested work session | Collaborators | Action and acceptance |
|---|---|---|
| Next session, about 1 hour | Bingsheng + A/B | Decide sparse-support treatment, commute meaning, park categories and source conflicts; record dated decisions without silently changing the frozen baseline |
| Then 1–2 hours | Website/Agent owner + Bingsheng | Extract the package, run the notebook and connect one result_id across map, contributions and Top 5; demonstrate balanced, changed preferences and 40/60-minute cases with visible unknown/support flags |
| After integration, about 1 hour | Bingsheng + validation owner | Review walking-only, long-walk and initial-wait cases; decide whether to create a separately versioned elapsed-time/transit-required variant |
| Report integration, 1–2 hours | Bingsheng + report editor | Resolve highlighted TO DISCUSS items, align terminology/figures/script, disclose individual contributions and AI use, and check the whole-report 5,000-word limit |
| Before submission, about 1 hour | Whole group | Reproduce in another environment; check links, offline results, versions, report and video; record the actual receiving member's acceptance |
| Later, budget first | A/B + Bingsheng | Resolve data issues, obtain independent/field route evidence, then consider walking networks, other campuses, finer/coarser grids, distance decay and rent |

These are relative work sessions and suggested effort, not invented course deadlines. Website/Agent integration, user research, independent/field validation and final report approval remain group work.

## Decisions still needed

Keep or change the low-sample qualification rule; retain the precisely labelled first-itinerary variable or create a new timing/mode version; justify 800/1,000 m radii and examine redundancy; resolve postcode/address/operation/park evidence; decide how to present chaining-based analysis clusters. Keep `production_ready=false` until the evidence supports changing it.

Bingsheng's contribution covers indicator specifications, audit decisions, implementation/checking, experiment interpretation and handover, with AI assistance. A/B source contributions, website/Agent development and subsequent human acceptance belong to their respective contributors. Do not claim sole manual authorship or completed downstream validation.
