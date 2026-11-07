"""Part B: build the train/val/test split and the account labels in Athena.

    python q1b-split/build_split.py

Dates (from q1b-split/out/RESULTS.md, 2-day gaps; same as D's --periods):
    train Sep 1-8 | gap Sep 9-10 | val Sep 11-12 | gap Sep 13-14 | test Sep 15-16 | tail Sep 17-28
The tail is kept (label 'tail') so test can be reported twice: Sep 15-16, and Sep 15-28.

Writes
    is459_aml.gbm_split           one row per transaction: split, attempt_id, attempt_start,
                                  is_new_attempt (attempt started on/after its split's first day)
    is459_aml.gbm_account_labels  one row per account per period (train, val, test, test_tail):
                                  is_illicit = sent or received >= 1 laundering transfer in the period
                                  acct uses D's format: '<bank>|<account>'
"""
import os
import sys

import boto3

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'aws'))
import config as C  # noqa: E402

DB = C.DATABASE
SPLIT_PREFIX = 'results/q1b/split/'
LABELS_PREFIX = 'results/q1b/account_labels/'

# name: (first day, last day), inclusive
SPLITS = [('train', '2022-09-01', '2022-09-08'), ('gap1', '2022-09-09', '2022-09-10'),
          ('val', '2022-09-11', '2022-09-12'), ('gap2', '2022-09-13', '2022-09-14'),
          ('test', '2022-09-15', '2022-09-16'), ('tail', '2022-09-17', '2022-09-28')]
# label periods: name -> (first day, last day)
PERIODS = [('train', '2022-09-01', '2022-09-08'), ('val', '2022-09-11', '2022-09-12'),
           ('test', '2022-09-15', '2022-09-16'), ('test_tail', '2022-09-15', '2022-09-28')]


def empty(s3, prefix):
    assert prefix in (SPLIT_PREFIX, LABELS_PREFIX)
    keys = [o['Key'] for p in s3.get_paginator('list_objects_v2').paginate(
        Bucket=C.BUCKET, Prefix=prefix) for o in p.get('Contents', [])]
    for i in range(0, len(keys), 1000):
        s3.delete_objects(Bucket=C.BUCKET, Delete={'Objects': [{'Key': k} for k in keys[i:i + 1000]]})


def main():
    s3 = boto3.client('s3', region_name=C.REGION)
    split_case = '\n'.join(
        f"WHEN t.transaction_date BETWEEN '{a}' AND '{b}' THEN '{n}'" for n, a, b in SPLITS)
    start_case = '\n'.join(
        f"WHEN '{n}' THEN TIMESTAMP '{a} 00:00:00'" for n, a, _ in SPLITS)

    C.athena(f'DROP TABLE IF EXISTS {DB}.gbm_split')
    empty(s3, SPLIT_PREFIX)
    C.athena(f"""CREATE TABLE {DB}.gbm_split
      WITH (format = 'PARQUET', external_location = 's3://{C.BUCKET}/{SPLIT_PREFIX}') AS
      WITH att AS (
        SELECT p.transaction_id, p.attempt_id, p.pattern_type AS attempt_type,
               min(t.txn_ts) OVER (PARTITION BY p.attempt_id) AS attempt_start
        FROM {DB}.pattern_transactions p
        JOIN {DB}.transactions t ON t.transaction_id = p.transaction_id
      ),
      s AS (
        SELECT t.transaction_id, t.transaction_date, t.is_laundering,
               CASE {split_case} END AS split
        FROM {DB}.transactions t
      )
      SELECT s.transaction_id, s.split, s.is_laundering, a.attempt_id, a.attempt_type, a.attempt_start,
             CASE WHEN a.attempt_start >= (CASE s.split {start_case} END) THEN 1 ELSE 0 END
               AS is_new_attempt
      FROM s LEFT JOIN att a ON a.transaction_id = s.transaction_id""")
    print('gbm_split written')

    C.athena(f'DROP TABLE IF EXISTS {DB}.gbm_account_labels')
    empty(s3, LABELS_PREFIX)
    period_case = ' UNION ALL '.join(
        f"SELECT '{n}' AS period, DATE '{a}' AS d0, DATE '{b}' AS d1" for n, a, b in PERIODS)
    C.athena(f"""CREATE TABLE {DB}.gbm_account_labels
      WITH (format = 'PARQUET', external_location = 's3://{C.BUCKET}/{LABELS_PREFIX}') AS
      WITH p AS ({period_case}),
      sides AS (
        SELECT p.period, t.from_bank || '|' || t.from_account AS acct,
               t.is_laundering AS laund_sent, 0 AS laund_recv
        FROM {DB}.transactions t JOIN p ON date(t.transaction_date) BETWEEN p.d0 AND p.d1
        UNION ALL
        SELECT p.period, t.to_bank || '|' || t.to_account AS acct,
               0 AS laund_sent, t.is_laundering AS laund_recv
        FROM {DB}.transactions t JOIN p ON date(t.transaction_date) BETWEEN p.d0 AND p.d1
      )
      SELECT period, acct, count(*) AS n_txn_sides,
             sum(laund_sent) AS n_laund_sent, sum(laund_recv) AS n_laund_recv,
             CASE WHEN sum(laund_sent) + sum(laund_recv) > 0 THEN 1 ELSE 0 END AS is_illicit
      FROM sides GROUP BY period, acct""")
    print('gbm_account_labels written\n')

    print('Transactions per split:')
    for r in C.athena(f"""SELECT split, count(*) n_rows, sum(is_laundering) n_laund,
            round(100.0 * avg(is_laundering), 3) laund_pct,
            sum(CASE WHEN is_laundering = 1 AND attempt_id IS NOT NULL THEN 1 ELSE 0 END) in_patterns,
            sum(CASE WHEN attempt_id IS NOT NULL AND is_new_attempt = 1 THEN 1 ELSE 0 END) new_attempt_rows
          FROM {DB}.gbm_split GROUP BY 1
          ORDER BY CASE split WHEN 'train' THEN 1 WHEN 'gap1' THEN 2 WHEN 'val' THEN 3
                   WHEN 'gap2' THEN 4 WHEN 'test' THEN 5 ELSE 6 END"""):
        print('  '.join(f'{c:>16}' for c in r))
    print('\nAccounts per period:')
    for r in C.athena(f"""SELECT period, count(*) accounts, sum(is_illicit) illicit,
            round(100.0 * avg(is_illicit), 3) illicit_pct
          FROM {DB}.gbm_account_labels GROUP BY 1
          ORDER BY CASE period WHEN 'train' THEN 1 WHEN 'val' THEN 2 WHEN 'test' THEN 3 ELSE 4 END"""):
        print('  '.join(f'{c:>16}' for c in r))


if __name__ == '__main__':
    main()
