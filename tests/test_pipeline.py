"""The public matrix boundary rejects mixed routing scenes and preserves failures."""

import pandas as pd
import pytest

from ge5219.pipeline import assemble_matrix
from ge5219.settings import DEPARTURE


def test_matrix_retains_planned_points_without_routes_and_rejects_other_destinations():
    static = pd.DataFrame({"location_id": ["a", "b"], "latitude": [1.3, 1.31],
                           "longitude": [103.7, 103.71]})
    routes = pd.DataFrame({
        "location_id": ["a"], "origin_lat": [1.3], "origin_lon": [103.7],
        "latitude": [1.3], "longitude": [103.7],
        "destination_id": ["NUS_AS8"], "destination_lat": [1.296],
        "destination_lon": [103.772], "departure": [DEPARTURE], "mode": ["TRANSIT"],
        "route_status": ["Success"], "campus_transit_min": [35.0],
    })
    frame = assemble_matrix(static, routes, {"destination_id": "NUS_AS8", "latitude": 1.296,
                                             "longitude": 103.772})
    assert frame.location_id.tolist() == ["a", "b"]
    assert pd.isna(frame.loc[1, "campus_transit_min"])
    assert frame.loc[1, "route_status"] == "Not_Requested"
    assert frame.destination_id.tolist() == ["NUS_AS8", "NUS_AS8"]
    routes["destination_id"] = "NTU"
    with pytest.raises(ValueError, match="destination"):
        assemble_matrix(static, routes, {"destination_id": "NUS_AS8", "latitude": 1.296,
                                         "longitude": 103.772})
