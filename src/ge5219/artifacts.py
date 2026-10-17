"""Portable result bundles with explicit JSON nulls for unobserved quantities."""

import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


def _json_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_value(item) for item in value]
    if isinstance(value, np.generic):
        return _json_value(value.item())
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, Path):
        return str(value)
    return value


def write_json(path: Path, payload: Any) -> None:
    """Write standards-compliant UTF-8 JSON, rejecting accidental NaN literals."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_json_value(payload), ensure_ascii=False, indent=2,
                               allow_nan=False), encoding="utf-8")


def save_result(result: dict[str, Any], output: Path) -> None:
    """Save tables and metadata from one recommendation without recomputing ranks."""
    output.mkdir(parents=True, exist_ok=True)
    for key in ("point_scores", "area_scores", "top5"):
        result[key].to_csv(output / f"{key}.csv", index=False)
    write_json(output / "result_metadata.json", result["metadata"])


def read_locations(path: Path) -> pd.DataFrame:
    """Read portable location identifiers without losing postal leading zeroes."""
    frame = pd.read_csv(path, float_precision="round_trip", dtype={
        "location_id": "str", "building_id": "str", "area_id": "str",
        "cluster_id": "str", "postal_code": "str", "Residential_ID": "str",
    })
    if "sample_A" in frame:
        parsed = frame.sample_A.astype(str).str.lower().map({"true": True, "false": False})
        if parsed.isna().any():
            raise ValueError("sample_A must contain explicit true/false values")
        frame["sample_A"] = parsed.astype(bool)
    return frame
