"""Frozen v1.0 indicator definitions and declared experiment settings."""

FEATURES = (
    "campus_transit_min",
    "rail_exit_euclid_m",
    "bus_stops_800m",
    "supermarket_sites_800m",
    "library_euclid_m",
    "clinic_sites_1000m",
    "park_proximity_euclid_m",
)
COST_FEATURES = frozenset((FEATURES[0], FEATURES[1], FEATURES[4], FEATURES[6]))
SCENARIOS = {
    "campus_first": (0.40, 0.20, 0.10, 0.10, 0.05, 0.05, 0.10),
    "transit_first": (0.15, 0.35, 0.25, 0.10, 0.05, 0.05, 0.05),
    "lifestyle": (0.10, 0.10, 0.10, 0.20, 0.15, 0.15, 0.20),
    "balanced": (0.25, 0.15, 0.10, 0.15, 0.10, 0.10, 0.15),
}
DESTINATION_ID = "NUS_AS8"
DEPARTURE = "2026-10-19T08:00:00+08:00"
ANALYSIS_VERSION = "mcda-v1.0"
