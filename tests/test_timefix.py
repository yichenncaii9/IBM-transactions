import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'glue', 'lib'))
from aml_common.patterns import parse_lines  # noqa: E402
from aml_common.timefix import fix_attempt, fix_patterns, summarise  # noqa: E402


def t(h):
    return datetime(2022, 9, 1, h)


def test_in_order_chain_is_unchanged():
    rows = [(t(1), 'A', 'B'), (t(2), 'B', 'C'), (t(3), 'C', 'D')]
    assert fix_attempt(rows) == [t(1), t(2), t(3)]


def test_hop_before_its_inflow_moves_to_inflow_time():
    rows = [(t(5), 'A', 'B'), (t(2), 'B', 'C')]
    assert fix_attempt(rows) == [t(5), t(5)]


def test_fix_carries_down_the_chain():
    # B->C is fixed to 5; C->D at 4 now leaves before C's money arrives, so it moves too.
    rows = [(t(5), 'A', 'B'), (t(2), 'B', 'C'), (t(4), 'C', 'D')]
    assert fix_attempt(rows) == [t(5), t(5), t(5)]


def test_any_earlier_inflow_is_enough():
    # Gather into B: one inflow at 1 is before B->C at 3, so no fix.
    rows = [(t(1), 'A', 'B'), (t(6), 'X', 'B'), (t(3), 'B', 'C')]
    assert fix_attempt(rows) == [t(1), t(6), t(3)]


def test_cycle_origin_is_not_moved():
    # The closing transfer back to A is listed last, so A's first send has no feeder.
    rows = [(t(1), 'A', 'B'), (t(2), 'B', 'C'), (t(3), 'C', 'A')]
    assert fix_attempt(rows) == [t(1), t(2), t(3)]


def test_account_without_feeder_is_not_moved():
    rows = [(t(5), 'A', 'B'), (t(1), 'Z', 'Y')]
    assert fix_attempt(rows) == [t(5), t(1)]


SAMPLE = """BEGIN LAUNDERING ATTEMPT - SCATTER-GATHER
2022/09/01 02:39,015598,8022C7240,023375,801A1CEC0,1377.20,Euro,1377.20,Euro,ACH,1
2022/09/01 01:00,023375,801A1CEC0,011054,80120B860,1313.95,Euro,1313.95,Euro,ACH,1
END LAUNDERING ATTEMPT - SCATTER-GATHER
BEGIN LAUNDERING ATTEMPT - STACK
2022/09/01 05:14,00952,8139F54E0,0111632,8062C56E0,5331.44,US Dollar,5331.44,US Dollar,ACH,1
2022/09/03 13:09,0111632,8062C56E0,008456,81363F620,5602.59,US Dollar,5602.59,US Dollar,ACH,1
END LAUNDERING ATTEMPT - STACK"""


def test_fix_patterns_keys_and_summary():
    out = fix_patterns(parse_lines(SAMPLE.splitlines()))
    assert [r['attempt_id'] for r in out] == [1, 1, 2, 2]
    assert out[1]['from_bank'] == '023375' and out[1]['amount_paid'] == 1313.95
    assert out[1]['fixed_ts'] == datetime(2022, 9, 1, 2, 39)
    s = summarise(out)
    assert s['rows'] == 4 and s['changed'] == 1
    assert s['by_typology']['SCATTER-GATHER']['changed'] == 1
    assert s['by_typology']['STACK']['changed'] == 0
