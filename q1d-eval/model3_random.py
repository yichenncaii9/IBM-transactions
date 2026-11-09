"""Model 3 (baseline): random score per account -- the floor every other model must beat.

Runs on the REAL accounts in S3 (the same accounts LightGBM scores), not the sample CSV.
Credentials/bucket: see real_data.py (boto3 default chain + aws/config.py).

Usage: python model3_random.py [period]        # period = train | val | test (default val)
Output: model3_predictions.csv  (columns: account, score)
"""
import sys

import numpy as np
import pandas as pd

from real_data import load_accounts

PERIOD = sys.argv[1] if len(sys.argv) > 1 else "val"
OUT_PATH = "model3_predictions.csv"
SEED = 42  # fixed seed so the team gets the same "random" scores on every run

accounts = load_accounts(PERIOD)["acct"].rename("account")
print(f"Period: {PERIOD} | Unique accounts: {len(accounts)}")

# Draw one uniform random score in [0, 1) per account.
rng = np.random.default_rng(SEED)
preds = pd.DataFrame({"account": accounts, "score": rng.random(len(accounts))})

# Sort highest first so the file reads like a ranked list.
preds = preds.sort_values("score", ascending=False).reset_index(drop=True)

print("\nTop 10 accounts by random score:")
print(preds.head(10).to_string(index=False))

preds.to_csv(OUT_PATH, index=False)
print(f"\nSaved {len(preds)} rows to {OUT_PATH}")
