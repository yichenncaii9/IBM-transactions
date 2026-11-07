"""Part C: graph shapes per account per period, and scheme groups on the test days.

    python q1c-graph/build_graph_features.py

Input   D's per-period edge lists: s3://<bucket>/results/rule-features/q1/edges/period=*/
        (one row per sender-receiver pair, USD summed, self-transfers removed, B's dates)
        D's features (test) for the rule-flagged scheme run.
Shapes ignore transaction times (the prof's advice: timestamps are unreliable).

Output  results/neo4j/motifs/period=<p>/   period, acct, gather, scatter, chains, loops2, loops3
            gather  = distinct accounts that send to it          (many -> one)
            scatter = distinct accounts it sends to              (one -> many)
            chains  = 2-hop paths passing through it (in x out)  (A -> it -> C)
            loops2  = accounts it both sends to and receives from (A <-> B)
            loops3  = 3-account loops it is in                   (A -> B -> C -> A)
        results/neo4j/schemes/   acct, scheme_all, size_all, scheme_flagged, size_flagged
            scheme_all     = weakly connected group over all test transfers
            scheme_flagged = group over transfers between rule-flagged test accounts only
        results/neo4j/reports/graph_summary.json
Tables  is459_aml.graph_motifs, is459_aml.graph_schemes
"""
import io
import json
import os
import sys
import time
from collections import defaultdict

import boto3
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'aws'))
import config as C  # noqa: E402

DB = C.DATABASE
PERIODS = ['train', 'val', 'test']
s3 = boto3.client('s3', region_name=C.REGION)


def read_prefix(prefix, columns=None):
    keys = [o['Key'] for p in s3.get_paginator('list_objects_v2').paginate(Bucket=C.BUCKET, Prefix=prefix)
            for o in p.get('Contents', []) if o['Key'].endswith('.parquet')]
    frames = [pq.read_table(io.BytesIO(s3.get_object(Bucket=C.BUCKET, Key=k)['Body'].read()),
                            columns=columns).to_pandas() for k in keys]
    return pd.concat(frames, ignore_index=True)


def write_parquet(df, key):
    buf = io.BytesIO()
    pq.write_table(pa.Table.from_pandas(df, preserve_index=False), buf)
    s3.put_object(Bucket=C.BUCKET, Key=key, Body=buf.getvalue())


def clear(prefix):
    assert prefix.startswith('results/neo4j/motifs/') or prefix.startswith('results/neo4j/schemes/')
    keys = [o['Key'] for p in s3.get_paginator('list_objects_v2').paginate(Bucket=C.BUCKET, Prefix=prefix)
            for o in p.get('Contents', [])]
    for i in range(0, len(keys), 1000):
        s3.delete_objects(Bucket=C.BUCKET, Delete={'Objects': [{'Key': k} for k in keys[i:i + 1000]]})


def shapes(edges):
    """edges: DataFrame src, dst (unique pairs, no self loops). Returns per-account counts."""
    codes, accts = pd.factorize(pd.concat([edges.src, edges.dst], ignore_index=True))
    n, m = len(accts), len(edges)
    s, d = codes[:m].astype(np.int64), codes[m:].astype(np.int64)

    scatter = np.bincount(s, minlength=n)
    gather = np.bincount(d, minlength=n)
    chains = scatter.astype(np.int64) * gather.astype(np.int64)

    key = s * n + d
    rev = np.isin(d * n + s, key)
    loops2 = np.bincount(s[rev], minlength=n)

    # 3-loops: for edge u->v, every w with v->w and w->u closes u->v->w->u.
    out_sets, in_sets = defaultdict(set), defaultdict(set)
    for u, v in zip(s.tolist(), d.tolist()):
        out_sets[u].add(v)
        in_sets[v].add(u)
    loops3 = np.zeros(n, dtype=np.int64)
    for u, v in zip(s.tolist(), d.tolist()):
        a, b = out_sets.get(v), in_sets.get(u)
        if not a or not b:
            continue
        ws = a & b if len(a) < len(b) else b & a
        if ws:
            k = len(ws)
            loops3[u] += k
            loops3[v] += k
            for w in ws:
                loops3[w] += 1
    loops3 //= 3  # each loop is found once from each of its 3 edges

    return pd.DataFrame({'acct': accts, 'gather': gather, 'scatter': scatter, 'chains': chains,
                         'loops2': loops2, 'loops3': loops3}), s, d, accts


def wcc(s, d, n):
    g = coo_matrix((np.ones(len(s), dtype=np.int8), (s, d)), shape=(n, n))
    _, labels = connected_components(g, directed=True, connection='weak')
    sizes = np.bincount(labels)
    return labels, sizes[labels], sizes


def main():
    summary = {}
    clear('results/neo4j/motifs/')
    for p in PERIODS:
        t0 = time.time()
        edges = read_prefix(f'results/rule-features/q1/edges/period={p}/', ['src', 'dst'])
        df, s, d, accts = shapes(edges)
        df.insert(0, 'period', p)
        write_parquet(df.drop(columns='period'), f'results/neo4j/motifs/period={p}/motifs.parquet')
        summary[p] = {'accounts': len(df), 'edges': len(edges),
                      'accounts_in_loops2': int((df.loops2 > 0).sum()),
                      'accounts_in_loops3': int((df.loops3 > 0).sum()),
                      'total_loops3': int(df.loops3.sum() // 3),
                      'seconds': round(time.time() - t0, 1)}
        print(p, summary[p], flush=True)
        if p == 'test':
            test = (df, s, d, accts)

    # Schemes on the test days.
    df, s, d, accts = test
    n = len(accts)
    lab_all, size_all, sizes_all = wcc(s, d, n)

    feats = read_prefix('results/rule-features/q1/features/period=test/',
                        ['acct', 'fan_ratio', 'flow_match', 'chain_score', 'taint'])
    # Rule-flagged = top 1% of test accounts by their strongest rule score.
    feats['top'] = feats[['fan_ratio', 'flow_match', 'chain_score', 'taint']].max(axis=1)
    cut = feats['top'].quantile(0.99)
    flagged = set(feats.loc[feats['top'] >= max(cut, 1e-9), 'acct'])
    is_flag = np.array([a in flagged for a in accts])
    keep = is_flag[s] & is_flag[d]
    lab_f, size_f, sizes_f = wcc(s[keep], d[keep], n)
    involved = np.zeros(n, dtype=bool)
    involved[s[keep]] = True
    involved[d[keep]] = True

    schemes = pd.DataFrame({'acct': accts, 'scheme_all': lab_all, 'size_all': size_all,
                            'scheme_flagged': np.where(involved, lab_f, -1),
                            'size_flagged': np.where(involved, size_f, 0)})
    clear('results/neo4j/schemes/')
    write_parquet(schemes, 'results/neo4j/schemes/schemes.parquet')

    top_all = np.sort(sizes_all)[::-1][:5].tolist()
    flagged_sizes = np.bincount(lab_f[involved]) if involved.any() else np.array([0])
    flagged_sizes = flagged_sizes[flagged_sizes > 0]
    summary['schemes'] = {
        'all_transfers': {'groups': int(len(sizes_all)), 'largest_5': top_all,
                          'largest_share_pct': round(100 * top_all[0] / n, 1)},
        'rule_flagged': {'flag_rule': 'top 1% of test accounts by max(fan, flow, chain, taint)',
                         'score_cut': round(float(cut), 3), 'flagged_accounts': len(flagged),
                         'accounts_in_groups': int(involved.sum()),
                         'groups_2plus': int((flagged_sizes >= 2).sum()),
                         'largest_5': np.sort(flagged_sizes)[::-1][:5].tolist()},
    }
    s3.put_object(Bucket=C.BUCKET, Key='results/neo4j/reports/graph_summary.json',
                  Body=json.dumps(summary, indent=2).encode())
    print(json.dumps(summary['schemes'], indent=2))

    C.athena(f'DROP TABLE IF EXISTS {DB}.graph_motifs')
    C.athena(f"""CREATE EXTERNAL TABLE {DB}.graph_motifs (
        acct string, gather bigint, scatter bigint, chains bigint, loops2 bigint, loops3 bigint)
      PARTITIONED BY (period string) STORED AS PARQUET
      LOCATION 's3://{C.BUCKET}/results/neo4j/motifs/'""")
    C.athena(f'MSCK REPAIR TABLE {DB}.graph_motifs')
    C.athena(f'DROP TABLE IF EXISTS {DB}.graph_schemes')
    C.athena(f"""CREATE EXTERNAL TABLE {DB}.graph_schemes (
        acct string, scheme_all bigint, size_all bigint, scheme_flagged bigint, size_flagged bigint)
      STORED AS PARQUET LOCATION 's3://{C.BUCKET}/results/neo4j/schemes/'""")
    print('tables ready:', f'{DB}.graph_motifs', f'{DB}.graph_schemes')


if __name__ == '__main__':
    main()
