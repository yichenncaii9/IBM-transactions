# IBM-transactions

# AML Blind Spots (IS459 Group 2)

## Dataset
IBM Transactions for Anti Money Laundering (AML) on Kaggle.
Link: https://www.kaggle.com/datasets/ealtman2019/ibm-transactions-for-anti-money-laundering-aml/data?select=HI-Medium_Trans.csv

We use HI-Medium_Trans.csv and LI-Medium_Trans.csv only.
The full files (about 3 GB each) are not stored in this repo.

## How to get the data
1. Log in to Kaggle and download the dataset from the link above.
2. Unzip it and keep only the two files listed above.
3. Upload them to the raw S3 bucket (see /ingestion).

## sample_data
The first 1,000 rows of each file, for testing scripts locally.