"""Command-line entry points for reproducible, separately restartable stages."""

import argparse
import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pandas as pd

from .artifacts import read_locations, save_result, write_json
from .mcda import fit_normalization, recommend
from .pipeline import assemble_matrix
from .settings import ANALYSIS_VERSION, DEPARTURE, FEATURES, SCENARIOS


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _matrix_and_context(args: argparse.Namespace) -> tuple[pd.DataFrame, dict, dict]:
    from .routing import load_destination

    destination = load_destination(args.destination)
    static_path = args.prepared / "static_indicators.csv"
    static = read_locations(static_path)
    routes = read_locations(args.routes)
    frame = assemble_matrix(static, routes, asdict(destination))
    digest = hashlib.sha256(static_path.read_bytes()).hexdigest()
    quality_path = args.prepared / "data_quality.json"
    quality = _read_json(quality_path) if quality_path.exists() else {}
    metadata = {"dataset_version": quality.get("dataset_version", digest),
                "static_measurements_sha256": digest, "analysis_version": ANALYSIS_VERSION,
                "destination_id": destination.destination_id, "departure": DEPARTURE,
                "destination": asdict(destination), "data_quality": quality,
                "sampling_limit": "Real sampled positions, not measurements at every building",
                "source_routes_sha256": hashlib.sha256(args.routes.read_bytes()).hexdigest()}
    return frame, metadata, asdict(destination)


def _normalization(frame: pd.DataFrame, metadata: dict, path: Path) -> dict:
    baseline = frame.loc[frame.sample_A].copy()
    fingerprint = hashlib.sha256(pd.util.hash_pandas_object(
        baseline.sort_values("location_id")[["location_id", *FEATURES, "route_status"]],
        index=False).to_numpy().tobytes()).hexdigest()
    if path.exists():
        frozen = _read_json(path)
        if frozen.get("dataset_version") != metadata["dataset_version"]:
            raise ValueError("Normalization belongs to another dataset; create a new analysis version")
        if frozen.get("baseline_measurements_sha256") != fingerprint:
            raise ValueError("Frozen A measurements changed; explicitly version normalization")
        return frozen["parameters"]
    params = fit_normalization(baseline)
    write_json(path, {"parameters": params, "dataset_version": metadata["dataset_version"],
                       "baseline_measurements_sha256": fingerprint,
                       "fitted_on": "A", "quantiles": [.05, .95], "departure": DEPARTURE})
    return params


def _run_route(args: argparse.Namespace) -> dict[str, Any]:
    from .routing import OneMapClient, SQLiteRouteCache, load_destination, route_locations

    locations = read_locations(args.prepared / "analysis_locations.csv")
    destination = load_destination(args.destination)
    client = OneMapClient()
    with SQLiteRouteCache(args.cache) as cache:
        routes = route_locations(locations, destination, cache, client,
                                 max_requests=args.max_requests,
                                 retry_no_route=args.retry_no_route)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    routes.to_csv(args.output, index=False)
    return {"output": str(args.output), "n_planned": len(routes),
            "route_status_counts": routes.route_status.value_counts().to_dict()}


def _run_score(args: argparse.Namespace) -> dict:
    frame, metadata, _ = _matrix_and_context(args)
    params = _normalization(frame, metadata, args.normalization)
    metadata["sample_set"] = args.sample_set
    selected = frame.loc[frame.sample_A] if args.sample_set == "A" else frame
    weights: tuple[float, ...] = SCENARIOS[args.scenario]
    if args.weights:
        weights = tuple(float(value) for value in args.weights.split(","))
    result = recommend(selected, params, weights, group_by=args.group_by,
                       max_commute_min=args.max_commute_min, metadata=metadata)
    save_result(result, args.output)
    frame.to_csv(args.output / "indicator_matrix.csv", index=False)
    return result["metadata"]


def _run_experiments(args: argparse.Namespace) -> dict:
    import geopandas as gpd

    from .experiments import run_experiments

    frame, metadata, _ = _matrix_and_context(args)
    params = _normalization(frame, metadata, args.normalization)
    members = read_locations(args.prepared / "cluster_membership.csv")
    buildings = gpd.read_file(args.prepared / "buildings.gpkg").to_crs(3414)
    coordinates = pd.DataFrame({"building_id": buildings.building_id,
                                "x_3414": buildings.geometry.x, "y_3414": buildings.geometry.y})
    members = members.merge(coordinates, on="building_id", how="left", validate="one_to_one")
    return run_experiments(frame, params, args.output, building_membership=members, metadata=metadata)


def _run_status(args: argparse.Namespace) -> dict:
    quality_path = args.prepared / "data_quality.json"
    quality = _read_json(quality_path) if quality_path.exists() else {}
    destination = _read_json(args.destination)
    status: dict[str, Any] = {"stage": "spatial_prepared" if quality else "not_prepared",
                              "data_quality": quality,
                              "destination_reviewed": destination.get("reviewed") is True,
                              "routing_scene": DEPARTURE,
                              "result_metadata_path": str(args.result),
                              "seven_factor_result_bundle_available": args.result.exists()}
    if args.result.exists():
        result = _read_json(args.result)
        status["stored_result_status"] = result.get("status")
        status["stored_result_id"] = result.get("result_id")
    if args.routes and args.routes.exists():
        routes = read_locations(args.routes)
        status["route_status_counts"] = routes.route_status.value_counts().to_dict()
    return status


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="GE5219 reproducible GIS-MCDA stages")
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare", help="Build real housing samples and static indicators")
    prepare.add_argument("--data-root", type=Path, required=True)
    prepare.add_argument("--output", type=Path, default=Path("outputs/prepared"))
    prepare.set_defaults(handler=_run_prepare)
    report = commands.add_parser("report", help="Show actual spatial preparation evidence")
    report.add_argument("--prepared", type=Path, default=Path("outputs/prepared"))
    report.add_argument("--output", type=Path, default=Path("outputs/preparation_report.html"))
    report.set_defaults(handler=_run_report)
    for name, handler in (("route", _run_route), ("score", _run_score),
                           ("experiments", _run_experiments), ("status", _run_status)):
        command = commands.add_parser(name)
        command.add_argument("--prepared", type=Path, default=Path("outputs/prepared"))
        command.add_argument("--destination", type=Path, default=Path("config/destination.json"))
        command.set_defaults(handler=handler)
        if name in ("score", "experiments", "status"):
            command.add_argument("--routes", type=Path, required=name != "status")
        if name in ("score", "experiments"):
            command.add_argument("--normalization", type=Path,
                                 default=Path("outputs/normalization-v1.json"))
            command.add_argument("--output", type=Path, default=Path(f"outputs/{name}"))
    route = commands.choices["route"]
    commands.choices["status"].add_argument("--result", type=Path,
                                            default=Path("outputs/score/result_metadata.json"))
    route.add_argument("--cache", type=Path, default=Path("outputs/routes.sqlite"))
    route.add_argument("--output", type=Path, default=Path("outputs/routes.csv"))
    route.add_argument("--max-requests", type=int)
    route.add_argument("--retry-no-route", action="store_true")
    score = commands.choices["score"]
    score.add_argument("--scenario", choices=list(SCENARIOS), default="balanced")
    score.add_argument("--weights", help="Seven comma-separated importance values in documented order")
    score.add_argument("--max-commute-min", type=float)
    score.add_argument("--sample-set", choices=["A", "B"], default="A")
    score.add_argument("--group-by", choices=["area_id", "cluster_id"], default="area_id")
    return parser


def _run_prepare(args: argparse.Namespace) -> dict:
    from .spatial import prepare_data

    return prepare_data(args.data_root, args.output)


def _run_report(args: argparse.Namespace) -> dict:
    from .report import create_preparation_report

    return {"output": str(create_preparation_report(args.prepared, args.output))}


def main(argv: list[str] | None = None) -> int:
    """Return a clear failing exit status without dumping request headers or secrets."""
    args = _build_parser().parse_args(argv)
    try:
        result = args.handler(args)
        print(json.dumps(result, ensure_ascii=False, default=str, indent=2))
        return 0
    except (ValueError, KeyError, OSError) as error:
        print(json.dumps({"status": "invalid_parameters_or_inputs", "message": str(error)},
                         ensure_ascii=False))
        return 2
