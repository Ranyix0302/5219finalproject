# Contribution standards

- Use the accepted implementation plan and ADRs as the behavior specification.
- Keep Python functions focused and names descriptive. Prefer straightforward
  data transformations; avoid speculative abstraction and deep nesting.
- Public analysis interfaces need docstrings with semantics and limitations.
  Additional inline comments explain non-obvious reasons in English.
- Test public seams with independently worked examples. Label synthetic
  fixtures, preserve failed observations, and do not use tests as field review.
- Do not change raw data or commit tokens, source datasets, or route caches.
- Preserve source identifiers, sample A/B separation, raw measurement units,
  fixed normalization parameters, planned denominators and deterministic IDs.
- Run relevant tests and type checks during work; run the full suite once at
  completion. Review the code against standards and the specification separately.
