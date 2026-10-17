"""Auditable housing sampling and Euclidean proximity preparation in EPSG:3414.

Preparation creates provisional measurements even when source review remains
outstanding. It never certifies residential use, public opening or operation.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
import pyogrio
import shapely
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from scipy.spatial import cKDTree

RAIL_OPERATION_REVIEW = {
    "version": "rail-operation-review-2026-10-17-v1",
    "reviewed_on": "2026-10-17",
    "analysis_date": "2026-10-19",
    "scope": "partial_station_review_not_full_station_or_exit_operation_certification",
    "excluded_station_names": ["MARINA SOUTH MRT STATION"],
    "exclusion_reason": "LTA ties opening to surrounding developments; opening date not advised",
    "evidence_url": (
        "https://www.lta.gov.sg/content/ltagov/en/upcoming_projects/rail_expansion/"
        "thomson_east_coast_line.html"
    ),
    "evidence_page_updated_on": "2026-07-07",
    "matching_rule": "exact station name after uppercase and whitespace normalisation",
    "scope_notes": [
        "Marina South Pier is a different station and is retained",
        "Mount Pleasant is also not yet open per LTA, but has no exit in this source",
        "CC30, CC31 and CC32 opened on 2026-07-12; retain their delivered exits",
        "Other retained exits, including LRT exits, are not individually certified operational",
        "Temporary entrance closures and full bus-stop operation are not covered by this review",
    ],
    "retained_circle_line_evidence_url": (
        "https://www.lta.gov.sg/content/ltagov/en/upcoming_projects/rail_expansion/"
        "circle_line_6.html"
    ),
}

SERVICE_ADDRESS_RULE_VERSION = "complete-service-address-v2"
SERVICE_ADDRESS_REVIEW = {
    "version": SERVICE_ADDRESS_RULE_VERSION,
    "grouping_fields": ["postal_code", "street_address", "floor", "unit"],
    "group_only_complete_usable_addresses": True,
    "invalid_unit_values": ["", "0"],
    "suspect_unit_rule": "all numeric with at least five digits",
    "incomplete_address_policy": "retain separate licence-keyed unresolved site",
    "missing_licence_policy": "retain separate source-row-keyed unresolved site",
    "free_text_building_name_policy": "do not infer floor or unit",
    "coordinate_policy": "same coordinates alone do not establish a duplicate site",
    "coordinate_choice": "lexically first licence then source row within complete address",
    "review_trigger_coordinate_spread_m": 20,
}


def filter_rail_exits(
    source_exits: gpd.GeoDataFrame,
) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    """Remove identified unopened stations and retain a complete source audit.

    A partial official-source review does not certify every retained station
    or exit. The frozen rule and evidence travel with the prepared dataset.
    """
    if "STATION_NA" not in source_exits:
        raise ValueError("Rail operation filtering requires the source station-name field")
    audit = source_exits.copy()
    normalised = audit.STATION_NA.map(_normalise_text)
    excluded = normalised.isin(RAIL_OPERATION_REVIEW["excluded_station_names"])
    audit["included_in_proximity"] = ~excluded
    audit["operation_review_status"] = np.where(
        excluded, "excluded_known_not_open", "retained_not_fully_operation_verified",
    )
    audit["operation_evidence_url"] = np.where(
        excluded, RAIL_OPERATION_REVIEW["evidence_url"], "",
    )
    audit["operation_review_version"] = RAIL_OPERATION_REVIEW["version"]
    return audit.loc[~excluded].copy(), audit


def _require_projected(frame: gpd.GeoDataFrame) -> None:
    if frame.crs is None or frame.crs.to_epsg() != 3414:
        raise ValueError("Spatial measurements require EPSG:3414")


def assign_subzones(
    residences: gpd.GeoDataFrame, subzones: gpd.GeoDataFrame,
) -> tuple[gpd.GeoDataFrame, pd.DataFrame]:
    """Assign intersecting polygons, preferring strict interior then lexical ID.

    Boundary and overlapping-polygon cases expose all choices in the audit.
    Outside points stay unassigned; there is no nearest-area extrapolation.
    """
    _require_projected(residences)
    _require_projected(subzones)
    joined = gpd.sjoin(
        residences[["building_id", "geometry"]],
        subzones[["area_id", "area_name", "geometry"]],
        how="left", predicate="intersects",
    ).reset_index(names="source_index")
    joined["strict_interior"] = False
    matched = joined.index_right.notna()
    joined.loc[matched, "strict_interior"] = [
        point.within(subzones.loc[polygon_index, "geometry"])
        for point, polygon_index in zip(
            joined.loc[matched, "geometry"], joined.loc[matched, "index_right"],
        )
    ]
    joined = joined.sort_values(
        ["building_id", "strict_interior", "area_id"], ascending=[True, False, True],
    )
    selected = joined.drop_duplicates("building_id").set_index("building_id")
    assigned = residences.copy()
    assigned["area_id"] = assigned.building_id.map(selected.area_id).where(
        assigned.building_id.map(selected.area_id).notna(), None,
    )
    assigned["area_name"] = assigned.building_id.map(selected.area_name).where(
        assigned.building_id.map(selected.area_name).notna(), None,
    )
    candidates = joined.groupby("building_id").area_id.agg(
        lambda values: "|".join(sorted(values.dropna().astype(str).unique())),
    )
    counts = joined.groupby("building_id").area_id.count()
    selected["candidate_area_ids"] = candidates
    selected["candidate_count"] = counts
    selected["assignment_method"] = np.select(
        [selected.area_id.isna(), selected.strict_interior, counts.gt(1)],
        ["outside_all_subzones", "strict_interior", "intersects_lexical_tie"],
        default="boundary_single",
    )
    audit = selected.reset_index()[[
        "building_id", "area_id", "candidate_area_ids", "candidate_count",
        "assignment_method",
    ]]
    return assigned, audit


def sample_residences(
    residences: gpd.GeoDataFrame, grid_size_m: float = 400, cluster_radius_m: float = 150,
) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame, pd.DataFrame]:
    """Build full-point connected components and frozen A/B real-building samples.

    A selects one point nearest each occupied cell centre within each Subzone.
    B adds the nearest member to the point centroid of every cluster missing A.
    Stable building IDs resolve equal distances, independently of input order.
    """
    _require_projected(residences)
    if not np.isfinite([grid_size_m, cluster_radius_m]).all():
        raise ValueError("Grid and radius must be finite")
    if grid_size_m <= 0 or cluster_radius_m <= 0:
        raise ValueError("Grid and radius must be positive")
    if residences.building_id.duplicated().any() or residences.area_id.isna().any():
        raise ValueError("Sampling requires unique building IDs and assigned Subzones")
    if residences.empty:
        raise ValueError("Sampling requires at least one eligible residential record")
    members = residences.sort_values("building_id").reset_index(drop=True).copy()
    members["cluster_id"] = ""
    members["cluster_name"] = ""
    summaries = []
    for area_id, area in members.groupby("area_id", sort=True):
        xy = np.column_stack([area.geometry.x, area.geometry.y])
        pairs = cKDTree(xy).query_pairs(cluster_radius_m, output_type="ndarray")
        graph = coo_matrix(
            (np.ones(len(pairs), dtype=np.uint8), (pairs[:, 0], pairs[:, 1])),
            shape=(len(area), len(area)),
        ).tocsr()
        _, labels = connected_components(graph, directed=False)
        for label in np.unique(labels):
            cluster = area.iloc[np.flatnonzero(labels == label)]
            digest = hashlib.sha256("|".join(cluster.building_id).encode()).hexdigest()[:12]
            cluster_id = f"{area_id}_C_{digest}"
            cluster_name = f"{cluster.area_name.iloc[0]} · analysis cluster {digest}"
            members.loc[cluster.index, "cluster_id"] = cluster_id
            members.loc[cluster.index, "cluster_name"] = cluster_name
            bounds = cluster.total_bounds
            summaries.append({
                "cluster_id": cluster_id, "cluster_name": cluster_name,
                "area_id": area_id, "area_name": cluster.area_name.iloc[0],
                "n_buildings": len(cluster), "singleton": len(cluster) == 1,
                "extent_diagonal_m": float(np.hypot(bounds[2]-bounds[0], bounds[3]-bounds[1])),
                "housing_type_counts": json.dumps(
                    cluster.housing_type.value_counts().sort_index().to_dict(), sort_keys=True,
                ),
            })
    members["grid_x"] = np.floor(members.geometry.x / grid_size_m).astype(int)
    members["grid_y"] = np.floor(members.geometry.y / grid_size_m).astype(int)
    members["distance_to_grid_center_m"] = np.hypot(
        members.geometry.x - (members.grid_x + 0.5)*grid_size_m,
        members.geometry.y - (members.grid_y + 0.5)*grid_size_m,
    )
    baseline = members.sort_values(
        ["area_id", "grid_x", "grid_y", "distance_to_grid_center_m", "building_id"],
    ).drop_duplicates(["area_id", "grid_x", "grid_y"])
    members["sample_A"] = members.building_id.isin(baseline.building_id)
    supplemented = []
    covered = set(baseline.cluster_id)
    for cluster_id, cluster in members.groupby("cluster_id", sort=True):
        if cluster_id in covered:
            continue
        distance = np.hypot(
            cluster.geometry.x - cluster.geometry.x.mean(),
            cluster.geometry.y - cluster.geometry.y.mean(),
        )
        supplemented.append(cluster.assign(distance=distance).sort_values(
            ["distance", "building_id"],
        ).building_id.iloc[0])
    locations = members[
        members.sample_A | members.building_id.isin(supplemented)
    ].sort_values("building_id").copy()
    locations["location_id"] = "LOC_" + locations.building_id
    locations["selection_reason"] = np.where(
        locations.sample_A, "400m_cell_subzone_nearest_center", "missing_cluster_nearest_centroid",
    )
    locations["x_3414"] = locations.geometry.x
    locations["y_3414"] = locations.geometry.y
    wgs = locations.to_crs(4326)
    locations["latitude"] = wgs.geometry.y
    locations["longitude"] = wgs.geometry.x
    summaries_frame = pd.DataFrame(summaries).sort_values("cluster_id").reset_index(drop=True)
    summaries_frame["n_sample_A"] = summaries_frame.cluster_id.map(
        locations.loc[locations.sample_A].cluster_id.value_counts(),
    ).fillna(0).astype(int)
    summaries_frame["n_sample_B"] = summaries_frame.cluster_id.map(
        locations.cluster_id.value_counts(),
    ).fillna(0).astype(int)
    return members, locations.reset_index(drop=True), summaries_frame


def measure_static_indicators(
    origins: gpd.GeoDataFrame, facilities: dict[str, gpd.GeoDataFrame],
) -> pd.DataFrame:
    """Measure six static proxies; empty source layers remain unknown, not zero.

    Park distance is distance to polygon (zero inside), not distance to entrance.
    Radius counts include an exactly-on-radius service site.
    """
    _require_projected(origins)
    result = pd.DataFrame(origins.drop(columns="geometry")).reset_index(drop=True)
    xy = np.column_stack([origins.geometry.x, origins.geometry.y])
    measures = {
        "rail": ("rail_exit_euclid_m", None),
        "bus": ("bus_stops_800m", 800),
        "supermarket": ("supermarket_sites_800m", 800),
        "library": ("library_euclid_m", None),
        "clinic": ("clinic_sites_1000m", 1000),
    }
    for source, (feature, radius) in measures.items():
        points = facilities[source]
        _require_projected(points)
        if points.empty:
            result[feature] = np.nan
            continue
        tree = cKDTree(np.column_stack([points.geometry.x, points.geometry.y]))
        result[feature] = (
            tree.query(xy)[0] if radius is None else
            tree.query_ball_point(xy, r=radius, return_length=True)
        )
    parks = facilities["park"]
    _require_projected(parks)
    if parks.empty:
        result["park_proximity_euclid_m"] = np.nan
    else:
        union = shapely.union_all(parks.geometry.array)
        result["park_proximity_euclid_m"] = shapely.distance(origins.geometry.array, union)
    return result


def _postal(values: pd.Series) -> pd.Series:
    text = values.astype("string").str.strip().str.replace(r"\.0$", "", regex=True)
    return text.where(text.str.fullmatch(r"\d{1,6}", na=False)).str.zfill(6)


def _normalise_text(value: Any) -> str:
    if pd.isna(value):
        return ""
    text = re.sub(r"\s+", " ", str(value).strip().upper())
    return "" if text in {"NA", "N/A", "NONE", "NULL", "NAN"} else text


def _description_fields(description: object) -> dict[str, str]:
    return {
        _normalise_text(html.unescape(key)): _normalise_text(html.unescape(value))
        for key, value in re.findall(
            r"<th[^>]*>(.*?)</th>\s*<td[^>]*>(.*?)</td>", str(description), re.DOTALL,
        )
    }


def _read_layer(path: Path, layer: str | None = None) -> gpd.GeoDataFrame:
    frame = pyogrio.read_dataframe(path, layer=layer)
    if frame.crs is None:
        raise ValueError(f"Unknown CRS: {path.name}/{layer}")
    frame.geometry = shapely.force_2d(frame.geometry.array)
    return frame.to_crs(3414).reset_index(drop=True)


def _repair_polygons(frame: gpd.GeoDataFrame, source: str) -> tuple[gpd.GeoDataFrame, list]:
    repaired = frame.copy()
    audits = []
    for index in frame.index[~frame.geometry.is_valid]:
        before = frame.loc[index, "geometry"]
        after = shapely.make_valid(before)
        if after.geom_type == "GeometryCollection":
            after = shapely.union_all([
                part for part in after.geoms if part.geom_type in {"Polygon", "MultiPolygon"}
            ])
        repaired.loc[index, "geometry"] = after
        audits.append({
            "source": source, "source_row": int(index),
            "before_type": before.geom_type, "after_type": after.geom_type,
            "valid_after": after.is_valid, "area_before_m2": before.area,
            "area_after_m2": after.area,
        })
    if repaired.geometry.is_empty.any() or not repaired.geometry.is_valid.all():
        raise ValueError(f"Polygon repair left unusable geometries: {source}")
    return repaired, audits


def group_service_addresses(
    frame: gpd.GeoDataFrame, source: str,
) -> tuple[gpd.GeoDataFrame, pd.DataFrame]:
    """Group licences only when complete service-unit addresses establish identity.

    Missing or suspect floor/unit fields retain each licence as an unresolved
    site. Free-text building names are not guessed into structured unit fields.
    Different licences sharing geocoded coordinates remain separate unless a
    complete reliable address provides evidence for grouping.
    """
    _require_projected(frame)
    if source not in {"clinic", "supermarket"}:
        raise ValueError("Service-address source must be clinic or supermarket")
    entries = []
    for index, row in frame.iterrows():
        if source == "clinic":
            fields = _description_fields(row.Description)
            postal = _postal(pd.Series([row.Postal_Code])).iloc[0]
            street_address = _normalise_text(row.Clinic_Address)
            floor = fields.get("FLOOR_NO", "")
            unit = fields.get("UNIT_NO", "")
            licence = _normalise_text(row.Clinic_ID)
            precision = "source_clinic_point"
        else:
            postal = _postal(pd.Series([row.postal_code])).iloc[0]
            street_address = " ".join(filter(None, [
                _normalise_text(row.block_house_num), _normalise_text(row.street_name),
            ]))
            floor, unit = _normalise_text(row.level_num), _normalise_text(row.unit_num)
            licence = _normalise_text(row.licence_num)
            precision = _normalise_text(row.match_status)
        reliable = pd.notna(postal) and bool(street_address)
        review_flags = []
        if not reliable:
            review_flags.append("missing_postal_or_street_address")
        if not floor:
            review_flags.append("floor_missing")
        if not unit or unit == "0":
            review_flags.append("unit_missing_or_placeholder")
        if unit.isdigit() and len(unit) >= 5:
            review_flags.append("long_numeric_unit_possible_spreadsheet_conversion")
        if source == "supermarket" and precision != "MATCHED":
            review_flags.append("geocoding_precision_requires_review")
        complete_address = (
            reliable and bool(floor) and bool(unit) and unit != "0"
            and not (unit.isdigit() and len(unit) >= 5)
        )
        address_key = "|".join([str(postal), street_address, floor, unit]) if reliable else ""
        unresolved_key = f"unresolved_licence_{licence}" if licence else f"unresolved_row_{index}"
        key = address_key if complete_address else unresolved_key
        site_id = f"{source}_" + hashlib.sha256(key.encode()).hexdigest()[:16]
        entries.append({
            "source_row": index, "licence_id": licence, "site_id": site_id,
            "postal_code": postal, "street_address": street_address,
            "floor": floor, "unit": unit, "address_key": address_key,
            "dedupe_status": "full_address_grouped" if complete_address else "unresolved_retained",
            "coordinate_precision": precision,
            "address_review_flags": "|".join(review_flags),
        })
    mapping = pd.DataFrame(entries)
    joined = frame.join(mapping.set_index("source_row")[["site_id"]])
    site_rows = []
    for site_id, records in joined.groupby("site_id", sort=True):
        spread = np.hypot(
            records.geometry.x.max()-records.geometry.x.min(),
            records.geometry.y.max()-records.geometry.y.min(),
        )
        ordered = mapping[mapping.site_id == site_id].sort_values(["licence_id", "source_row"])
        chosen = int(ordered.source_row.iloc[0])
        site_rows.append({
            "site_id": site_id, "n_licences": len(records),
            "coordinate_spread_m": float(spread),
            "coordinate_review_required": spread > 20,
            "geometry": frame.loc[chosen, "geometry"],
        })
    sites = gpd.GeoDataFrame(site_rows, geometry="geometry", crs=3414)
    mapping = mapping.merge(
        sites.drop(columns="geometry"), on="site_id", validate="many_to_one",
    )
    return sites, mapping


def _write_csv(frame: pd.DataFrame, path: Path) -> None:
    pd.DataFrame(frame.drop(columns="geometry", errors="ignore")).to_csv(
        path, index=False, encoding="utf-8-sig", float_format="%.15g",
    )


def prepare_data(data_root: Path, output_dir: Path) -> dict:
    """Read the unchanged A/B handover and emit real, provisional spatial inputs.

    The 107 overlapping postal-code pairs are held out pending source review.
    Outstanding use/category/operation checks are returned as readiness blockers,
    while usable geometry and six static indicators are still prepared.
    """
    data_root, output_dir = Path(data_root), Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    audits_dir = output_dir / "audits"
    audits_dir.mkdir(exist_ok=True)
    gdb = data_root / "GE5219_Indicators.gdb"
    handover = data_root / "GE5219_B_Handover"
    csv_path = handover / "01_Data" / "Residential_Accessibility_API.csv"
    master = pd.read_csv(csv_path, dtype="string")
    if master.Residential_ID.isna().any() or master.Residential_ID.duplicated().any():
        raise ValueError("B Residential_ID is missing or duplicated")
    master["source_layer"] = np.where(master.Residential_Type.eq("HDB"), "HDB_Point", "Dwelling")
    master["postal_code"] = _postal(master.POSTAL_COD.fillna(master.POSTALCODE))
    master["source_object_id"] = pd.to_numeric(master.OBJECTID_1).astype("Int64").astype(str)
    master["building_id"] = [
        "BLD_" + hashlib.sha256(f"{layer}|{oid}|{postal}".encode()).hexdigest()[:20]
        for layer, oid, postal in zip(master.source_layer, master.source_object_id, master.postal_code)
    ]
    if master.building_id.duplicated().any():
        raise ValueError("Source-derived building IDs are duplicated")
    master["source_residential_id"] = master.Residential_ID
    master["housing_type"] = master.PROP_TYPE.where(master.source_layer.eq("Dwelling"), "HDB")
    master["housing_type"] = master.housing_type.fillna("Unknown")
    master["coordinate_source"] = "B_frozen_handover_csv"
    master["residential_use_status"] = "source_classification_only_review_required"
    conflict = master.postal_code.notna() & master.postal_code.duplicated(keep=False)
    master["postal_conflict"] = conflict
    longitude = pd.to_numeric(master.Longitude, errors="coerce")
    latitude = pd.to_numeric(master.Latitude, errors="coerce")
    coordinates_ok = longitude.between(103, 105) & latitude.between(0.8, 1.7)
    buildings = gpd.GeoDataFrame(
        master.drop(columns=["Longitude", "Latitude"]),
        geometry=gpd.points_from_xy(longitude, latitude), crs=4326,
    ).to_crs(3414)
    attributes = []
    for layer, postcode in [("HDB_Point", "POSTAL_COD"), ("Dwelling", "POSTALCODE")]:
        source = _read_layer(gdb, layer)
        attributes.append(pd.DataFrame({
            "source_layer": layer,
            "source_object_id": pd.to_numeric(source.OBJECTID_1).astype("Int64").astype(str),
            "a_postal_code": _postal(source[postcode]),
            "a_inc_crc": source.INC_CRC,
            "a_x_3414": source.geometry.x, "a_y_3414": source.geometry.y,
        }))
    source_map = pd.concat(attributes, ignore_index=True)
    buildings = buildings.merge(
        source_map, on=["source_layer", "source_object_id"], how="left", validate="one_to_one",
    )
    buildings["a_coordinate_difference_m"] = np.hypot(
        buildings.geometry.x-buildings.a_x_3414, buildings.geometry.y-buildings.a_y_3414,
    )
    buildings["source_mapping_valid"] = (
        buildings.a_postal_code.eq(buildings.postal_code).fillna(False)
        & buildings.a_inc_crc.eq(buildings.INC_CRC).fillna(False)
    )
    subzones, repair_audit = _repair_polygons(_read_layer(gdb, "Subzone"), "Subzone")
    subzones = subzones.rename(columns={"SUBZONE_C": "area_id", "SUBZONE_N": "area_name"})
    if subzones.area_id.isna().any() or subzones.area_id.duplicated().any():
        raise ValueError("Subzone codes must be present and unique")
    buildings, assignment_audit = assign_subzones(buildings, subzones)
    buildings["candidate_included"] = (
        ~buildings.postal_conflict & buildings.source_mapping_valid & coordinates_ok
        & buildings.area_id.notna() & buildings.housing_type.isin(["HDB", "Landed", "Non-Landed", "EC"])
    )
    _write_csv(buildings.loc[conflict], audits_dir / "postal_conflicts.csv")
    _write_csv(buildings.loc[~buildings.candidate_included], audits_dir / "held_out_residences.csv")
    _write_csv(assignment_audit, audits_dir / "subzone_assignments.csv")
    membership, locations, clusters = sample_residences(
        buildings.loc[buildings.candidate_included].copy(),
    )
    for column in ["cluster_id", "cluster_name", "sample_A", "grid_x", "grid_y"]:
        buildings[column] = buildings.building_id.map(membership.set_index("building_id")[column])
    parks, park_repairs = _repair_polygons(_read_layer(gdb, "Parks_and_Nature"), "Parks_and_Nature")
    park_review = parks.drop(columns="geometry").copy()
    park_review["included_provisionally"] = ~parks.N_RESERVE.eq(1)
    park_review["category_review_status"] = np.where(
        parks.N_RESERVE.eq(1), "excluded_source_N_RESERVE_flag",
        "non_reserve_source_category_review_required",
    )
    park_review["opening_status"] = "not_verified"
    _write_csv(park_review, audits_dir / "park_category_review.csv")
    clinics, clinic_map = group_service_addresses(_read_layer(gdb, "Healthcare"), "clinic")
    supermarkets, supermarket_map = group_service_addresses(
        _read_layer(gdb, "Supermarket"), "supermarket",
    )
    _write_csv(clinic_map, audits_dir / "clinic_licence_site_mapping.csv")
    _write_csv(supermarket_map, audits_dir / "supermarket_licence_site_mapping.csv")
    rail_source = _read_layer(handover / "03_GIS" / "MRT_Station_Exits.gpkg")
    rail, rail_review = filter_rail_exits(rail_source)
    bus = _read_layer(handover / "03_GIS" / "BusStop_Points.gpkg")
    bus["operation_review_status"] = "not_available_in_source_review_required"
    _write_csv(rail_review, audits_dir / "rail_operation_review.csv")
    _write_csv(bus, audits_dir / "bus_operation_review.csv")
    facilities = {
        "rail": rail, "bus": bus, "supermarket": supermarkets,
        "library": _read_layer(gdb, "Library"), "clinic": clinics,
        "park": parks.loc[~parks.N_RESERVE.eq(1)].copy(),
    }
    static = measure_static_indicators(locations, facilities)
    static["source_review_status"] = "provisional_review_required"
    _write_csv(locations, output_dir / "analysis_locations.csv")
    _write_csv(static, output_dir / "static_indicators.csv")
    _write_csv(membership[[
        "building_id", "area_id", "area_name", "cluster_id", "cluster_name", "housing_type",
    ]], output_dir / "cluster_membership.csv")
    _write_csv(clusters, output_dir / "clusters.csv")
    _write_csv(buildings[[
        "building_id", "source_residential_id", "source_layer", "source_object_id", "postal_code",
        "a_postal_code", "a_inc_crc", "source_mapping_valid", "a_coordinate_difference_m",
        "housing_type", "candidate_included", "coordinate_source", "residential_use_status",
    ]], audits_dir / "building_source_mapping.csv")
    _write_csv(pd.DataFrame(repair_audit + park_repairs), audits_dir / "geometry_repairs.csv")
    buildings.to_file(output_dir / "buildings.gpkg", layer="buildings", driver="GPKG")
    locations.to_file(output_dir / "analysis_locations.gpkg", layer="analysis_locations", driver="GPKG")
    subzones[["area_id", "area_name", "geometry"]].to_crs(4326).to_file(
        output_dir / "subzones.geojson", driver="GeoJSON",
    )
    baseline = locations.loc[locations.sample_A]
    unique_positions = locations[["latitude", "longitude"]].drop_duplicates()
    previous_comparison = static[["location_id", "source_residential_id"]].copy()
    previous_comparison["rail_recalculated_m"] = static.rail_exit_euclid_m
    rail_tree_raw = cKDTree(np.column_stack([rail_source.geometry.x, rail_source.geometry.y]))
    unfiltered_distance = rail_tree_raw.query(
        np.column_stack([locations.geometry.x, locations.geometry.y]),
    )[0]
    previous_comparison["rail_unfiltered_recalculated_m"] = unfiltered_distance
    previous_comparison["rail_operation_filter_difference_m"] = (
        previous_comparison.rail_recalculated_m - unfiltered_distance
    )
    previous_comparison["rail_handover_m"] = pd.to_numeric(static.Nearest_MRT_Exit_m)
    previous_comparison["rail_unfiltered_handover_difference_m"] = (
        unfiltered_distance - previous_comparison.rail_handover_m
    )
    previous_comparison["rail_difference_m"] = (
        previous_comparison.rail_recalculated_m-previous_comparison.rail_handover_m
    )
    previous_comparison["bus_recalculated"] = static.bus_stops_800m
    previous_comparison["bus_handover"] = pd.to_numeric(static.BusStop_Count_800)
    previous_comparison["bus_difference"] = (
        previous_comparison.bus_recalculated-previous_comparison.bus_handover
    )
    _write_csv(previous_comparison, audits_dir / "python_vs_handover_transit.csv")
    source_paths = [csv_path] + sorted(gdb.glob("*")) + [
        handover / "03_GIS" / "MRT_Station_Exits.gpkg",
        handover / "03_GIS" / "BusStop_Points.gpkg",
    ]
    source_manifest = {
        path.relative_to(data_root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in source_paths if path.is_file() and path.suffix.lower() != ".lock"
    }
    operation_config_text = json.dumps(RAIL_OPERATION_REVIEW, sort_keys=True, indent=2) + "\n"
    operation_config_sha256 = hashlib.sha256(operation_config_text.encode()).hexdigest()
    (output_dir / "transit_operation.json").write_bytes(operation_config_text.encode())
    source_manifest["analysis_config/transit_operation.json"] = operation_config_sha256
    address_config_text = json.dumps(SERVICE_ADDRESS_REVIEW, sort_keys=True, indent=2) + "\n"
    address_config_sha256 = hashlib.sha256(address_config_text.encode()).hexdigest()
    (output_dir / "service_address_rules.json").write_bytes(address_config_text.encode())
    source_manifest["analysis_config/service_address_rules.json"] = address_config_sha256
    dataset_version = hashlib.sha256(
        json.dumps(source_manifest, sort_keys=True).encode(),
    ).hexdigest()
    (output_dir / "source_manifest.json").write_text(
        json.dumps(source_manifest, indent=2), encoding="utf-8",
    )
    quality = {
        "status": "provisional_review_required", "production_ready": False,
        "dataset_version": dataset_version,
        "source_records": len(buildings), "candidate_records": len(membership),
        "held_out_records": int((~buildings.candidate_included).sum()),
        "conflict_records": int(conflict.sum()),
        "conflict_postal_codes": int(buildings.loc[conflict, "postal_code"].nunique()),
        "source_mapping_failures": int((~buildings.source_mapping_valid).sum()),
        "outside_subzones": int(buildings.area_id.isna().sum()),
        "area_count": int(locations.area_id.nunique()), "cluster_count": len(clusters),
        "singleton_clusters": int(clusters.singleton.sum()),
        "sample_A_count": len(baseline), "sample_B_count": len(locations),
        "supplement_count": len(locations)-len(baseline),
        "unique_route_origins_B": len(unique_positions),
        "unique_route_origins_A": len(baseline[["latitude", "longitude"]].drop_duplicates()),
        "request_count_semantics": "one initial query per unique origin for one frozen scenario; retries extra",
        "grid_size_m": 400, "grid_origin_3414": [0, 0], "cluster_radius_m": 150,
        "park_source_records": len(parks), "nature_reserves_excluded": int(parks.N_RESERVE.eq(1).sum()),
        "park_candidate_records": len(facilities["park"]),
        "clinic_source_records": len(clinic_map), "clinic_sites": len(clinics),
        "supermarket_source_records": len(supermarket_map), "supermarket_sites": len(supermarkets),
        "clinic_address_review_records": int(clinic_map.address_review_flags.ne("").sum()),
        "supermarket_address_review_records": int(supermarket_map.address_review_flags.ne("").sum()),
        "bus_source_records": len(bus), "rail_exit_source_records": len(rail_source),
        "rail_exit_candidate_records": len(rail),
        "rail_exits_excluded_known_not_open": len(rail_source)-len(rail),
        "rail_operation_filter_changed_points": int(
            previous_comparison.rail_operation_filter_difference_m.abs().gt(1e-8).sum(),
        ),
        "rail_operation_filter_max_distance_change_m": float(
            previous_comparison.rail_operation_filter_difference_m.abs().max(),
        ),
        "rail_operation_review": RAIL_OPERATION_REVIEW,
        "transit_operation_config_sha256": operation_config_sha256,
        "geometry_repairs": repair_audit + park_repairs,
        "readiness_blockers": [
            f"{buildings.loc[conflict, 'postal_code'].nunique()} postal conflicts require adjudication; held-out records excluded",
            "Residential use is source-classification evidence only; independent use review outstanding",
            "Identified unopened station excluded; remaining rail exits and bus stops still need operation review",
            "Non-reserve park/corridor categories and public opening require review; distances provisional",
            "Facility address precision, licence grouping and coordinate spread need sample review",
            "Destination review, public-transit coverage and independent route evidence are tracked separately from static preparation",
        ],
        "facility_units": (
            "complete postal+street+floor+unit groups; incomplete addresses retained by licence"
        ),
        "service_address_rule_version": SERVICE_ADDRESS_RULE_VERSION,
        "service_address_config_sha256": address_config_sha256,
        "clinic_unresolved_sites": int(
            clinic_map.loc[clinic_map.dedupe_status.eq("unresolved_retained"), "site_id"].nunique(),
        ),
        "supermarket_unresolved_sites": int(
            supermarket_map.loc[
                supermarket_map.dedupe_status.eq("unresolved_retained"), "site_id",
            ].nunique(),
        ),
        "coordinate_semantics": "B coordinates retained; A coordinate differences audited, never overwritten",
        "source_csv_sha256": hashlib.sha256(csv_path.read_bytes()).hexdigest(),
        "measurement_labels": {
            "rail_exit_euclid_m": "Euclidean proximity after identified-closed exclusion; remaining operation not fully verified",
            "bus_stops_800m": "Euclidean stop-point count, not routes/frequency, operation unverified",
            "park_proximity_euclid_m": "polygon proximity; inside zero; not entrance/network access",
        },
    }
    (output_dir / "data_quality.json").write_text(
        json.dumps(quality, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    return quality
