import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'glue', 'lib'))
from aml_common.tracer import cash_out_ranking, trace  # noqa: E402

T0 = datetime(2022, 9, 1)


def edge(rid, hour, u, v, usd, fmt='ACH', uent=None, vent=None):
    return {'rid': rid, 'ts': T0 + timedelta(hours=hour), 'u': u, 'v': v, 'usd': usd,
            'fmt': fmt, 'uent': uent or 'E' + u, 'vent': vent or 'E' + v}


def test_stack_chain_counts_hops_and_ends_at_last_account():
    edges = [edge(1, 0, 'A', 'B', 1000), edge(2, 1, 'B', 'C', 1050), edge(3, 2, 'C', 'D', 1100)]
    r = trace(edges)
    assert [r[i]['hops'] for i in (1, 2, 3)] == [1, 2, 3]
    assert [r[i]['terminal'] for i in (1, 2, 3)] == [False, False, True]
    assert r[3]['roots'] == {1}


def test_hop_cannot_go_back_in_time():
    # B->C happens before A->B, so it cannot carry A's money.
    edges = [edge(1, 5, 'A', 'B', 1000), edge(2, 1, 'B', 'C', 1000)]
    r = trace(edges)
    assert r[2]['hops'] == 1
    assert r[1]['terminal']  # B never sends after receiving


def test_amount_mismatch_starts_a_new_chain():
    edges = [edge(1, 0, 'A', 'B', 1000), edge(2, 1, 'B', 'C', 5000)]
    assert trace(edges)[2]['hops'] == 1


def test_takes_fewest_hops_when_chains_merge():
    # B is reached directly (1 hop) and via X (2 hops); B->C takes the shorter route.
    edges = [edge(1, 0, 'A', 'X', 1000), edge(2, 1, 'X', 'B', 1000),
             edge(3, 2, 'A', 'B', 1000), edge(4, 3, 'B', 'C', 1000)]
    r = trace(edges)
    assert r[4]['hops'] == 2
    assert r[4]['roots'] == {1, 3}


def test_cash_and_cross_entity_cheque_are_exits():
    edges = [edge(1, 0, 'A', 'B', 1000, fmt='Cash'), edge(2, 1, 'B', 'C', 1000),
             edge(3, 2, 'C', 'D', 1000, fmt='Cheque'),
             edge(4, 3, 'D', 'D2', 1000, fmt='Cheque', uent='same', vent='same'), edge(5, 4, 'D2', 'Z', 1000)]
    r = trace(edges)
    assert r[1]['terminal'] and r[3]['terminal']
    assert not r[4]['terminal']  # cheque to own account at another bank is not a cash-out


def test_ranking_counts_distinct_chains():
    edges = [edge(1, 0, 'A', 'HUB', 1000), edge(2, 0, 'B', 'HUB', 1000), edge(3, 0, 'C', 'SIDE', 9000)]
    ranked, chains = cash_out_ranking(edges, trace(edges))
    assert ranked[0] == 'HUB' and len(chains['HUB']) == 2
