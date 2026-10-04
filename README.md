# Job Market Analysis and Recommendation System

Analysis of 244,828 Upwork job postings, mostly from February and March 2024:
salary signals in job titles, emerging job categories, demand forecasts,
hourly rates by country, remote-work signals, and a job recommendation API
with a dashboard.

> **Status:** foundation and data cleaning complete (Notebook 01). The
> analysis notebooks for Tasks 1-8 build on the cleaned master table.

## Notebooks

| Notebook | What it does |
|---|---|
| `00_build_overview` | Shows which build the notebooks use and the raw file before cleaning |
| `01_data_audit_and_cleaning` | Audits every column, explains each cleaning rule with its evidence, and validates the master table `jobs_clean.parquet` |
| `02_exploratory_market_analysis` | Explores market size, pay, geography, time patterns, missing-pay bias and title words before modelling |
| `03_job_categories` | Gives every job one job-function category (rules + a guarded classifier), tunes it on 150 hand labels and reports the honest result on 350 blind labels |
| `04_pay_keywords_and_countries` | Task 1: which title words go with higher or lower pay (raw, same country, same country + category); Task 4: hourly rates offered by client country, with an interactive map |

## Data setup

The source file is the Upwork job-postings CSV supplied with the assignment:

| Item | Value |
|---|---|
| File name | `all_upwork_jobs_2024-02-07-2024-03-24.csv` |
| Location | `data/raw/` |
| Rows | 244,828 (plus a header row) |
| SHA-256 | `6513e9a744f15726bdb40d6435a60834e864ace08a75e1d7feb75e10ddb78b11` |

The CSV is not stored in this repository (decision D-011). Download it from
the dataset link in the assignment brief (`docs/assignment_brief.pdf`) and
place it in `data/raw/` without opening or re-saving it (a spreadsheet
program can change its bytes). The build records the file hash, and the
lineage check fails if the file differs from the one used for the results.

## Setup

The pinned analysis environment of the official build is in `environment.yml`
(Python 3.11 and exact versions of every package that can change a result).
From a terminal (Anaconda Prompt on Windows) inside the project folder:

```bash
conda env create -f environment.yml
conda activate jobmarket
pip install -e . --no-deps
```

`pip install -e .[dev]` also works in any Python 3.10+ environment, with
compatible (not pinned) versions. Every command still runs and prints a
WARNING for each version that differs from the pins. Official results come
from the pinned environment; set `JOB_MARKET_STRICT=1` to turn those
warnings into errors (continuous integration does this).

## Build and verify

```bash
python -m job_market rebuild        # every generated file, from the raw CSV
python -m pytest                    # automated tests
python -m job_market run-notebooks  # every notebook, top to bottom, fresh kernel
python -m job_market check          # lineage check
```

`python -m job_market verify` runs the rebuild, the notebooks and the
lineage check in one command.

| Command | What it proves |
|---|---|
| `rebuild` | Every generated file comes from the raw CSV in one run, recorded in `data/processed/run_manifest.json`. |
| `run-notebooks` | Every notebook runs top to bottom in a fresh kernel. |
| `check` | Raw data, settings, code and `environment.yml` match the build; every output matches its recorded hash; no stale file exists; every notebook is a clean, error-free, top-to-bottom run of the current build whose first code cell calls `start()`. Environment differences are warnings (errors in strict mode). |
| `check-notebooks` | The notebook part of `check` only. It needs the committed run manifest but not the raw CSV, so CI can run it. |

Each command exits with code 0 on success and 1 on failure.

## Opening notebooks interactively

Start JupyterLab from the project environment, so the default kernel is the
project's Python. From a terminal (Anaconda Prompt on Windows) in the project
folder:

```bash
conda activate jobmarket
jupyter lab --port 8899 --port-retries 0
```

A fixed port (8899) avoids landing in a Jupyter server from another project
that already uses the default port 8888. Check that the browser address
starts with `localhost:8899`. To confirm the kernel, run in a scratch
notebook:

```python
import sys
print(sys.executable)   # should point into the jobmarket environment
```

Use `scratch.ipynb` (ignored by Git and by the checks) for experiments, so
the numbered project notebooks stay clean. Stop JupyterLab with Ctrl+C in
the terminal when finished.

## Project layout

```text
config/pipeline.toml     every threshold and path, in one place
data/raw/                source CSV, never modified
data/processed/          generated tables and the run manifest
docs/decisions.md        every decision with its plain-English reason
.github/workflows/ci.yml tests and notebook check on every push
docs/assignment_brief.pdf
environment.yml          pinned analysis environment of the official build
notebooks/               narrative analysis, reading verified pipeline outputs
src/job_market/          pipeline, analysis steps and quality gates
tests/                   automated tests
```

## Decisions

Each analytical decision, with its reason and evidence, is in
[`docs/decisions.md`](docs/decisions.md).
