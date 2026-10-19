# Code structure and how to run it

This is a small, staged Python application. GIS measurements and MCDA scores are calculated in Python; the result page displays saved bundles. The language model does not calculate independent scores.

## 1. Folders: keep these distinctions

| Folder | What it contains | When to change it |
|---|---|---|
| `raw_data/` | All 176 unchanged A/B delivery files, including original ZIPs and their extracted contents | Keep read-only; reconcile new evidence in a new version |
| `config/` | Destination, indicator dictionary, service-address and transit-operation rules | A changed rule requires documented versioning and appropriate reruns |
| `src/ge5219/` | The thirteen application modules listed below | Review changes before regenerating results |
| `notebooks/` | Complete Chinese and English teaching/reproduction notebooks | Run from the extracted package with the correct Python environment |
| `outputs/prepared/` | Derived housing, membership, samples, static indicators, quality and source hashes | Use `prepare` to regenerate in a different directory |
| `outputs/routes.csv`, `routes.sqlite` | Frozen route measurements and resumable cache | Do not mix destinations, times, adapters or versions |
| `outputs/score/` | Formal A/Subzone balanced/no-cap bundle | Keep frozen for comparisons |
| `outputs/experiments/` | Scenarios, all 1,000 weight draws/ranks, OAT and spatial/cap/qualification results | Full reruns go in a new output directory |
| `outputs/audits/` | Arithmetic, raw-copy, notebook and handover checks | Evidence has a stated scope; it is not full data certification |
| `docs/` | Main handbooks, processing methods, interfaces, decisions, methodology and progress | Interpret the dated evidence rather than treating every old plan as current |
| `tests/` | Synthetic implementation checks, clearly separate from research observations | Synthetic fixtures are never housing results |

`raw_data/` and `outputs/` are distributed in the complete ZIP packages, not in GitHub source. Never put credentials in either notebook cells or committed files. New route calls read `ONEMAP_TOKEN` from the local environment.

## 2. Modules: follow the data rather than reading every file at once

| Module | Responsibility |
|---|---|
| `spatial.py` | Read A/B, reconcile source identities, hold out conflicts, project/repair geometries, form clusters and grid representatives, calculate six static indicators and preparation audits |
| `routing.py` | Build OneMap requests, validate the destination, read a local token, classify responses, select the first itinerary, and use SQLite caching/retries |
| `pipeline.py` | Join static measurements and routes by stable location IDs; enforce compatible destination/time data and preserve unknowns |
| `mcda.py` | Fit fixed P5/P95 bounds, normalize, validate weights/constraints, calculate feasible-point contributions, apply area eligibility and rank |
| `experiments.py` | Four scenarios, Dirichlet, OAT, caps, qualification rules and the three spatial arms; retain each setting and result |
| `artifacts.py` | Read location tables and write deterministic result bundles with version metadata |
| `settings.py` | Ordered seven indicators, directions, scenario vectors, departure and analysis version |
| `cli.py` | User-facing stage commands and clear error statuses |
| `report.py` | Preparation evidence page |
| `result_report.py` | Portable Chinese and English actual-results pages from saved outputs, including translated chart labels |
| `route_audit.py` | Route-review plans, evidence binding and review summaries |
| `__main__.py`, `__init__.py` | Package entry and initialization |

For formulas, start with `mcda.py`; for sampling and facility counts, use `spatial.py`; for the OneMap special cases, read the processing guide before changing `routing.py`.

Run `.\.venv\Scripts\python.exe scripts/render_result_pages.py` to regenerate both actual-results pages. It only reads frozen prepared data, baseline scores and experiment outputs, renders charts and writes HTML; it makes no new route requests and does not recalculate MCDA. The Chinese file is `outputs/GE5219_MCDA_真实结果.html`, and the English file is `outputs/GE5219_MCDA_Actual_Results_EN.html`. Both are included in the complete packages and can be opened offline.

## 3. Installation and offline Run All

Use Python 3.11 or later. From the **extracted package root**, on Windows:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pip install jupyterlab ipykernel nbclient nbformat
.\.venv\Scripts\python.exe -m ipykernel install --user --name ge5219 --display-name "GE5219"
.\.venv\Scripts\python.exe -m jupyterlab
```

Open the relevant `GE5219_Full_Workflow_en.ipynb` or `_zh.ipynb` and select that environment. On macOS/Linux, the Python executable is `.venv/bin/python`. An existing GIS environment is also acceptable if all required packages are installed. The execution audit records the tested Python version; library versions can affect hashing and numerical rendering, so retain the supplied snapshot and investigate differences.

Defaults are `RUN_PREPARE=False`, `RUN_API=False`, and `RUN_FULL_EXPERIMENTS=False`. Run All still reads the actual original GIS/CSV data and source hashes, assembles the full seven-indicator matrix, refits/checks A's normalization, recalculates the baseline, four scenarios, three spatial arms, caps and qualification settings, and compares these against thirteen saved bundles. It regenerates the 1,000 weight vectors and recomputes frequency/rank summaries from the 241,000 saved area-rank rows; it does **not** rerun all 1,000 MCDA simulations by default. OAT weight settings and the 77 adjacent intervals are checked from saved outputs. All frozen input/output hashes are checked for accidental modification.

`scripts/execute_handover_notebooks.py` executes both notebooks in separate clean kernels and writes `outputs/audits/notebook_execution_check.json`. It requires the notebook dependencies above. Its evidence describes actual execution, not a guarantee that a fresh clone without datasets will run.

## 4. Stage commands and optional reruns

```powershell
.\.venv\Scripts\python.exe -m ge5219 prepare --data-root raw_data --output outputs/new_version/prepared
.\.venv\Scripts\python.exe -m ge5219 status --prepared outputs/prepared --routes outputs/routes.csv
.\.venv\Scripts\python.exe -m ge5219 score --prepared outputs/prepared --routes outputs/routes.csv --normalization outputs/normalization-v1.json --scenario balanced --output outputs/new_score
.\.venv\Scripts\python.exe -m ge5219 experiments --prepared outputs/prepared --routes outputs/routes.csv --normalization outputs/normalization-v1.json --output outputs/new_experiments
```

The score command also accepts `--weights` (seven comma-separated nonnegative importance inputs), `--max-commute-min`, `--sample-set A|B` and `--group-by area_id|cluster_id`. See `python -m ge5219 score --help` for the exact contract. A new data/measurement version needs new normalization provenance; do not point a changed matrix at an old version file and suppress the resulting error.

Optional notebook preparation writes to `outputs/notebook_recomputed/prepared`; the optional API branch makes **one pilot request**, not a complete new matrix. It writes to its own pilot cache, and must not be mistaken for route coverage. For a complete new route batch, use the `route` command with explicit prepared/destination/cache/output settings and a request budget. The historical 19 October scene may later become unavailable: changing the date requires a new declared scene, not silently refreshing the old results. Optional full experiments write to `outputs/notebook_recomputed/experiments` and may take several minutes. These optional branches are code paths provided for deliberate new runs, not evidence that they executed in the default audit.

## 5. Hand off one whole result bundle

Each result contains `point_scores.csv`, `area_scores.csv`, `top5.csv` and `result_metadata.json`. Join by location/unit identifiers and verify the same `result_id`; keep `dataset_version`, departure, destination and applied weights. Point raw/z values are separate from the Top-5 area summary. Do not show a map from one scenario and explanations from another.

No route, insufficient coverage, no feasible candidates and invalid parameters are meaningful states. Show them, keep unknown values unknown and request an explicit user decision before relaxing hard constraints. Website/Agent integration and an independent-environment acceptance run remain group tasks; the repository does not claim they are finished.
