"""Model 3 (baseline): random score per account -- the floor every other model must beat.

Usage: python model3_random.py [path_to_csv]
Output: model3_predictions.csv  (columns: account, score)
"""
import sys

import numpy as np
import pandas as pd

CSV_PATH = sys.argv[1] if len(sys.argv) > 1 else "HI-Medium_sample.csv"
OUT_PATH = "model3_predictions.csv"
SEED = 42  # fixed seed so the team gets the same "random" scores on every run

# The raw header has "Account" twice (sender and receiver), so we skip the header
# and give the columns our own unique names instead.
COLS = ["ts", "from_bank", "from_acct", "to_bank", "to_acct",
        "amt_recv", "recv_ccy", "amt_paid", "pay_ccy", "fmt", "is_laund"]
# Read bank IDs and account numbers as strings, otherwise pandas drops the
# leading zeros (e.g. "020" would become 20) and the account IDs would not match.
df = pd.read_csv(CSV_PATH, header=0, names=COLS,
                 dtype={"from_bank": str, "from_acct": str, "to_bank": str, "to_acct": str})

# Build account IDs in the same "bank_id|account_number" format as the SQL files.
from_ids = df["from_bank"] + "|" + df["from_acct"]
to_ids = df["to_bank"] + "|" + df["to_acct"]

# An account can be a sender or a receiver, so stack both and keep unique values.
accounts = pd.Series(pd.concat([from_ids, to_ids]).unique(), name="account")
print(f"Rows: {len(df)} | Unique accounts: {len(accounts)}")

# Draw one uniform random score in [0, 1) per account.
rng = np.random.default_rng(SEED)
preds = pd.DataFrame({"account": accounts, "score": rng.random(len(accounts))})

# Sort highest first so the file reads like a ranked list.
preds = preds.sort_values("score", ascending=False).reset_index(drop=True)

print("\nTop 10 accounts by random score:")
print(preds.head(10).to_string(index=False))

preds.to_csv(OUT_PATH, index=False)
print(f"\nSaved {len(preds)} rows to {OUT_PATH}")
