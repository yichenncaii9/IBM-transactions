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
- poc: local pilot on the full files with DuckDB (see poc/README.md)
- tests: unit tests, run with `python -m pytest tests`
