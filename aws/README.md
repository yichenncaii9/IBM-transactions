# Lane A: AWS and data cleaning

Run from the repo root with the project venv (`.venv/bin/python`).

## Keys (once)
Team account 897729121624 is a full AWS account (not Learner Lab), IAM user `g2team8`.
`.venv/bin/aws configure` with the user's access key, region `us-east-1`.
Real credits: nothing stops on its own. Get Xinqi's OK before creating or deleting resources.

## Check AWS works
    .venv/bin/python aws/check_aws.py

## Clean data (already done, 30 Oct)
Glue job `is459-clean-transaction` -> `is459_aml.transactions`
(31,898,238 rows, 35,230 laundering, 0 rejected; partitioned by `transaction_date`).

## Corrected timestamps
    .venv/bin/python aws/ts_fix.py ~/Downloads/archive/HI-Medium_Patterns.txt
- `is459_aml.txn_ts_fix`: Patterns.txt rows with `transaction_id`, `txn_ts`, `txn_ts_fixed`
- `is459_aml.v_transactions_fixed`: `transactions` + `txn_ts_fixed`, `ts_fixed_flag`
- Report: `processed/reports/ts_fix_hi_medium.json` (351 of 22,743 rows fixed)
- Rule: `glue/lib/aml_common/timefix.py`

`txn_ts_fixed` comes from the labels: Q1 tracer and checks only, never a model feature.
Use `txn_ts` for features and the split.
