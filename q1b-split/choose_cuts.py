"""Pick train/val/test day cuts the Multi-GNN way, plus two additions:
positives count toward the score, and G gap days sit between the parts.

Input: daily_counts.csv from step 1 of split_queries.sql
        (columns: day, n_rows, n_pos), one row per calendar day.
Usage:  python choose_cuts.py daily_counts.csv --gap 2 --alpha 0.5 --last-day 2022-09-16
"""
import argparse, itertools
import pandas as pd

TARGET = (0.6, 0.2, 0.2)

def score(rows, pos, alpha):
    # Multi-GNN score: worst relative error of each part's share vs target.
    # Here it is a blend of the row-share error and the positive-share error.
    def worst(xs):
        tot = sum(xs)
        return max(abs(x / tot - t) / t for x, t in zip(xs, TARGET))
    return (1 - alpha) * worst(rows) + alpha * worst(pos)

def search(df, gap, alpha, min_pos):
    n, best = len(df), None
    r, p = df.n_rows.to_numpy(), df.n_pos.to_numpy()
    # train = [0, i), gap, val = [i+gap, j), gap, test = [j+gap, n)
    for i, j in itertools.combinations(range(1, n), 2):
        if j - (i + gap) < 1 or n - (j + gap) < 1:
            continue
        parts = [(0, i), (i + gap, j), (j + gap, n)]
        rows = [r[a:b].sum() for a, b in parts]
        pos = [p[a:b].sum() for a, b in parts]
        if min(pos[1:]) < min_pos:
            continue
        s = score(rows, pos, alpha)
        if best is None or s < best[0]:
            best = (s, parts, rows, pos)
    return best

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--gap", type=int, default=2, help="gap days G")
    ap.add_argument("--alpha", type=float, default=0.5, help="0 = IBM rows only, 1 = positives only")
    ap.add_argument("--min-pos", type=int, default=300, help="min positives in val and in test")
    ap.add_argument("--last-day", default=None, help="drop days after this (tail artifact)")
    a = ap.parse_args()
    df = pd.read_csv(a.csv, parse_dates=["day"]).sort_values("day").reset_index(drop=True)
    if a.last_day:
        df = df[df.day <= a.last_day].reset_index(drop=True)
    best = search(df, a.gap, a.alpha, a.min_pos)
    if best is None:
        raise SystemExit("no cut meets --min-pos; lower it or the gap")
    s, parts, rows, pos = best
    print(f"score={s:.3f}  gap={a.gap}  alpha={a.alpha}")
    for name, (lo, hi), nr, npos in zip(["train", "val", "test"], parts, rows, pos):
        print(f"{name:5s} {df.day[lo].date()} .. {df.day[hi-1].date()}  "
              f"rows={nr:>10,} ({nr/sum(rows):.1%})  pos={npos:>7,} ({npos/sum(pos):.1%})  "
              f"prev={npos/nr:.3%}")
    for k, (lo, hi) in enumerate(parts[:2]):
        nxt = parts[k + 1][0]
        if nxt > hi:
            print(f"gap   {df.day[hi].date()} .. {df.day[nxt-1].date()}  (context only, not trained or scored)")
