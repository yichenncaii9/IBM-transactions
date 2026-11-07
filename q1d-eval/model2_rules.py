"""Model 2 (baseline): fixed rule engine on motif counts -- no learning.

The Neo4j motif counts are not ready yet, so this script creates MOCK counts
(random integers) for every account. Once C posts the real counts, delete the
"mock data" block and load the real table instead; the scoring function stays the same.

Usage: python model2_rules.py [path_to_csv]
Output: model2_predictions.csv  (columns: account, loop_count, chain_count,
        scatter_count, gather_count, score)
"""
import sys

import numpy as np
import pandas as pd

CSV_PATH = sys.argv[1] if len(sys.argv) > 1 else "HI-Medium_sample.csv"
OUT_PATH = "model2_predictions.csv"
SEED = 42

# ---- Rule thresholds and points (kept in one place so the team can tweak them) ----
LOOP_LIMIT, LOOP_PTS = 5, 50
CHAIN_LIMIT, CHAIN_PTS = 3, 30
FAN_LIMIT, FAN_PTS = 10, 20      # applies to scatter OR gather
MAX_SCORE = 100

# ---- 1. Load the CSV and build account IDs ----
# The raw header repeats "Account", so we supply our own column names.
COLS = ["ts", "from_bank", "from_acct", "to_bank", "to_acct",
        "amt_recv", "recv_ccy", "amt_paid", "pay_ccy", "fmt", "is_laund"]
# Keep bank IDs / account numbers as strings to preserve leading zeros.
df = pd.read_csv(CSV_PATH, header=0, names=COLS,
                 dtype={"from_bank": str, "from_acct": str, "to_bank": str, "to_acct": str})

# Same "bank_id|account_number" format as the SQL files.
from_ids = df["from_bank"] + "|" + df["from_acct"]
to_ids = df["to_bank"] + "|" + df["to_acct"]
accounts = pd.Series(pd.concat([from_ids, to_ids]).unique(), name="account")
print(f"Rows: {len(df)} | Unique accounts: {len(accounts)}")

# ---- 2. MOCK DATA: fake motif counts (replace with Neo4j output later) ----
rng = np.random.default_rng(SEED)
n = len(accounts)
feats = pd.DataFrame({
    "account": accounts,
    "loop_count": rng.integers(0, 11, n),     # 0..10
    "chain_count": rng.integers(0, 8, n),     # 0..7
    "scatter_count": rng.integers(0, 21, n),  # 0..20
    "gather_count": rng.integers(0, 21, n),   # 0..20
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
