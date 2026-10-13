"""Q1 pilot: run the tracer on all laundering edges and score it against Patterns.txt.

Usage: python poc/q1_pilot.py [db_path]   (run build_db.py first)
"""
import collections
import os
import statistics as st
import sys

import duckdb

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'glue', 'lib'))
from aml_common.tracer import cash_out_ranking, trace  # noqa: E402

DB = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), 'aml.duckdb')
con = duckdb.connect(DB, read_only=True)


def longest_path_hops(es):
    """Answer-key hop count for one attempt: longest time-ordered path, independent of the tracer."""
    best, top = collections.defaultdict(int), 0
    for e in sorted(es, key=lambda e: (e['ts'], e['rid'])):
        h = best[e['u']] + 1
        top = max(top, h)
        if e['u'] != e['v']:
            best[e['v']] = max(best[e['v']], h)
    return top


def attempt_id(e):
    a = e['attempt_id']
    return int(a) if a is not None and a == a else None


for ds in ['HI', 'LI']:
    edges = con.execute(f"""select rid, ts, from_bank||':'||from_acct u, to_bank||':'||to_acct v,
        from_entity uent, to_entity vent, fmt, usd, attempt_id, typology
        from lndp where ds='{ds}'""").df().to_dict('records')
    traced = trace(edges)

    attempts = collections.defaultdict(list)
    for e in edges:
        if attempt_id(e) is not None:
            attempts[attempt_id(e)].append(e)

    # Ground truth per attempt: sinks = receivers that never send inside the attempt;
    # true hops = longest time-ordered path inside the attempt.
    true_sinks, rows = set(), []
    for a, es in attempts.items():
        sinks = {e['v'] for e in es} - {e['u'] for e in es if e['u'] != e['v']}
        true_sinks |= sinks
        true_h = longest_path_hops(es)
        our_h = max(traced[e['rid']]['hops'] for e in es)
        found = {traced[e['rid']]['v'] for e in es if traced[e['rid']]['terminal']}
        rows.append({'typ': es[0]['typology'], 'true_h': true_h, 'our_h': our_h,
                     'recall': len(sinks & found) / len(sinks) if sinks else None})

    print(f"\n######## {ds}: {len(edges)} laundering edges, {len(attempts)} attempts")
    print(f"{'typology':16}{'attempts':>9}{'sinkRecall':>11}{'hopExact':>9}{'hopMAE':>7}{'medianHops':>11}")
    by = collections.defaultdict(list)
    for r in rows:
        by[r['typ']].append(r)
    for t, rs in sorted(by.items()) + [('ALL', rows)]:
        rec = [r['recall'] for r in rs if r['recall'] is not None]
        print(f"{t:16}{len(rs):9}{(st.mean(rec) if rec else float('nan')):11.3f}"
              f"{st.mean(r['true_h'] == r['our_h'] for r in rs):9.3f}"
              f"{st.mean(abs(r['true_h'] - r['our_h']) for r in rs):7.2f}"
              f"{st.median(r['true_h'] for r in rs):11}")

    ranked, chains = cash_out_ranking(edges, traced)
    usd_in, indeg = collections.Counter(), collections.Counter()
    for e in edges:
        usd_in[e['v']] += e['usd']
        indeg[e['v']] += 1
    by_usd = [a for a, _ in usd_in.most_common()]
    by_deg = [a for a, _ in indeg.most_common()]
    print(f"true sink accounts={len(true_sinks)}, cash-out accounts={len(chains)}, "
          f"pooled sink recall={len(true_sinks & set(chains)) / len(true_sinks):.3f}")
    for k in (25, 100, 500):
        p = lambda rk: sum(a in true_sinks for a in rk[:k]) / k  # noqa: E731
        print(f"precision@{k}: tracer={p(ranked):.2f} top_usd={p(by_usd):.2f} top_in_degree={p(by_deg):.2f}")

    hops = collections.Counter(x['hops'] for x in traced.values() if x['terminal'])
    n = sum(hops.values())
    print(f"chains ending within 2 hops={(hops[1] + hops[2]) / n:.3f}, "
          f"5+ hops={sum(v for h, v in hops.items() if h >= 5) / n:.3f}, max={max(hops)}")

    accts = collections.Counter()
    for a, es in attempts.items():
        for node in {e['u'] for e in es} | {e['v'] for e in es}:
            accts[node] += 1
    print(f"scheme accounts={len(accts)}, shared by 2+ schemes={sum(c > 1 for c in accts.values())}")
