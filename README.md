# IBM-transactions

# AML Blind Spots (IS459 Group 2)

## Dataset
IBM Transactions for Anti Money Laundering (AML) on Kaggle.
Link: https://www.kaggle.com/datasets/ealtman2019/ibm-transactions-for-anti-money-laundering-aml/data?select=HI-Medium_Trans.csv

We use the Medium sets only, three files each:
- HI-Medium_Trans.csv, HI-Medium_Patterns.txt, HI-Medium_accounts.csv
- LI-Medium_Trans.csv, LI-Medium_Patterns.txt, LI-Medium_accounts.csv

The full files (about 3 GB per Trans file) are not stored in this repo.

## How to get the data
1. Log in to Kaggle and download the dataset from the link above.
2. Unzip it and keep only the six files listed above.
3. Upload them to the raw S3 bucket (see /ingestion).

## sample_data
The first 1,000 rows of each file, for testing scripts locally.

## Layout
- glue/lib/aml_common: shared code (Q1 tracer, Patterns.txt parser), no Spark dependency
- glue/rule_features.py: Part D Glue job 1, Rules A, B and D per account per period, plus the edge list
- glue/rule_taint.py: Part D Glue job 2, Rule C taint from job 1's output; writes the feature table for E and F
- glue/deploy_part_d.py: creates or updates both Part D Glue jobs and the `part-d` workflow that runs job 2 after job 1 succeeds
- dashboard: one Streamlit app for Q1 and Q2, `streamlit run dashboard/app.py` (see dashboard/README.md)
- poc: local pilot on the full files with DuckDB (see poc/README.md)
- tests: unit tests, run with `python -m pytest tests`. The Spark tests need Java 17 and `pyspark==3.5.*`, and are skipped without pyspark.
