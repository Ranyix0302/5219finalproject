"""Package reviewed source, original deliveries and the frozen analysis snapshot."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from render_handover_docs import root_document

ROOT = Path(__file__).resolve().parents[1]
TOKEN_PATTERN = re.compile(rb"eyJ[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}")


def compute_hash(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def check_for_credentials(path: Path) -> None:
    with path.open("rb") as stream:
        previous = b""
        while chunk := stream.read(1024 * 1024):
            if TOKEN_PATTERN.search(previous + chunk):
                raise ValueError(f"Credential-shaped content: {path.relative_to(ROOT)}")
            previous = chunk[-512:]
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as original_archive:
            for entry in original_archive.infolist():
                if not entry.is_dir() and TOKEN_PATTERN.search(original_archive.read(entry)):
                    raise ValueError(
                        f"Credential-shaped content inside: {path.name}/{entry.filename}"
                    )


def collect_files() -> dict[str, Path]:
    tracked = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode().split("\0")
    files = {name.replace("\\", "/"): ROOT / name for name in tracked if name}
    for directory in (
        "raw_data",
        "outputs/prepared",
        "outputs/score",
        "outputs/experiments",
        "outputs/route_audit_v2",
        "outputs/audits",
        "outputs/interface_acceptance",
        "outputs/GE5219_MCDA_真实结果_figures",
        "outputs/GE5219_MCDA_Actual_Results_EN_figures",
    ):
        for path in (ROOT / directory).rglob("*"):
            if path.is_file():
                files[path.relative_to(ROOT).as_posix()] = path
    for name in (
        "routes.csv",
        "routes.sqlite",
        "routing_execution.json",
        "normalization-v1.json",
        "test-final.log",
        "GE5219_MCDA_真实结果.html",
        "GE5219_MCDA_Actual_Results_EN.html",
    ):
        files[f"outputs/{name}"] = ROOT / "outputs" / name
    for name in ("audit_plan.csv", "audit_plan_manifest.json"):
        files[f"outputs/route_audit_v1/{name}"] = ROOT / "outputs/route_audit_v1" / name
    for short, name in (
        ("personal", "Xie Bingsheng_GE5219_个人工作计划.docx"),
        ("implementation", "GE5219_MCDA_实施计划.docx"),
    ):
        files[f"work_plans/{name}"] = ROOT / "outputs/updated_work_plans" / f"{short}.docx"
    files["outputs/google_methodology_updated.png"] = (
        ROOT / "outputs/google_methodology_updated.png"
    )
    return files


def make_entry(language: str) -> str:
    return root_document(language)


def create_packages(destination: Path) -> dict:
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT).strip():
        raise RuntimeError("Commit reviewed files before packaging")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    metadata = json.loads((ROOT / "outputs/score/result_metadata.json").read_text(encoding="utf-8"))
    raw_manifest = json.loads(
        (ROOT / "outputs/audits/raw_data_handover_manifest.json").read_text(encoding="utf-8")
    )
    files = collect_files()
    for row in raw_manifest["files"]:
        path = files[f"raw_data/{row['path']}"]
        if compute_hash(path) != row["sha256"]:
            raise ValueError(f"Raw source changed: {row['path']}")
    entries = []
    for name, path in sorted(files.items()):
        if not path.is_file():
            raise FileNotFoundError(path)
        check_for_credentials(path)
        entries.append({"path": name, "bytes": path.stat().st_size, "sha256": compute_hash(path)})
    delivered = []
    destination.mkdir(parents=True, exist_ok=True)
    for language, filename in (
        ("zh", "GE5219_MCDA_完整交接包_中文.zip"),
        ("en", "GE5219_MCDA_Complete_Handover_EN.zip"),
    ):
        archive = ROOT / "outputs" / filename
        entry_bytes = make_entry(language).encode("utf-8")
        local_entries = [entry for entry in entries if entry["path"] != "doc.html"]
        local_entries.append(
            {
                "path": "doc.html",
                "bytes": len(entry_bytes),
                "sha256": hashlib.sha256(entry_bytes).hexdigest(),
            }
        )
        manifest = {
            "created_utc": datetime.now(UTC).isoformat(),
            "language": language,
            "git_commit": commit,
            "dataset_version": metadata["dataset_version"],
            "baseline_result_id": metadata["result_id"],
            "source_routes_sha256": metadata["source_routes_sha256"],
            "raw_file_count": raw_manifest["file_count"],
            "raw_total_bytes": raw_manifest["total_bytes"],
            "scope": "Original A/B deliveries unchanged; reviewed source; bilingual explanations and actual-results pages with embedded translated charts; executed notebooks; prepared data; route cache; saved MCDA/experiments; audits; updated work plans. No credentials or runtime environments. Original source files and archived route-review pages retain their original language.",
            "files": local_entries,
        }
        temporary = archive.with_suffix(".zip.partial")
        with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as packed:
            for entry in local_entries:
                if entry["path"] == "doc.html":
                    packed.writestr("doc.html", entry_bytes)
                else:
                    packed.write(files[entry["path"]], entry["path"])
            packed.writestr(
                "HANDOVER_MANIFEST.json", json.dumps(manifest, ensure_ascii=False, indent=2)
            )
        with zipfile.ZipFile(temporary) as packed:
            if packed.testzip() is not None:
                raise ValueError("ZIP CRC verification failed")
            for entry in local_entries:
                if hashlib.sha256(packed.read(entry["path"])).hexdigest() != entry["sha256"]:
                    raise ValueError(f"ZIP hash mismatch: {entry['path']}")
        temporary.replace(archive)
        delivered_path = destination / filename
        shutil.copy2(archive, delivered_path)
        if compute_hash(archive) != compute_hash(delivered_path):
            raise ValueError(f"Delivered copy mismatch: {filename}")
        (ROOT / f"outputs/HANDOVER_MANIFEST_{language}.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        delivered.append(
            {
                "path": str(delivered_path),
                "bytes": archive.stat().st_size,
                "sha256": compute_hash(archive),
                "files": len(local_entries) + 1,
                "every_member_crc_and_sha256_verified": True,
            }
        )
    return {
        "git_commit": commit,
        "raw_files": raw_manifest["file_count"],
        "credential_scan_passed": True,
        "packages": delivered,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--destination", type=Path, default=ROOT / "outputs/delivered")
    result = create_packages(parser.parse_args().destination.resolve())
    (ROOT / "outputs/package_verification.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
