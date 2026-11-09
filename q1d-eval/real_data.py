"""Shared S3 loaders for model 2 and model 3 (real data, same access path as q1c-graph).

Credentials: boto3's default chain (`aws configure` or AWS_* env vars), region and bucket
from aws/config.py (override with AWS_REGION / AML_BUCKET). Needs: boto3, pandas, pyarrow.
"""
import io
import os
import sys

import boto3
import pandas as pd
import pyarrow.parquet as pq

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'aws'))
import config as C  # noqa: E402

s3 = boto3.client('s3', region_name=C.REGION)


def read_prefix(prefix, columns=None):
    keys = [o['Key'] for p in s3.get_paginator('list_objects_v2').paginate(Bucket=C.BUCKET, Prefix=prefix)
            for o in p.get('Contents', []) if o['Key'].endswith('.parquet')]
    if not keys:
        raise SystemExit(f'no parquet files under s3://{C.BUCKET}/{prefix}')
    frames = [pq.read_table(io.BytesIO(s3.get_object(Bucket=C.BUCKET, Key=k)['Body'].read()),
                            columns=columns).to_pandas() for k in keys]
    return pd.concat(frames, ignore_index=True)


def load_accounts(period):
    """Every account scored in `period` (LightGBM's universe), as a one-column frame `acct`."""
    a = read_prefix(f'results/rule-features/q1/features/period={period}/', ['acct'])
    return a.drop_duplicates('acct').reset_index(drop=True)


def load_motifs(period):
    """Real Neo4j motif counts: acct, gather, scatter, chains, loops2, loops3."""
    return read_prefix(f'results/neo4j/motifs/period={period}/')
