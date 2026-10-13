"""Q1 chain tracer: temporal BFS over laundering transactions.

Spark-free so it can be unit-tested locally and run on the Glue driver after
Spark has filtered the full dataset down to laundering edges (~35K HI, ~16K LI).

Each edge is a dict with keys:
    rid   unique transaction id
    ts    timestamp (anything orderable, e.g. datetime)
    u, v  sender / receiver node id (account, or entity for owner-level runs)
    uent, vent  sender / receiver entity id (used for the cheque cash-out rule)
    fmt   payment format
    usd   amount normalised to USD

Rules:
    - Edges are processed once in (ts, rid) order.
    - An edge continues a chain from an inbound edge to its sender only if that
      inbound edge happened at or before it (time order) and its amount is
      [amount_lo, amount_hi] x the inbound amount (same money moving on).
    - hops = 1 + the fewest hops among qualifying inbound edges (BFS distance),
      or 1 if none qualify (a new chain starts here).
    - roots = ids of the edges that started the chains this edge continues.
    - An edge is terminal (its receiver is a cash-out point) if the receiver
      sends no laundering edge at or after it, or it pays out as Cash, or as a
      Cheque to a different entity.
"""
import bisect
import collections

AMOUNT_LO = 0.8
AMOUNT_HI = 1.25


def trace(edges, amount_lo=AMOUNT_LO, amount_hi=AMOUNT_HI):
    """Return {rid: {'hops', 'roots', 'terminal', 'u', 'v'}}."""
    ordered = sorted(edges, key=lambda e: (e['ts'], e['rid']))
    out_ts = collections.defaultdict(list)
    for e in ordered:
        out_ts[e['u']].append(e['ts'])

    inbound = collections.defaultdict(list)  # node -> [(hops, usd, roots)]
    res = {}
    for e in ordered:
        u, v, t = e['u'], e['v'], e['ts']
        preds = [p for p in inbound[u] if amount_lo <= e['usd'] / p[1] <= amount_hi]
        hops = 1 + min((p[0] for p in preds), default=0)
        roots = set().union(*(p[2] for p in preds)) if preds else {e['rid']}

        later = out_ts.get(v, [])
        sends_later = bisect.bisect_left(later, t) < len(later)
        terminal = (not sends_later) or e['fmt'] == 'Cash' or (
            e['fmt'] == 'Cheque' and e['uent'] != e['vent'])

        res[e['rid']] = {'hops': hops, 'roots': roots, 'terminal': terminal, 'u': u, 'v': v}
        if u != v:
            inbound[v].append((hops, e['usd'], roots))
    return res


def cash_out_ranking(edges, traced):
    """Rank receivers of terminal edges by the number of distinct chains ending there."""
    chains = collections.defaultdict(set)
    usd_in = collections.Counter()
    for e in edges:
        usd_in[e['v']] += e['usd']
        t = traced[e['rid']]
        if t['terminal']:
            chains[t['v']] |= t['roots']
    return sorted(chains, key=lambda a: (-len(chains[a]), -usd_in[a])), chains
