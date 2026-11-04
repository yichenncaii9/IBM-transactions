"""Lane A: corrected timestamps for out-of-order laundering hops, added beside the
existing cleaned table (is459_aml.transactions is NOT modified).

    python aws/ts_fix.py ~/Downloads/archive/HI-Medium_Patterns.txt

Steps
 1. Compute fixed timestamps locally from Patterns.txt (glue/lib/aml_common/timefix.py).
 2. Upload them to s3://<bucket>/processed/ts_fix_input/ (about 23K rows).
 3. Athena matches each row to its transaction_id -> table is459_aml.txn_ts_fix
    (s3://<bucket>/processed/ts_fix/).
 4. View is459_aml.v_transactions_fixed = transactions + txn_ts_fixed + ts_fixed_flag.
 5. Report -> s3://<bucket>/processed/reports/ts_fix_hi_medium.json

txn_ts_fixed comes from Patterns.txt (labels): Q1 tracer and checks only, never a model feature.
"""
import csv
import io
import json
import os
import sys

import boto3

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'glue', 'lib'))
import config as C  # noqa: E402
from aml_common.patterns import parse_file  # noqa: E402
from aml_common.timefix import fix_patterns, summarise  # noqa: E402

DB = C.DATABASE
INPUT_PREFIX = 'processed/ts_fix_input/'
OUTPUT_PREFIX = 'processed/ts_fix/'
REPORT_KEY = 'processed/reports/ts_fix_hi_medium.json'


def empty_prefix(s3, prefix):
    """Delete objects under one of OUR prefixes (CTAS needs an empty location)."""
    assert prefix in (INPUT_PREFIX, OUTPUT_PREFIX)
    keys = [o['Key'] for p in s3.get_paginator('list_objects_v2').paginate(
        Bucket=C.BUCKET, Prefix=prefix) for o in p.get('Contents', [])]
    for i in range(0, len(keys), 1000):
        s3.delete_objects(Bucket=C.BUCKET, Delete={'Objects': [{'Key': k} for k in keys[i:i + 1000]]})


def main(patterns_path):
    s3 = boto3.client('s3', region_name=C.REGION)

    fixed = fix_patterns(parse_file(os.path.expanduser(patterns_path)))
    summary = summarise(fixed)
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator='\n')
    w.writerow(['pattern_row', 'attempt_id', 'attempt_type', 'ts_raw', 'from_bank', 'from_account',
                'to_bank', 'to_account', 'amount_paid', 'payment_currency', 'payment_format',
                'fixed_ts'])
    for i, r in enumerate(fixed, 1):
        w.writerow([i, r['attempt_id'], r['typology'], r['ts_raw'], r['from_bank'], r['from_account'],
                    r['to_bank'], r['to_account'], repr(r['amount_paid']), r['payment_currency'],
                    r['payment_format'], r['fixed_ts'].strftime('%Y-%m-%d %H:%M:%S')])
    empty_prefix(s3, INPUT_PREFIX)
    s3.put_object(Bucket=C.BUCKET, Key=INPUT_PREFIX + 'ts_fix_input.csv', Body=buf.getvalue().encode())
    print(f'1-2. {len(fixed):,} pattern rows, {summary["changed"]:,} with a fixed time; uploaded.')

    C.athena(f'DROP TABLE IF EXISTS {DB}.ts_fix_input')
    C.athena(f"""CREATE EXTERNAL TABLE {DB}.ts_fix_input (
        pattern_row bigint, attempt_id bigint, attempt_type string, ts_raw string,
        from_bank string, from_account string, to_bank string, to_account string,
        amount_paid double, payment_currency string, payment_format string, fixed_ts string)
      ROW FORMAT DELIMITED FIELDS TERMINATED BY ','
      LOCATION 's3://{C.BUCKET}/{INPUT_PREFIX}'
      TBLPROPERTIES ('skip.header.line.count'='1')""")

    C.athena(f'DROP TABLE IF EXISTS {DB}.txn_ts_fix')
    empty_prefix(s3, OUTPUT_PREFIX)
    # Match by natural key among laundering rows; a transaction listed in two attempts
    # keeps the lowest attempt. Amounts compared with a tiny tolerance (float vs decimal).
    C.athena(f"""CREATE TABLE {DB}.txn_ts_fix
      WITH (format = 'PARQUET', external_location = 's3://{C.BUCKET}/{OUTPUT_PREFIX}') AS
      WITH m AS (
        SELECT p.pattern_row, p.attempt_id, p.attempt_type, t.transaction_id, t.txn_ts,
               date_parse(p.fixed_ts, '%Y-%m-%d %H:%i:%s') AS txn_ts_fixed,
               row_number() OVER (PARTITION BY t.transaction_id
                                  ORDER BY p.attempt_id, p.pattern_row) AS rk
        FROM {DB}.ts_fix_input p
        JOIN {DB}.transactions t
          ON t.is_laundering = 1
         AND t.txn_ts = date_parse(p.ts_raw, '%Y/%m/%d %H:%i')
         AND t.from_bank = p.from_bank AND t.from_account = p.from_account
         AND t.to_bank = p.to_bank AND t.to_account = p.to_account
         AND t.payment_currency = p.payment_currency AND t.payment_format = p.payment_format
         AND abs(CAST(t.amount_paid AS double) - p.amount_paid) <= 1e-6 * greatest(1, p.amount_paid)
      )
      SELECT transaction_id, attempt_id, attempt_type, pattern_row, txn_ts, txn_ts_fixed,
             CASE WHEN txn_ts_fixed <> txn_ts THEN 1 ELSE 0 END AS ts_fixed_flag
      FROM m WHERE rk = 1""")
    print('3.   table txn_ts_fix written')

    C.athena(f"""CREATE OR REPLACE VIEW {DB}.v_transactions_fixed AS
      SELECT t.*, COALESCE(f.txn_ts_fixed, t.txn_ts) AS txn_ts_fixed,
             COALESCE(f.ts_fixed_flag, 0) AS ts_fixed_flag
      FROM {DB}.transactions t
      LEFT JOIN {DB}.txn_ts_fix f ON f.transaction_id = t.transaction_id""")
    print('4.   view v_transactions_fixed created')

    m = C.athena(f"""SELECT count(*), count(DISTINCT pattern_row), sum(ts_fixed_flag),
                            count(DISTINCT transaction_id)
                     FROM {DB}.txn_ts_fix""")[1]
    by_type = C.athena(f"""SELECT attempt_type, count(*), sum(ts_fixed_flag),
                                  round(avg(CASE WHEN ts_fixed_flag = 1 THEN
                                    date_diff('minute', txn_ts, txn_ts_fixed) / 60.0 END), 1)
                           FROM {DB}.txn_ts_fix GROUP BY 1 ORDER BY 1""")[1:]
    tot = C.athena(f'SELECT count(*), sum(is_laundering) FROM {DB}.transactions')[1]
    report = {
        'dataset': 'hi_medium',
        'transactions_rows': int(tot[0]), 'transactions_laundering': int(tot[1]),
        'pattern_rows': len(fixed),
        'pattern_rows_matched': int(m[1]),
        'transactions_with_pattern': int(m[3]),
        'rows_ts_fixed': int(m[2]),
        'rows_ts_fixed_pct_of_pattern_rows': round(100 * int(m[2]) / len(fixed), 2),
        'by_attempt_type': {r[0]: {'rows': int(r[1]), 'fixed': int(r[2]),
                                   'avg_shift_hours': float(r[3]) if r[3] else 0.0}
                            for r in by_type},
        'local_check': summary,
        'tables': [f'{DB}.txn_ts_fix', f'{DB}.v_transactions_fixed'],
    }
    s3.put_object(Bucket=C.BUCKET, Key=REPORT_KEY, Body=json.dumps(report, indent=2).encode())
    print(json.dumps({k: v for k, v in report.items() if k != 'local_check'}, indent=2))
    print(f'5.   report at s3://{C.BUCKET}/{REPORT_KEY}')


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else '~/Downloads/archive/HI-Medium_Patterns.txt')
