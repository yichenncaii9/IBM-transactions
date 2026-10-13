import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'glue', 'lib'))
from aml_common.patterns import parse_lines  # noqa: E402

SAMPLE = """BEGIN LAUNDERING ATTEMPT - STACK
2022/09/01 05:14,00952,8139F54E0,0111632,8062C56E0,5331.44,US Dollar,5331.44,US Dollar,ACH,1
2022/09/03 13:09,0111632,8062C56E0,008456,81363F620,5602.59,US Dollar,5602.59,US Dollar,ACH,1
END LAUNDERING ATTEMPT - STACK

BEGIN LAUNDERING ATTEMPT - CYCLE:  Max 3 hops
2022/09/01 00:01,001,A1,002,B1,10.00,Euro,10.00,Euro,ACH,1
END LAUNDERING ATTEMPT - CYCLE
BEGIN LAUNDERING ATTEMPT - FAN-OUT:  Max 2-degree Fan-Out
2022/09/02 00:01,001,A1,002,B1,10.00,Euro,10.00,Euro,ACH,1
END LAUNDERING ATTEMPT - FAN-OUT"""


def test_parses_attempts_types_and_params():
    rows = list(parse_lines(SAMPLE.splitlines()))
    assert [r[0] for r in rows] == [1, 1, 2, 3]
    assert [r[1] for r in rows] == ['STACK', 'STACK', 'CYCLE', 'FAN-OUT']
    assert [r[2] for r in rows] == [None, None, 3, 2]


def test_keeps_zero_padded_bank_ids_as_strings():
    row = next(parse_lines(SAMPLE.splitlines()))
    assert row[4] == '00952' and row[5] == '8139F54E0' and row[10] == 5331.44
