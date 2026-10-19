"""Regenerate both offline result pages from saved data without model or API calls."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ge5219.result_report import create_result_report


def fingerprint(paths: list[Path]) -> dict[str, str]:
    return {
        str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths
    }


def payload(path: Path) -> dict:
    document = path.read_text(encoding="utf-8")
    return json.loads(document.split('id="report-data">', 1)[1].split("</script>", 1)[0])


def saved_result_data(data: dict) -> dict:
    context = {key: value for key, value in data["context"].items() if key != "generated_utc"}
    return {
        "context": context,
        "spatial": data["spatial"],
        "views": {
            key: {
                field: value
                for field, value in view.items()
                if field not in {"map", "contributions"}
            }
            for key, view in data["views"].items()
        },
        "arms": {
            key: {
                field: value
                for field, value in arm.items()
                if field not in {"map", "contributions"}
            }
            for key, arm in data["arms"].items()
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "outputs")
    args = parser.parse_args()
    prepared, score, experiments = [
        ROOT / "outputs" / folder for folder in ("prepared", "score", "experiments")
    ]
    inputs = sorted(
        {
            prepared / "data_quality.json",
            prepared / "analysis_locations.csv",
            prepared / "subzones.geojson",
            *score.glob("*.csv"),
            *score.glob("*.json"),
            *experiments.rglob("*.csv"),
            *experiments.rglob("*.json"),
        }
    )
    before = fingerprint(inputs)
    outputs = {}
    for language, filename in [
        ("zh", "GE5219_MCDA_真实结果.html"),
        ("en", "GE5219_MCDA_Actual_Results_EN.html"),
    ]:
        target = args.output_dir / filename
        create_result_report(prepared, score, experiments, target, language=language)
        outputs[language] = target
    after = fingerprint(inputs)
    if before != after:
        raise RuntimeError("Saved source data changed while rendering result pages")
    chinese, english = [payload(outputs[language]) for language in ("zh", "en")]
    if saved_result_data(chinese) != saved_result_data(english):
        raise RuntimeError("Chinese and English result pages contain different saved result data")
    audit = {
        "status": "passed",
        "languages": list(outputs),
        "saved_inputs_unchanged": True,
        "input_files_checked": len(inputs),
        "input_sha256": before,
        "numeric_and_result_identity_payload_equal": True,
        "saved_view_count": len(english["views"]),
        "spatial_arm_count": len(english["arms"]),
        "new_routing_requests": 0,
        "model_recalculated": False,
        "outputs": {key: str(value) for key, value in outputs.items()},
    }
    audit_dir = ROOT / "outputs/audits"
    audit_dir.mkdir(parents=True, exist_ok=True)
    (audit_dir / "result_page_localization_check.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {key: value for key, value in audit.items() if key != "input_sha256"},
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
