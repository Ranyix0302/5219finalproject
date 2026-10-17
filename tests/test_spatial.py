"""Synthetic geometry tests for the approved public sampling and measurement seams."""

import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import Point, box

from ge5219.spatial import (
    SERVICE_ADDRESS_REVIEW,
    assign_subzones,
    filter_rail_exits,
    group_service_addresses,
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


def test_incomplete_clinic_addresses_keep_distinct_licences_and_complete_ones_merge():
    """Synthetic regression mirrors missing structured floors at different hospital levels."""
    descriptions = [
        ("<table><tr><th>FLOOR_NO</th><td></td></tr>"
         "<tr><th>UNIT_NO</th><td></td></tr></table>"),
        ("<table><tr><th>FLOOR_NO</th><td></td></tr>"
         "<tr><th>UNIT_NO</th><td></td></tr></table>"),
        ("<table><tr><th>FLOOR_NO</th><td>01</td></tr>"
         "<tr><th>UNIT_NO</th><td>02</td></tr></table>"),
        ("<table><tr><th>FLOOR_NO</th><td>01</td></tr>"
         "<tr><th>UNIT_NO</th><td>02</td></tr></table>"),
    ]
    clinics = gpd.GeoDataFrame(
        {"Clinic_ID": ["level12", "level2", "complete_b", "complete_a"],
         "Postal_Code": ["188770"] * 4,
         "Clinic_Address": ["585 NORTH BRIDGE ROAD"] * 4,
         "Building_Name": ["LEVEL 12 HOSPITAL", "LEVEL 2 HOSPITAL", "ANNEX", "ANNEX"],
         "Description": descriptions},
        geometry=[Point(0, 0), Point(0, 0), Point(20, 0), Point(19, 0)], crs=3414,
    )
    sites, mapping = group_service_addresses(clinics, "clinic")
    by_licence = mapping.set_index("licence_id")
    assert len(sites) == 3
    assert by_licence.loc["LEVEL12", "site_id"] != by_licence.loc["LEVEL2", "site_id"]
    assert by_licence.loc[["LEVEL12", "LEVEL2"], "dedupe_status"].eq(
        "unresolved_retained").all()
    assert by_licence.loc["COMPLETE_A", "site_id"] == by_licence.loc["COMPLETE_B", "site_id"]
    assert by_licence.loc["COMPLETE_A", "n_licences"] == 2
    grouped_site = sites.set_index("site_id").loc[by_licence.loc["COMPLETE_A", "site_id"]]
    assert grouped_site.geometry == Point(19, 0)
    assert grouped_site.coordinate_spread_m == 1
    assert set(mapping.source_row) == {0, 1, 2, 3}


def test_placeholder_or_converted_supermarket_units_cannot_establish_duplicate_address():
    supermarkets = gpd.GeoDataFrame(
        {"postal_code": ["123456"] * 4, "block_house_num": ["1"] * 4,
         "street_name": ["SYNTHETIC STREET"] * 4, "level_num": ["1"] * 4,
         "unit_num": ["0", "0", "42401", "42401"],
         "licence_num": ["a", "b", "c", "d"], "match_status": ["matched"] * 4},
        geometry=[Point(0, 0)] * 4, crs=3414,
    )
    sites, mapping = group_service_addresses(supermarkets, "supermarket")
    assert len(sites) == 4
    assert mapping.dedupe_status.eq("unresolved_retained").all()
    assert mapping.address_review_flags.ne("").all()


def test_service_address_configuration_matches_the_packaged_review_rule():
    path = Path(__file__).resolve().parents[1] / "config" / "service_address_rules.json"
    assert json.loads(path.read_text(encoding="utf-8")) == SERVICE_ADDRESS_REVIEW
