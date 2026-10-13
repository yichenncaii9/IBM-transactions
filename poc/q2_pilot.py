"""Q2 pilot: corridor risk, the currency-conversion blind spot, and the Basel AML Index test.

Usage: python poc/q2_pilot.py [db_path]   (run build_db.py first)
All rates exclude the Sep 17-28 tail, which is ~58% laundering.
"""
import os
import sys

import duckdb
from scipy.stats import spearmanr

DB = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), 'aml.duckdb')
con = duckdb.connect(DB)
con.execute("SET threads=8")


def show(title, sql):
    print(f"\n== {title}")
    print(con.execute(sql).df().to_string(index=False))


show("Cross-border vs domestic", """
select ds, cross_border, count(*) n, sum(is_laund) k, round(sum(is_laund)*1e4/count(*),2) per_10k
from enr where not tail group by all order by ds, cross_border""")

show("Currency conversion x cross-border (2x2)", """
select ds, cross_ccy, cross_border, count(*) n, sum(is_laund) k, round(sum(is_laund)*1e4/count(*),2) per_10k
from enr where not tail group by all order by all""")

show("'Flag every currency conversion' rule", """
select ds, sum(cross_ccy::int) flagged, sum((cross_ccy and is_laund=1)::int) caught, sum(is_laund) positives
from enr where not tail group by ds order by ds""")

show("What conversions are (all rows)", """
select ds, count(*) n, round(avg((from_acct=to_acct and from_bank=to_bank)::int),3) self_transfer,
       round(avg((from_bank=to_bank)::int),3) same_bank, round(avg((fmt='ACH')::int),3) ach
from enr where cross_ccy group by ds order by ds""")

show("Laundering by payment format", """
select ds, fmt, count(*) n, sum(is_laund) k, round(sum(is_laund)*1e4/count(*),2) per_10k
from enr where not tail group by all order by ds, per_10k desc""")

# Corridor lift with a Wilson 95% lower bound so small corridors don't dominate.
con.execute("""CREATE OR REPLACE TEMP TABLE corr AS
with base as (select ds, sum(is_laund)*1.0/count(*) p0 from enr where not tail group by ds),
c as (select ds, from_country, to_country, count(*) n, sum(is_laund) k from enr where not tail group by all)
select c.*, k*1.0/n rate, (k*1.0/n)/p0 lift, p0,
  ((k*1.0/n) + 1.96^2/(2*n) - 1.96*sqrt((k*1.0/n)*(1-k*1.0/n)/n + 1.96^2/(4*n*n))) / (1 + 1.96^2/n) wilson_lo
from c join base using (ds)""")
show("Corridors with n>=500 and how many are clearly above base rate", """
select ds, sum((n>=500)::int) corridors_n500, sum((n>=500 and wilson_lo>p0)::int) above_base
from corr group by ds order by ds""")
for ds in ['HI', 'LI']:
    show(f"Top corridors {ds} (n>=500, ranked by Wilson lower bound)", f"""
select from_country, to_country, n, k, round(rate*100,2) pct, round(lift,1) lift
from corr where ds='{ds}' and n>=500 order by wilson_lo desc limit 10""")
pairs = con.execute("""select h.lift, l.lift from corr h join corr l
  on h.from_country=l.from_country and h.to_country=l.to_country and h.ds='HI' and l.ds='LI'
  where h.n>=500 and l.n>=500""").fetchall()
rho, p = spearmanr([a for a, _ in pairs], [b for _, b in pairs])
print(f"\nCorridor lift HI vs LI: {len(pairs)} corridors, spearman={rho:.2f} p={p:.1e}")

print("\n== Basel AML Index vs laundering rate (per country)")
for side in ['to', 'from']:
    for ds in ['HI', 'LI']:
        df = con.execute(f"""select any_value({side}_basel) b, sum(is_laund)*1e4/count(*) r
            from enr where ds='{ds}' and not tail and {side}_basel is not null group by {side}_country""").df()
        rho, p = spearmanr(df.b, df.r)
        print(f"{side}-country {ds}: {len(df)} countries, spearman={rho:.3f} p={p:.3f}")
show("Basel terciles (receiving country)", """
with x as (select ds, is_laund, to_basel, ntile(3) over (partition by ds order by to_basel) t
           from enr where not tail and to_basel is not null)
select ds, t tercile, min(to_basel) lo, max(to_basel) hi, count(*) n, round(sum(is_laund)*1e4/count(*),2) per_10k
from x group by all order by ds, t""")
show("Rows without a Basel score (sending side)", """
select ds, from_country, count(*) n from enr where from_basel is null group by all order by ds, n desc""")
