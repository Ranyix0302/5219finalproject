"""Synthetic geometry tests for the approved public sampling and measurement seams."""

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import Point, box

from ge5219.spatial import (
    assign_subzones,
    filter_rail_exits,
    measure_static_indicators,
    sample_residences,
)


def test_sampling_keeps_boundary_subzones_chains_and_uncovered_singletons():
    residences = gpd.GeoDataFrame(
        {
            "building_id": ["b4", "b2", "b1", "b3", "b5"],
            "housing_type": ["HDB"] * 5,
            "area_id": ["S1"] * 4 + ["S2"],
            "area_name": ["First"] * 4 + ["Second"],
        },
        geometry=[Point(350, 200), Point(200, 200), Point(50, 200),
                  Point(399, 399), Point(201, 200)],
        crs=3414,
    )
    members, locations, clusters = sample_residences(residences)
    first = members.set_index("building_id")
    assert first.loc["b1", "cluster_id"] == first.loc["b4", "cluster_id"]
    assert first.loc["b3", "cluster_id"] != first.loc["b1", "cluster_id"]
    assert first.loc["b5", "cluster_id"] != first.loc["b2", "cluster_id"]
    assert set(locations.loc[locations.sample_A, "building_id"]) == {"b2", "b5"}
    assert set(locations.building_id) == {"b2", "b3", "b5"}
    assert set(clusters.cluster_id) == set(locations.cluster_id)
    _, shuffled, _ = sample_residences(residences.sample(frac=1, random_state=42))
    assert locations.drop(columns="geometry").to_dict("records") == shuffled.drop(
        columns="geometry").to_dict("records")


def test_boundary_assignment_uses_stable_id_and_audits_all_options():
    points = gpd.GeoDataFrame(
        {"building_id": ["edge", "inside", "outside"]},
        geometry=[Point(200, 100), Point(100, 100), Point(700, 700)], crs=3414,
    )
    areas = gpd.GeoDataFrame(
        {"area_id": ["S2", "S1"], "area_name": ["Second", "First"]},
        geometry=[box(200, 0, 400, 400), box(0, 0, 200, 400)], crs=3414,
    )
    assigned, audit = assign_subzones(points, areas)
    assert assigned.set_index("building_id").loc["edge", "area_id"] == "S1"
    assert pd.isna(assigned.set_index("building_id").loc["outside", "area_id"])
    edge = audit.set_index("building_id").loc["edge"]
    assert edge.candidate_area_ids == "S1|S2"
    assert edge.assignment_method == "intersects_lexical_tie"


def test_nearest_grid_center_tie_uses_stable_building_id():
    residences = gpd.GeoDataFrame(
        {"building_id": ["z", "a"], "housing_type": ["HDB", "Landed"],
         "area_id": ["S", "S"], "area_name": ["Area", "Area"]},
        geometry=[Point(210, 200), Point(190, 200)], crs=3414,
    )
    _, locations, _ = sample_residences(residences)
    assert locations.building_id.tolist() == ["a"]
    assert locations.sample_A.tolist() == [True]


def test_static_measures_preserve_true_zero_and_polygon_interior_distance():
    origins = gpd.GeoDataFrame(
        {"location_id": ["a", "b"]}, geometry=[Point(0, 0), Point(2000, 0)], crs=3414,
    )
    facilities = {
        "rail": gpd.GeoDataFrame(geometry=[Point(3, 4)], crs=3414),
        "bus": gpd.GeoDataFrame(geometry=[Point(800, 0)], crs=3414),
        "supermarket": gpd.GeoDataFrame(geometry=[Point(0, 0)], crs=3414),
        "library": gpd.GeoDataFrame(geometry=[Point(0, 10)], crs=3414),
        "clinic": gpd.GeoDataFrame(geometry=[Point(1000, 0)], crs=3414),
        "park": gpd.GeoDataFrame(geometry=[box(-1, -1, 1, 1)], crs=3414),
    }
    measured = measure_static_indicators(origins, facilities)
    assert measured.loc[0, "rail_exit_euclid_m"] == 5
    assert measured.bus_stops_800m.tolist() == [1, 0]
    assert measured.clinic_sites_1000m.tolist() == [1, 1]
    assert measured.park_proximity_euclid_m.tolist() == [0, 1999]
    facilities["library"] = gpd.GeoDataFrame(geometry=[], crs=3414)
    incomplete = measure_static_indicators(origins, facilities)
    assert np.isnan(incomplete.library_euclid_m).all()


def test_known_closed_station_is_excluded_without_certifying_or_name_filtering_others():
    exits = gpd.GeoDataFrame(
        {"STATION_NA": ["MARINA SOUTH MRT STATION", "MARINA SOUTH PIER MRT STATION",
                        "CC30", "UNKNOWN LRT STATION"],
         "OBJECTID_1": [21568, 1, 2, 3]},
        geometry=[Point(0, 0), Point(3, 4), Point(10, 0), Point(12, 0)], crs=3414,
    )
    eligible, audit = filter_rail_exits(exits)
    assert eligible.OBJECTID_1.tolist() == [1, 2, 3]
    assert audit.included_in_proximity.tolist() == [False, True, True, True]
    assert audit.loc[0, "operation_review_status"] == "excluded_known_not_open"
    assert audit.loc[1:, "operation_review_status"].eq(
        "retained_not_fully_operation_verified").all()
    assert "lta.gov.sg" in audit.loc[0, "operation_evidence_url"]
    assert "STATION_NA" in eligible.columns
