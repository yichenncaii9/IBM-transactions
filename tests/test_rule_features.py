import os
import sys
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

pytest.importorskip("pyspark")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'glue'))
from rule_features import (  # noqa: E402
    Period, edges, features_abd, parse_periods, period_days, prepare, rule_a, rule_b, rule_d, stage,
    unpriced_currencies, usd_rates,
)

PERIODS = [Period('train', date(2022, 9, 1), date(2022, 9, 8)),
           Period('val', date(2022, 9, 11), date(2022, 9, 12))]
STARTS = {p.name: p.start for p in PERIODS}
RAW_SCHEMA = ('transaction_id string, row_num long, txn_ts timestamp, from_bank string, from_account string, '
              'to_bank string, to_account string, amount_received decimal(30,8), receiving_currency string, '
              'amount_paid decimal(30,8), payment_currency string, payment_format string, is_laundering int')
TXN_SCHEMA = 'period string, period_start date, ts timestamp, src string, dst string, usd double'
USD = 'US Dollar'


def at(stamp):
    """UTC like Glue; a naive datetime would be read in this machine's local time zone."""
    return datetime.strptime(stamp, '%m-%d %H:%M').replace(year=2022, tzinfo=timezone.utc)


def acct(name):
    return '001|' + name


def raw_txn(stamp, src, dst, paid, pay_ccy=USD, received=None, recv_ccy=USD):
    """One row in the processed-transactions schema (sample_data/processed-transactions.parquet)."""
    return ('id', 0, at(stamp), '001', src, '001', dst, Decimal(paid if received is None else received), recv_ccy,
            Decimal(paid), pay_ccy, 'ACH', 0)


def txns(spark, rows):
    """rows: (period, 'MM-DD HH:MM', src, dst, usd), already in job 1's prepared shape."""
    return spark.createDataFrame(
        [(p, STARTS[p], at(stamp), acct(src), acct(dst), float(usd)) for p, stamp, src, dst, usd in rows],
        TXN_SCHEMA)


def by_acct(df, column):
    return {(r['period'], r['acct']): r[column] for r in df.collect()}


def test_parse_periods_reads_spec():
    assert parse_periods('train=2022-09-01:2022-09-08,val=2022-09-11:2022-09-12') == PERIODS


@pytest.mark.parametrize('spec', ['train=2022-09-01:2022-09-08,val=2022-09-08:2022-09-12',
                                  'train=2022-09-08:2022-09-01'])
def test_parse_periods_rejects_overlap_and_reversed_dates(spec):
    with pytest.raises(ValueError):
        parse_periods(spec)


def test_period_days_lists_every_period_day_and_skips_gaps():
    days = period_days(PERIODS)

    assert days[0] == date(2022, 9, 1) and days[7] == date(2022, 9, 8)
    assert days[8:] == [date(2022, 9, 11), date(2022, 9, 12)]


def test_usd_rates_come_from_the_given_period_only_with_usd_on_either_side(spark):
    raw = spark.createDataFrame([
        raw_txn('09-01 10:00', 'A', 'B', 1000, received=900, recv_ccy='Euro'),
        raw_txn('09-02 10:00', 'C', 'D', 140000, pay_ccy='Yen', received=1000),
        raw_txn('09-11 10:00', 'A', 'B', 1000, received=500, recv_ccy='Euro'),
        raw_txn('09-12 10:00', 'E', 'F', 1000, received=1000, recv_ccy='Rupee'),
    ], RAW_SCHEMA)

    rates = {r['currency']: r['per_usd'] for r in usd_rates(raw, PERIODS[0]).collect()}

    assert rates == {USD: 1.0, 'Euro': pytest.approx(0.9), 'Yen': pytest.approx(140)}


def test_prepare_keeps_period_days_drops_self_transfers_and_unpriced_rows(spark):
    raw = spark.createDataFrame([
        raw_txn('09-01 10:00', 'A', 'B', 100),
        raw_txn('09-01 11:00', 'C', 'C', 50),
        raw_txn('09-09 10:00', 'A', 'B', 100),
        raw_txn('09-12 10:00', 'E', 'F', 90, pay_ccy='Euro', recv_ccy='Euro'),
        raw_txn('09-12 11:00', 'G', 'H', 5000, pay_ccy='Rupee', recv_ccy='Rupee'),
    ], RAW_SCHEMA)
    rates = spark.createDataFrame([(USD, 1.0), ('Euro', 0.9)], 'currency string, per_usd double')

    rows = {(r['period'], r['src'], r['dst']): r['usd'] for r in prepare(raw, PERIODS, rates).collect()}

    assert rows == {
        ('train', acct('A'), acct('B')): pytest.approx(100),
        ('val', acct('E'), acct('F')): pytest.approx(100),
    }


def test_rule_a_counts_distinct_counterparties(spark):
    df = rule_a(txns(spark, [
        ('train', '09-01 10:00', 'A', 'B', 10),
        ('train', '09-01 11:00', 'A', 'B', 10),
        ('train', '09-01 12:00', 'A', 'C', 10),
        ('train', '09-01 13:00', 'D', 'A', 10),
    ]))
    row = {r['acct']: r for r in df.collect()}[acct('A')]

    assert (row['n_out'], row['d_out'], row['n_in'], row['d_in']) == (3, 2, 1, 1)
    assert row['fan_ratio'] == pytest.approx(0.5)
    assert by_acct(df, 'fan_ratio')[('train', acct('B'))] == 0


def test_rule_b_matches_flows_in_either_order_within_72_hours(spark):
    df = rule_b(txns(spark, [
        ('train', '09-01 10:00', 'M', 'Y', 90),
        ('train', '09-02 10:00', 'X', 'M', 100),
        ('train', '09-01 00:00', 'X', 'N', 100),
        ('train', '09-05 00:00', 'N', 'Y', 100),
    ]))
    scores = by_acct(df, 'flow_match')

    assert scores[('train', acct('M'))] == pytest.approx(90)
    assert scores[('train', acct('N'))] == 0


def test_rule_b_never_mixes_periods(spark):
    df = rule_b(txns(spark, [
        ('train', '09-08 23:00', 'X', 'M', 100),
        ('val', '09-11 01:00', 'M', 'Y', 100),
    ]))

    assert by_acct(df, 'flow_match')[('train', acct('M'))] == 0
    assert by_acct(df, 'flow_match')[('val', acct('M'))] == 0


def test_rule_d_scores_closest_amount_pair_in_same_block(spark):
    df = rule_d(txns(spark, [
        ('train', '09-01 05:00', 'M', 'Y', 950),
        ('train', '09-01 06:00', 'M', 'Y', 10),
        ('train', '09-01 10:00', 'X', 'M', 100),
        ('train', '09-02 10:00', 'X', 'M', 1000),
        ('train', '09-01 10:00', 'X', 'T', 100),
        ('train', '09-01 11:00', 'T', 'Y', 100),
        ('train', '09-03 23:00', 'X', 'N', 100),
        ('train', '09-04 01:00', 'N', 'Y', 100),
    ]))
    scores = by_acct(df, 'chain_score')

    assert scores[('train', acct('M'))] == pytest.approx(95)
    assert scores[('train', acct('T'))] == pytest.approx(100)
    assert scores[('train', acct('N'))] is None


def test_features_abd_has_one_row_per_account_period_and_fills_zeros(spark):
    df = features_abd(txns(spark, [
        ('train', '09-01 10:00', 'X', 'M', 100),
        ('train', '09-01 11:00', 'M', 'Y', 90),
        ('val', '09-11 10:00', 'X', 'M', 100),
    ]))
    keys = [(r['period'], r['acct']) for r in df.collect()]
    chain = by_acct(df, 'chain_score')

    assert len(keys) == len(set(keys)) == 5
    assert chain[('train', acct('M'))] == pytest.approx(90)
    assert chain[('val', acct('M'))] == 0
    assert by_acct(df, 'flow_match')[('val', acct('M'))] == 0


def test_edges_sum_usd_per_sender_receiver_pair(spark):
    df = edges(txns(spark, [
        ('train', '09-01 10:00', 'A', 'B', 10),
        ('train', '09-02 10:00', 'A', 'B', 5),
        ('val', '09-11 10:00', 'A', 'B', 7),
    ]))

    assert {(r['period'], r['usd']) for r in df.collect()} == {('train', 15.0), ('val', 7.0)}


def test_unpriced_currencies_lists_currencies_without_a_rate_on_either_side(spark):
    raw = spark.createDataFrame([
        raw_txn('09-01 10:00', 'A', 'B', 100, pay_ccy='Euro', recv_ccy='Euro'),
        raw_txn('09-01 11:00', 'A', 'B', 100, pay_ccy='Yen', recv_ccy=USD),
        raw_txn('09-01 12:00', 'A', 'B', 100, pay_ccy=USD, recv_ccy='Rupee'),
    ], RAW_SCHEMA)
    rates = spark.createDataFrame([(USD, 1.0), ('Euro', 0.9)], 'currency string, per_usd double')

    assert unpriced_currencies(raw, rates) == ['Rupee', 'Yen']


def test_stage_logs_start_and_duration_but_only_start_when_it_fails(caplog):
    caplog.set_level('INFO', logger='rule_features')
    with stage('good step'):
        pass
    with pytest.raises(RuntimeError), stage('bad step'):
        raise RuntimeError('boom')

    messages = [r.getMessage() for r in caplog.records]
    assert messages[0] == 'good step: started' and messages[1].startswith('good step: done in ')
    assert messages[2:] == ['bad step: started']
