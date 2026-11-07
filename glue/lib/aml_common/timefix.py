"""Corrected timestamps for out-of-order laundering hops (Spark-free).

The IBM generator sometimes stamps a relay hop (money leaving an account)
earlier than the money arriving there in the same laundering attempt.
Patterns.txt lists each attempt's transfers in money-flow order (a cycle
starts with the origin's first transfer and ends with the transfer back),
so we use that order to decide which inflows feed a hop.

Rule, per attempt, walking rows in file order:
    feeders(o) = earlier-listed rows i in the same attempt with i.dst == o.src
    if o has feeders and none of them arrives at or before o's time,
        fixed_ts(o) = earliest fixed_ts among its feeders
    else
        fixed_ts(o) = ts(o)
Feeders use their own fixed_ts, so a fix carries down the chain.
The original timestamp is never changed; this only produces a second column.

Only rows in Patterns.txt can be fixed (about 65% of HI and 24% of LI laundering),
so the fixed column is derived from labels: use it for the Q1 tracer and for
checking the split, never as a model feature (it would leak the answer).
"""
import collections
from datetime import datetime

TS_FORMAT = '%Y/%m/%d %H:%M'


def fix_attempt(rows):
    """rows: list of (ts, src, dst) in file order for one attempt.

    Returns a list of fixed timestamps, same order and type as ts.
    """
    fixed = []
    inflow = collections.defaultdict(list)  # account -> fixed ts of earlier-listed arrivals
    for ts, src, dst in rows:
        feeders = inflow.get(src)
        if feeders and min(feeders) > ts:
            new_ts = min(feeders)
        else:
            new_ts = ts
        fixed.append(new_ts)
        if src != dst:
            inflow[dst].append(new_ts)
    return fixed


def fix_patterns(pattern_rows):
    """pattern_rows: tuples from aml_common.patterns.parse_lines (COLUMNS order).

    Returns a list of dicts, one per row, with the natural key used to match
    the transaction plus attempt_id, typology, ts (datetime) and fixed_ts.
    """
    by_attempt = collections.OrderedDict()
    for r in pattern_rows:
        by_attempt.setdefault(r[0], []).append(r)

    out = []
    for attempt_id, rows in by_attempt.items():
        parsed = [(datetime.strptime(r[3], TS_FORMAT), r[4] + '|' + r[5], r[6] + '|' + r[7])
                  for r in rows]
        fixed = fix_attempt(parsed)
        for r, (ts, _, _), fts in zip(rows, parsed, fixed):
            out.append({
                'attempt_id': attempt_id, 'typology': r[1], 'ts_raw': r[3], 'ts': ts,
                'from_bank': r[4], 'from_account': r[5], 'to_bank': r[6], 'to_account': r[7],
                'amount_paid': r[10], 'payment_currency': r[11], 'payment_format': r[12],
                'fixed_ts': fts,
            })
    return out


def summarise(fixed_rows):
    """Count changed rows overall and per typology, plus the average shift in hours."""
    total = collections.Counter()
    changed = collections.Counter()
    shift_h = collections.defaultdict(float)
    for r in fixed_rows:
        total[r['typology']] += 1
        if r['fixed_ts'] != r['ts']:
            changed[r['typology']] += 1
            shift_h[r['typology']] += (r['fixed_ts'] - r['ts']).total_seconds() / 3600
    per_type = {
        t: {'rows': total[t], 'changed': changed[t],
            'changed_pct': round(100.0 * changed[t] / total[t], 2),
            'avg_shift_hours': round(shift_h[t] / changed[t], 1) if changed[t] else 0.0}
        for t in sorted(total)
    }
    n, c = sum(total.values()), sum(changed.values())
    return {'rows': n, 'changed': c, 'changed_pct': round(100.0 * c / n, 2) if n else 0.0,
            'by_typology': per_type}
