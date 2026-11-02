"""Train and evaluate on the time split. Plain pandas + LightGBM; it works
the same on a PySpark DataFrame after .toPandas() on the 700k candidates.

Input: one parquet/CSV with transaction_id, split, is_laundering,
       is_new_attempt, attempt_id, and the look-back features (feat_*).
"""
import sys
import numpy as np, pandas as pd, lightgbm as lgb
from sklearn.metrics import average_precision_score, precision_recall_curve, f1_score

df = pd.read_parquet(sys.argv[1])
FEATS = [c for c in df.columns if c.startswith("feat_")]
tr, va, te = (df[df.split == s] for s in ("train", "val", "test"))   # gap and tail rows never used

# Imbalance is handled in training only. Pick ONE of these:
pos, neg = tr.is_laundering.sum(), (1 - tr.is_laundering).sum()
params = dict(objective="binary", metric="average_precision",
              learning_rate=0.05, num_leaves=63,
              scale_pos_weight=neg / pos,        # (a) class weight
              # bagging_fraction=..., or undersample negatives below  (b)
              verbose=-1)
# (b) tr = pd.concat([tr[tr.is_laundering == 1],
#                     tr[tr.is_laundering == 0].sample(frac=0.1, random_state=0)])
#     If you undersample, scores are no longer calibrated; the val threshold handles that.

model = lgb.train(params, lgb.Dataset(tr[FEATS], tr.is_laundering),
                  num_boost_round=2000,
                  valid_sets=[lgb.Dataset(va[FEATS], va.is_laundering)],
                  callbacks=[lgb.early_stopping(100)])

# Threshold: best F1 on VALIDATION, then frozen.
pv = model.predict(va[FEATS])
p, r, t = precision_recall_curve(va.is_laundering, pv)
f1 = 2 * p * r / np.clip(p + r, 1e-12, None)
thr = t[np.nanargmax(f1[:-1])]

pt = model.predict(te[FEATS]); yhat = pt >= thr; y = te.is_laundering.to_numpy()
def recall(mask):
    m = mask & (y == 1)
    return yhat[m].mean() if m.any() else float("nan"), int(m.sum())

print(f"test prevalence     {y.mean():.3%}   (val {va.is_laundering.mean():.3%})")
print(f"PR-AUC              {average_precision_score(y, pt):.3f}   (random = prevalence)")
print(f"F1 @ val threshold  {f1_score(y, yhat):.3f}   threshold={thr:.4f}")
print(f"alerts              {yhat.sum():,} of {len(y):,}")
new = te.is_new_attempt.to_numpy() == 1
known = te.attempt_id.notna().to_numpy()
for name, m in [("recall, all laundering", np.ones_like(new)),
                ("recall, new attempts only (honest)", new),
                ("recall, attempts begun before train end", known & ~new),
                ("recall, not in Patterns.txt", ~known)]:
    rc, n = recall(m)
    print(f"{name:42s} {rc:.3f}  (n={n:,})")
