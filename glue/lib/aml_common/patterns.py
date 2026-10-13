"""Parser for IBM AML *_Patterns.txt (ground-truth laundering attempts)."""
import re

HEADER = re.compile(r'BEGIN LAUNDERING ATTEMPT - ([A-Z-]+)(?::\s*Max (\d+)[- ](degree|hops))?')
COLUMNS = ['attempt_id', 'typology', 'max_param', 'ts', 'from_bank', 'from_acct', 'to_bank',
           'to_acct', 'amt_recv', 'recv_ccy', 'amt_paid', 'pay_ccy', 'fmt']


def parse_lines(lines):
    """Yield one tuple per transaction (see COLUMNS); attempt_id starts at 1."""
    attempt_id, typology, param = 0, None, None
    for line in lines:
        line = line.strip()
        if not line:
            continue
        m = HEADER.match(line)
        if m:
            attempt_id += 1
            typology, param = m.group(1), m.group(2)
            continue
        if line.startswith('END LAUNDERING'):
            typology = None
            continue
        f = line.split(',')
        yield (attempt_id, typology, int(param) if param else None, f[0], f[1], f[2], f[3], f[4],
               float(f[5]), f[6], float(f[7]), f[8], f[9])


def parse_file(path):
    with open(path) as fh:
        return list(parse_lines(fh))
