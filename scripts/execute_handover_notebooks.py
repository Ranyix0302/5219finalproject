"""Execute the two handover notebooks in clean kernels and retain their evidence."""

import json
import os
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

import nbformat
from jupyter_client.kernelspec import KernelSpecManager
from nbclient import NotebookClient


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    checks = []
    with tempfile.TemporaryDirectory(prefix="ge5219-notebook-kernel-") as temporary:
        kernel_root = Path(temporary) / "kernels"
        kernel_path = kernel_root / "ge5219-handover"
        kernel_path.mkdir(parents=True)
        (kernel_path / "kernel.json").write_text(
            json.dumps(
                {
                    "argv": [sys.executable, "-m", "ipykernel_launcher", "-f", "{connection_file}"],
                    "display_name": "GE5219 handover verification",
                    "language": "python",
                }
            ),
            encoding="utf-8",
        )
        previous_jupyter_path = os.environ.get("JUPYTER_PATH")
        os.environ["JUPYTER_PATH"] = temporary + (
            os.pathsep + previous_jupyter_path if previous_jupyter_path else ""
        )
        try:
            manager = KernelSpecManager(kernel_dirs=[str(kernel_root)])
            for language in ("zh", "en"):
                path = root / "notebooks" / f"GE5219_Full_Workflow_{language}.ipynb"
                notebook = nbformat.read(path, as_version=4)
                for cell in notebook.cells:
                    if cell.cell_type == "code":
                        cell.outputs = []
                        cell.execution_count = None
                started = time.perf_counter()
                client = NotebookClient(
                    notebook,
                    timeout=600,
                    kernel_name="ge5219-handover",
                    resources={"metadata": {"path": str(path.parent)}},
                    allow_errors=False,
                )
                client.create_kernel_manager()
                client.km.kernel_spec_manager = manager
                client.execute()
                nbformat.write(notebook, path)
                code_cells = [cell for cell in notebook.cells if cell.cell_type == "code"]
                errors = [
                    output
                    for cell in code_cells
                    for output in cell.outputs
                    if output.output_type == "error"
                ]
                evidence_outputs = [
                    output
                    for cell in code_cells
                    for output in cell.outputs
                    if output.output_type == "display_data" and "application/json" in output.data
                ]
                evidence = evidence_outputs[-1].data["application/json"]
                assert not errors
                assert all(cell.execution_count is not None for cell in code_cells)
                assert evidence["baseline_matches_frozen"]
                assert evidence["raw_source_read"]
                checks.append(
                    {
                        "notebook": path.relative_to(root).as_posix(),
                        "language": language,
                        "clean_kernel": True,
                        "status": "passed",
                        "executed_code_cells": len(code_cells),
                        "cell_errors": len(errors),
                        "elapsed_seconds": round(time.perf_counter() - started, 3),
                        "evidence": evidence,
                    }
                )
                print(json.dumps(checks[-1], ensure_ascii=False), flush=True)
        finally:
            if previous_jupyter_path is None:
                os.environ.pop("JUPYTER_PATH", None)
            else:
                os.environ["JUPYTER_PATH"] = previous_jupyter_path
    report = root / "outputs" / "audits" / "notebook_execution_check.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(
        json.dumps(
            {
                "checked_at_utc": datetime.now(UTC).isoformat(),
                "python_version": sys.version.split()[0],
                "status": "passed",
                "notebooks": checks,
                "default_api_branch_enabled": False,
                "network_evidence_scope": "Routing branch disabled; no independent traffic monitoring",
                "full_experiment_rerun": False,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
