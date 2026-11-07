"""Run model 2 (rules) and model 3 (random) on the real val accounts and score
them next to LightGBM (model 1) on one baseline.

    python q1d-eval/run_models.py [path/to/account_scores.csv]

Inputs  account_scores.csv   LightGBM scores + labels (acct, period, model, score, label)
        s3://<bucket>/results/neo4j/motifs/period=val/   real motif counts (Part C)
Output  q1d-eval/out/model_scores_val.csv   acct, model, score, label (all models)
        q1d-eval/out/eval_summary.csv       one row per model
        q1d-eval/out/eval_deciles.csv       per-decile precision / recall / lift
"""
import os
import sys

import numpy as np
import pandas as pd


def average_precision_score(y, s):
    """Same as sklearn's: sum over distinct thresholds of (R_k - R_{k-1}) * P_k."""
    o = np.argsort(-s, kind='stable')
    y, s = y[o], s[o]
    last = np.r_[np.flatnonzero(np.diff(s)), len(s) - 1]   # end of each tie group
    tp = np.cumsum(y)[last]
    prec, rec = tp / (last + 1), tp / y.sum()
    return float(np.sum(np.diff(np.r_[0, rec]) * prec))

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'aws'))
import config as C  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'out')
SCORES = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser('~/Desktop/account_scores.csv')
SEED = 42

# ---- Model 2 rules: same thresholds and points as model2_rules.py ----
LOOP_LIMIT, LOOP_PTS = 5, 50
CHAIN_LIMIT, CHAIN_PTS = 3, 30
FAN_LIMIT, FAN_PTS = 10, 20
MAX_SCORE = 100


def rule_score(f):
    s = (f.loop_count > LOOP_LIMIT) * LOOP_PTS
    s = s + (f.chain_count > CHAIN_LIMIT) * CHAIN_PTS
    s = s + ((f.scatter_count > FAN_LIMIT) | (f.gather_count > FAN_LIMIT)) * FAN_PTS
    return s.clip(upper=MAX_SCORE)


def evaluate(name, y, s):
    """Rank by score (highest first, stable), then AP + top-k + deciles."""
    order = np.argsort(-s, kind='stable')
    y_r = y[order]
    n, P = len(y), y.sum()
    rate = P / n
    ap = average_precision_score(y, s)
    row = dict(model=name, rows=n, positives=int(P), pos_rate=rate,
               ap=ap, x_random=ap / rate)
    cum = np.cumsum(y_r)
    for pct in (10, 25, 30, 50):
        k = int(round(n * pct / 100))
        row[f'precision_top_{pct}pct'] = cum[k - 1] / k
        row[f'recall_top_{pct}pct'] = cum[k - 1] / P
        row[f'lift_top_{pct}pct'] = cum[k - 1] / k / rate
    for k in (100, 500, 1000):
        row[f'precision_at_{k}'] = cum[k - 1] / k
        row[f'recall_at_{k}'] = cum[k - 1] / P
    dec = []
    for d, idx in enumerate(np.array_split(np.arange(n), 10), start=1):
        hits = y_r[idx].sum()
        dec.append(dict(model=name, decile=d, accounts=len(idx), positives=int(hits),
                        precision=hits / len(idx), lift=hits / len(idx) / rate,
                        cum_recall=cum[idx[-1]] / P))
    return row, dec


def main():
    os.makedirs(OUT, exist_ok=True)
    lgb = pd.read_csv(SCORES, dtype={'acct': str})
    lgb = lgb[lgb.period == 'val']
    labels = lgb[lgb.model == 'no_taint'][['acct', 'label']]

    m = pd.read_parquet(f's3://{C.BUCKET}/results/neo4j/motifs/period=val/')
    m = labels.merge(m, on='acct', how='left').fillna(0)
    assert len(m) == len(labels), 'motif/label account mismatch'

    # Model 2 on real counts (loops = 2-account + 3-account loops)
    f = pd.DataFrame({'loop_count': m.loops2 + m.loops3, 'chain_count': m.chains,
                      'scatter_count': m.scatter, 'gather_count': m.gather})
    raw = rule_score(f).to_numpy(float)
    activity = f.sum(axis=1).to_numpy(float)
    # Same tie-break as model2_rules.py: total motif activity within a score.
    m2 = raw + activity / (activity.max() + 1)

    # Model 3: uniform random, fixed seed
    m3 = np.random.default_rng(SEED).random(len(m))

    parts = [lgb[['acct', 'model', 'score', 'label']]
             .replace({'model': {'no_taint': 'm1_lgbm_no_taint',
                                 'with_taint': 'm1_lgbm_with_taint'}})]
    for name, s in (('m2_rules', m2), ('m3_random', m3)):
        parts.append(pd.DataFrame({'acct': m.acct, 'model': name, 'score': s, 'label': m.label}))
    allp = pd.concat(parts, ignore_index=True)
    allp.to_csv(os.path.join(OUT, 'model_scores_val.csv'), index=False)

    print('Model 2 raw score distribution (val):')
    print(pd.Series(raw).value_counts().sort_index(ascending=False).to_string())

    rows, decs = [], []
    for name, g in allp.groupby('model', sort=True):
        r, d = evaluate(name, g.label.to_numpy(int), g.score.to_numpy(float))
        rows.append(r)
        decs += d
    summ = pd.DataFrame(rows)
    summ.to_csv(os.path.join(OUT, 'eval_summary.csv'), index=False)
    pd.DataFrame(decs).to_csv(os.path.join(OUT, 'eval_deciles.csv'), index=False)

    cols = ['model', 'ap', 'x_random', 'precision_top_10pct', 'recall_top_10pct',
            'lift_top_10pct', 'precision_at_100', 'precision_at_1000']
    print('\n' + summ[cols].to_string(index=False, float_format='%.4f'))
    piv = pd.DataFrame(decs).pivot(index='decile', columns='model', values='lift')
    print('\nLift by decile:\n' + piv.to_string(float_format='%.2f'))


if __name__ == '__main__':
    main()
