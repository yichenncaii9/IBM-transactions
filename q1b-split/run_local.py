"""Local (DuckDB) version of split_queries.sql queries 1-3. No AWS needed.
Run: python run_local.py <HI-Medium_Trans.csv> <HI-Medium_Patterns.txt> <outdir>
Patterns.txt rows are the transactions themselves, so queries 2-3 need no join."""
import sys, re, duckdb, pandas as pd
trans, pats, out = sys.argv[1:4]
con = duckdb.connect()

# Query 1: per-day rows and positives
con.execute(f"""COPY (
  SELECT CAST(strptime(Timestamp,'%Y/%m/%d %H:%M') AS DATE) AS day,
         count(*) AS n_rows, sum("Is Laundering") AS n_pos
  FROM read_csv('{trans}', header=true, all_varchar=false, auto_detect=true,
                columns={{'Timestamp':'VARCHAR','fb':'VARCHAR','fa':'VARCHAR','tb':'VARCHAR','ta':'VARCHAR',
                         'ar':'DOUBLE','rc':'VARCHAR','ap':'DOUBLE','pc':'VARCHAR','pf':'VARCHAR','Is Laundering':'INT'}},
                skip=1)
  GROUP BY 1 ORDER BY 1) TO '{out}/daily_counts.csv' (HEADER, DELIMITER ',')""")

# Parse patterns into one row per txn
rows, aid, atype = [], 0, None
for line in open(pats):
    line = line.strip()
    m = re.match(r"BEGIN LAUNDERING ATTEMPT - ([A-Z\-_]+)", line)
    if m: aid += 1; atype = m.group(1); continue
    if not line or line.startswith("END"): continue
    f = line.split(",")
    rows.append((aid, atype, len(rows), f[0], f[1]+"|"+f[2], f[3]+"|"+f[4]))
p = pd.DataFrame(rows, columns=["attempt_id","attempt_type","tid","ts","src","dst"])
p["ts"] = pd.to_datetime(p.ts, format="%Y/%m/%d %H:%M")
p.to_csv(f"{out}/pattern_txns.csv", index=False)
con.register("p", p)

# Query 2: span of attempts
q2 = """WITH a AS (SELECT attempt_id, attempt_type,
           date_diff('minute', min(ts), max(ts))/1440.0 AS span_days FROM p GROUP BY 1,2)
 SELECT attempt_type, count(*) attempts, round(quantile_cont(span_days,0.5),2) p50_days,
        round(quantile_cont(span_days,0.9),2) p90_days, round(quantile_cont(span_days,0.95),2) p95_days,
        round(max(span_days),2) max_days FROM a GROUP BY ROLLUP(attempt_type) ORDER BY attempt_type NULLS LAST"""
con.execute(f"COPY ({q2}) TO '{out}/q2_attempt_span.csv' (HEADER)")
print(con.execute(q2).df().to_string(index=False))

# Query 3: out-of-order hops
q3 = """WITH hop AS (
  SELECT o.attempt_type, o.tid, max(CASE WHEN i.ts <= o.ts THEN 1 ELSE 0 END) has_earlier_inflow
  FROM p o JOIN p i ON i.attempt_id=o.attempt_id AND i.dst=o.src AND i.tid<>o.tid GROUP BY 1,2)
 SELECT attempt_type, count(*) relay_hops, round(100.0*sum(1-has_earlier_inflow)/count(*),1) out_of_order_pct
 FROM hop GROUP BY ROLLUP(attempt_type) ORDER BY attempt_type NULLS LAST"""
con.execute(f"COPY ({q3}) TO '{out}/q3_out_of_order.csv' (HEADER)")
print(con.execute(q3).df().to_string(index=False))
