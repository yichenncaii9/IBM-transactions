# AML Blind Spots dashboard (Q1 + Q2)

One Streamlit app with three pages: Overview, Q1 (spotting laundering accounts)
and Q2 (risky money corridors). It reads only the small CSVs in `data/`, so it
needs no AWS access and costs nothing to run.

    pip install -r dashboard/requirements.txt
    streamlit run dashboard/app.py

## Pages
- **Overview**: both questions and their headline answers.
- **Q1**: model comparison (LightGBM vs fixed rules vs random), launderers caught
  while working down each list, LightGBM's top accounts, and how often each graph
  shape is illicit. All on the validation days (Sept 11–12).
- **Q2**: cross-border vs domestic, riskiest corridors, Basel index vs corridor
  risk, and a country heat map. The sidebar slider sets the minimum corridor size.

## Where the data comes from
| File | Source |
|---|---|
| `eval_summary.csv`, `eval_deciles.csv` | `python q1d-eval/run_models.py account_scores.csv` (copied from `q1d-eval/out/`) |
| `q1_top_accounts.csv` | Top 500 of `q1d-eval/out/model_scores_val.csv` by LightGBM (no taint) score, with each account's rank under fixed rules |
| `q1_shapes_val.csv` | Athena: `is459_aml.graph_motifs` (val) joined to `gbm_account_labels` (val), grouped by graph shape |
| `q2_corridors.csv` | Athena: `SELECT * FROM is459_aml.q2_corridors;` → Download results |

To refresh, re-export the file and replace it in `data/`.
