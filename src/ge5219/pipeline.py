"""Join measured routes to the frozen planned sample without losing unknowns."""

from typing import Any

import numpy as np
import pandas as pd

from .settings import DEPARTURE


def assemble_matrix(
    static: pd.DataFrame, routes: pd.DataFrame, destination: dict[str, Any],
    departure: str = DEPARTURE,
) -> pd.DataFrame:
    """Validate route context, then left-join all planned analysis locations.

    Imported demo times cannot pass this boundary without explicit matching
    origin, destination and departure provenance. Unqueried points stay unknown.
    """
    required = {"location_id", "origin_lat", "origin_lon", "destination_id", "destination_lat",
                "destination_lon", "departure", "mode", "route_status", "campus_transit_min"}
    if required - set(routes.columns):
        raise ValueError(f"Routes lack provenance fields: {sorted(required - set(routes.columns))}")
    for frame in (static, routes):
        if frame.location_id.isna().any() or frame.location_id.duplicated().any():
            raise ValueError("Duplicate or missing location_id")
    if not set(routes.location_id).issubset(set(static.location_id)):
        raise ValueError("Routes include locations outside the frozen sample")
    expected = {
        "destination_id": destination["destination_id"], "destination_lat": destination["latitude"],
        "destination_lon": destination["longitude"], "departure": departure, "mode": "TRANSIT",
    }
    for field, value in expected.items():
        if not routes[field].eq(value).all():
            raise ValueError(f"Mismatched route {field}; do not mix routing scenarios")
    matched = routes[["location_id", "origin_lat", "origin_lon"]].merge(
        static[["location_id", "latitude", "longitude"]], on="location_id", validate="one_to_one")
    if not (matched.origin_lat.eq(matched.latitude) & matched.origin_lon.eq(matched.longitude)).all():
        raise ValueError("Route origin differs from the frozen location coordinates")
    numeric = pd.to_numeric(routes.campus_transit_min, errors="coerce")
    success = routes.route_status.eq("Success")
    if (success & (~np.isfinite(numeric) | numeric.lt(0))).any():
        raise ValueError("Success routes must contain finite nonnegative transit minutes")
    if "campus_transit_min" in static or "route_status" in static:
        raise ValueError("Static matrix already contains routes; refuse ambiguous overwrite")
    route_columns = [column for column in routes if column == "location_id" or column not in static]
    frame = static.merge(routes[route_columns], on="location_id", how="left", validate="one_to_one")
    for field, value in expected.items():
        frame[field] = value
    frame["route_status"] = frame.route_status.fillna("Not_Requested")
    frame.loc[~frame.route_status.eq("Success"), "campus_transit_min"] = np.nan
    return frame
