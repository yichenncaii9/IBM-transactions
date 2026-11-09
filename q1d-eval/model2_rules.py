"""Model 2 (baseline): fixed rule engine on motif counts -- no learning.

Runs on the REAL Neo4j motif counts in S3 (results/neo4j/motifs/period=<p>/) over the real
accounts LightGBM scores. Accounts with no motif row get 0 for every count.
Credentials/bucket: see real_data.py (boto3 default chain + aws/config.py).

Usage: python model2_rules.py [period]        # period = train | val | test (default val)
Output: model2_predictions.csv  (columns: account, loop_count, chain_count,
        scatter_count, gather_count, score)
"""
import sys

import numpy as np
import pandas as pd

from real_data import load_accounts, load_motifs

PERIOD = sys.argv[1] if len(sys.argv) > 1 else "val"
OUT_PATH = "model2_predictions.csv"

# ---- Rule thresholds and points (kept in one place so the team can tweak them) ----
LOOP_LIMIT, LOOP_PTS = 5, 50
CHAIN_LIMIT, CHAIN_PTS = 3, 30
FAN_LIMIT, FAN_PTS = 10, 20      # applies to scatter OR gather
MAX_SCORE = 100

# ---- 1. Load real accounts and motif counts from S3 ----
accounts = load_accounts(PERIOD)
motifs = load_motifs(PERIOD)
m = accounts.merge(motifs, on="acct", how="left").fillna(0)
assert len(m) == len(accounts), "duplicate accounts in motif table"
print(f"Period: {PERIOD} | Accounts: {len(accounts)} | with motif row: {motifs.acct.isin(accounts.acct).sum()}")

feats = pd.DataFrame({
    "account": m["acct"],
    "loop_count": m["loops2"] + m["loops3"],   # 2-account + 3-account loops
    "chain_count": m["chains"],
    "scatter_count": m["scatter"],
    "gather_count": m["gather"],
})


# ---- 3. Rule engine ----
def score_accounts(f: pd.DataFrame) -> pd.Series:
    """Return a 0-100 risk score per row using fixed thresholds.

    Each rule is a True/False column; multiplying by its points adds the points
    only where the rule fires. All comparisons are vectorised (no row loops).
    """
    score = (f["loop_count"] > LOOP_LIMIT) * LOOP_PTS            # loops: +50
    score = score + (f["chain_count"] > CHAIN_LIMIT) * CHAIN_PTS  # chains: +30
    fan_hit = (f["scatter_count"] > FAN_LIMIT) | (f["gather_count"] > FAN_LIMIT)
    score = score + fan_hit * FAN_PTS                             # scatter OR gather: +20 (once)
    return score.clip(upper=MAX_SCORE)                            # cap at 100


feats["score"] = score_accounts(feats)

# ---- 4. Rank, show top 10, save ----
# Many accounts tie on score (only a few possible values), so break ties by
# total motif activity to keep the ordering stable and sensible.
feats["_activity"] = feats[["loop_count", "chain_count", "scatter_count", "gather_count"]].sum(axis=1)
preds = (feats.sort_values(["score", "_activity"], ascending=False)
              .drop(columns="_activity").reset_index(drop=True))

print("\nTop 10 highest-risk accounts:")
print(preds.head(10).to_string(index=False))
print("\nScore distribution:")
print(preds["score"].value_counts().sort_index(ascending=False).to_string())

preds.to_csv(OUT_PATH, index=False)
print(f"\nSaved {len(preds)} rows to {OUT_PATH}")
