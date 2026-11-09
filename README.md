# AML Blind Spots — IS459 Group 2

Code and supporting results for analyzing blind spots in the [IBM Transactions for Anti Money Laundering dataset](https://www.kaggle.com/datasets/ealtman2019/ibm-transactions-for-anti-money-laundering-aml/data). 

## What is included

- `glue/`: shared parsing, timestamp, and tracing logic plus account rule feature and taint jobs.
- `q1/`, `q1b-split/`, `q1c-graph/`, `q1d-eval/`: cash-out query, temporal split, graph features, and model comparison scripts. The split choice and measurements are in [`q1b-split/out/RESULTS.md`](q1b-split/out/RESULTS.md).
- `LightGBM_Final.ipynb`: model development notebook.
- `dashboard/`: Streamlit presentation app with the small prepared result tables needed to run it. See [`dashboard/README.md`](dashboard/README.md).
- `poc/`: DuckDB pilot and validation scripts. See [`poc/README.md`](poc/README.md).
- `aws/`: AWS configuration and timestamp correction utilities. See [`aws/README.md`](aws/README.md).
- `q2/corridors.sql`: recovered Athena SQL for the bank-country lookup, alert union, and Q2 corridor tables.
- `Neo4j_setup.md`: graph database setup guide.
- `sample_data/`: a small HI-Medium transaction sample for local checks.
- `tests/`: unit tests for shared logic and Glue jobs.

## Run locally

Use Python 3.11. Create an environment outside the submitted files or in `.venv/` (which is ignored), then install dependencies as needed:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pytest tests
.venv/bin/python -m pip install -r dashboard/requirements.txt
.venv/bin/python -m streamlit run dashboard/app.py
```

The pilot has its own dependencies in `poc/requirements.txt`. Large-data scripts require the original dataset and, where indicated in their docstrings, AWS or Neo4j resources.

## Data

Download the HI-Medium and LI-Medium transaction, pattern, and account files from the linked Kaggle dataset for the full pipeline. The dashboard uses the prepared CSV files committed under `dashboard/data/` and does not need the full dataset or AWS access.

## Interpretation

The dashboard shows validation-period results from the group's experiment. `q1d-eval/run_models.py` scores the fixed-rules baseline using real graph motif counts from S3. The separate `q1d-eval/model2_rules.py` is an early prototype that generates mock motif counts; do not use its predictions as evaluation results.

## Submission evidence

The source code and prepared dashboard tables are here. The presentation deck and narrated run video are stored separately from this repository. The assignment also requires a narrated *setup* video, YouTube links to both videos in the presentation appendix, and a live or recorded pipeline demo. See [`docs/submission-check.md`](docs/submission-check.md) for the remaining checks before upload.
