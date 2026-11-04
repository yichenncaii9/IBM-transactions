import os
import sys

import pytest

pytest.importorskip("pyspark")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'glue'))
from rule_taint import hit_cutoffs, seeds, taint, train_hits_per_rule, with_taint  # noqa: E402

FEATURES_SCHEMA = 'period string, acct string, fan_ratio double, flow_match double, chain_score double'
EDGES_SCHEMA = 'period string, src string, dst string, usd double'


def scores(df):
    return {(r['period'], r['acct']): r['taint'] for r in df.collect()}


def test_cutoffs_come_from_train_only(spark):
    features = spark.createDataFrame([
        ('train', 'a', 0.1, 10.0, 0.0),
        ('train', 'b', 0.2, 20.0, 0.0),
        ('train', 'c', 0.3, 30.0, 0.0),
        ('val', 'd', 1.0, 1000.0, 100.0),
        ('val', 'e', 1.0, 1000.0, 100.0),
        ('val', 'f', 1.0, 1000.0, 100.0),
    ], FEATURES_SCHEMA)

    assert hit_cutoffs(features, 0.5) == {'fan_ratio': 0.2, 'flow_match': 20.0, 'chain_score': 0.0}


def test_seeds_need_a_score_strictly_above_a_cutoff(spark):
    features = spark.createDataFrame([
        ('train', 'pipe', 0.6, 0.0, 0.0),
        ('train', 'edge', 0.5, 0.0, 0.0),
        ('val', 'chain', 0.0, 0.0, 5.0),
    ], FEATURES_SCHEMA)
    cutoffs = {'fan_ratio': 0.5, 'flow_match': 0.0, 'chain_score': 0.0}

    assert {(r['period'], r['acct']) for r in seeds(features, cutoffs).collect()} == {
        ('train', 'pipe'), ('val', 'chain')}


def test_train_hits_per_rule_counts_train_accounts_strictly_above_each_cutoff(spark):
    features = spark.createDataFrame([
        ('train', 'pipe', 1.0, 50.0, 0.0),
        ('train', 'tie', 1.0, 10.0, 0.0),
        ('val', 'chain', 1.0, 90.0, 90.0),
    ], FEATURES_SCHEMA)
    cutoffs = {'fan_ratio': 1.0, 'flow_match': 20.0, 'chain_score': 0.0}

    assert train_hits_per_rule(features, cutoffs) == {'fan_ratio': 0, 'flow_match': 1, 'chain_score': 0}


def test_taint_spreads_one_hop_per_round_and_seeds_stay_at_one(spark):
    edges = spark.createDataFrame([
        ('train', 'S', 'X', 50.0),
        ('train', 'Y', 'X', 50.0),
        ('train', 'X', 'Z', 100.0),
        ('train', 'Z', 'S', 10.0),
    ], EDGES_SCHEMA)
    seed = spark.createDataFrame([('train', 'S')], 'period string, acct string')

    one = scores(taint(edges, seed, rounds=1))
    two = scores(taint(edges, seed, rounds=2))

    assert one == {('train', 'S'): 1.0, ('train', 'X'): pytest.approx(0.5)}
    assert two == {('train', 'S'): 1.0, ('train', 'X'): pytest.approx(0.5), ('train', 'Z'): pytest.approx(0.5)}


def test_taint_never_crosses_periods(spark):
    edges = spark.createDataFrame([('val', 'S', 'X', 100.0)], EDGES_SCHEMA)
    seed = spark.createDataFrame([('train', 'S')], 'period string, acct string')

    assert scores(taint(edges, seed, rounds=3)) == {('train', 'S'): 1.0}


def test_with_taint_gives_untainted_accounts_zero(spark):
    features = spark.createDataFrame([('train', 'S', 0.0, 0.0, 0.0), ('train', 'Q', 0.0, 0.0, 0.0)],
                                     FEATURES_SCHEMA)
    taint_scores = spark.createDataFrame([('train', 'S', 1.0)], 'period string, acct string, taint double')

    assert scores(with_taint(features, taint_scores)) == {('train', 'S'): 1.0, ('train', 'Q'): 0.0}
