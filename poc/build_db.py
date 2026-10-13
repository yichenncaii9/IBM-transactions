"""Build the local pilot DuckDB from the full HI/LI Medium files.

Usage: python poc/build_db.py <data_dir> [db_path]
<data_dir> must contain {HI,LI}-Medium_Trans.csv, {HI,LI}-Medium_accounts.csv and
{HI,LI}-Medium_Patterns.txt. Takes ~4 minutes and ~14 GB RAM on a laptop.
"""
import os
import sys

import duckdb
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'glue', 'lib'))
from aml_common.patterns import COLUMNS, parse_file  # noqa: E402

DATA = sys.argv[1]
DB = sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(__file__), 'aml.duckdb')
HERE = os.path.dirname(os.path.abspath(__file__))
DATASETS = ['HI', 'LI']

con = duckdb.connect(DB)
con.execute("SET threads=8; SET memory_limit='14GB'")

# Explicit schema: the raw header repeats "Account" for sender and receiver.
cols = ("{'ts':'VARCHAR','from_bank':'VARCHAR','from_acct':'VARCHAR','to_bank':'VARCHAR',"
        "'to_acct':'VARCHAR','amt_recv':'DOUBLE','recv_ccy':'VARCHAR','amt_paid':'DOUBLE',"
        "'pay_ccy':'VARCHAR','fmt':'VARCHAR','is_laund':'INTEGER'}")
con.execute("CREATE OR REPLACE TABLE trans AS " + " UNION ALL ".join(
    f"""select '{ds}' ds, row_number() over () rid, strptime(ts,'%Y/%m/%d %H:%M') ts,
          from_bank, cast(from_bank as bigint) from_bank_i, from_acct,
          to_bank, cast(to_bank as bigint) to_bank_i, to_acct,
          amt_recv, recv_ccy, amt_paid, pay_ccy, fmt, is_laund
        from read_csv('{DATA}/{ds}-Medium_Trans.csv', header=true, columns={cols})"""
    for ds in DATASETS))

# Accounts: country comes from the synthetic bank name ("China Bank #561");
# US-style names ("Bank of Dallas") have no prefix and map to United States.
con.execute("CREATE OR REPLACE TABLE accts AS " + " UNION ALL ".join(
    f"""select '{ds}' ds, "Bank Name" bank_name, cast("Bank ID" as bigint) bank_i,
          "Account Number" acct, "Entity ID" entity_id, "Entity Name" entity_name,
          case when regexp_matches("Bank Name", '^.+? Bank #[0-9]+$')
               then regexp_extract("Bank Name", '^(.+?) Bank #[0-9]+$', 1)
               else 'United States' end country
        from read_csv('{DATA}/{ds}-Medium_accounts.csv', all_varchar=true)"""
    for ds in DATASETS))

con.execute(f"CREATE OR REPLACE TABLE basel AS select * from read_csv('{HERE}/basel_2025.csv')")

# Bank IDs are zero-padded in Trans but not in accounts, so join on the integer form.
con.execute("""CREATE OR REPLACE TABLE enr AS
select t.*, fa.entity_id from_entity, ta.entity_id to_entity,
       fa.country from_country, ta.country to_country,
       fb.basel_score from_basel, tb.basel_score to_basel,
       (fa.country <> ta.country) cross_border, (t.pay_ccy <> t.recv_ccy) cross_ccy,
       (t.ts >= TIMESTAMP '2022-09-17') tail
from trans t
left join accts fa on fa.ds=t.ds and fa.bank_i=t.from_bank_i and fa.acct=t.from_acct
left join accts ta on ta.ds=t.ds and ta.bank_i=t.to_bank_i and ta.acct=t.to_acct
left join basel fb on fb.country=fa.country
left join basel tb on tb.country=ta.country""")

# The generator uses fixed FX rates; recover them from USD-paid conversions.
con.execute("""CREATE OR REPLACE TABLE fx AS
select recv_ccy ccy, median(amt_recv/amt_paid) per_usd from trans
where pay_ccy='US Dollar' and recv_ccy<>'US Dollar' and amt_paid>100 group by 1
union all select 'US Dollar', 1.0""")
con.execute("""CREATE OR REPLACE TABLE lnd AS
select e.*, e.amt_paid/fx.per_usd usd from enr e join fx on fx.ccy=e.pay_ccy where is_laund=1""")

# Patterns: match each ground-truth row back to its transaction by natural key.
frames = []
for ds in DATASETS:
    df = pd.DataFrame(parse_file(f'{DATA}/{ds}-Medium_Patterns.txt'), columns=COLUMNS)
    df['ds'] = ds
    frames.append(df)
con.register('pat_df', pd.concat(frames))
con.execute("CREATE OR REPLACE TABLE pat AS select *, strptime(ts,'%Y/%m/%d %H:%M') tts from pat_df")
con.execute("""CREATE OR REPLACE TABLE patm AS
select p.ds, p.attempt_id, p.typology, p.max_param, min(l.rid) rid, count(l.rid) nmatch
from pat p left join lnd l
  on l.ds=p.ds and l.ts=p.tts and l.from_bank=p.from_bank and l.from_acct=p.from_acct
 and l.to_bank=p.to_bank and l.to_acct=p.to_acct and l.amt_paid=p.amt_paid
 and l.pay_ccy=p.pay_ccy and l.fmt=p.fmt
group by p.ds, p.attempt_id, p.typology, p.max_param, p.ts, p.from_bank, p.from_acct,
         p.to_bank, p.to_acct, p.amt_recv, p.amt_paid, p.pay_ccy, p.fmt""")
con.execute("""CREATE OR REPLACE TABLE lndp AS
select l.*, m.attempt_id, m.typology from lnd l
left join (select distinct ds, rid, attempt_id, typology from patm where rid is not null) m
  on m.ds=l.ds and m.rid=l.rid""")

print("transactions:", con.execute("select ds, count(*), sum(is_laund) from trans group by ds order by ds").fetchall())
print("unmatched accounts (from, to):", con.execute(
    "select ds, sum((from_entity is null)::int), sum((to_entity is null)::int) from enr group by ds order by ds").fetchall())
print("patterns matched (rows, matched, multi):", con.execute(
    "select ds, count(*), sum((nmatch>=1)::int), sum((nmatch>1)::int) from patm group by ds order by ds").fetchall())
