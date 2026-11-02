# Q1b split results (run locally with DuckDB, run_local.py; HI-Medium, 31.9M rows, 2022-09-01..09-28)

Recommended (gap 2, alpha 0.5, last-day 2022-09-16, min-pos 300):
- train 2022-09-01 .. 2022-09-08  rows=16,866,121 (68.6%) pos=13,514 (60.5%) prev=0.080%
- gap   2022-09-09 .. 2022-09-10
- val   2022-09-11 .. 2022-09-12  rows= 2,760,383 (11.2%) pos= 4,145 (18.6%) prev=0.150%
- gap   2022-09-13 .. 2022-09-14
- test  2022-09-15 .. 2022-09-16  rows= 4,952,285 (20.1%) pos= 4,669 (20.9%) prev=0.094%
- tail  2022-09-17 .. 2022-09-28 dropped (58% laundering, generator artifact)

Alternative gap 1: train 09-01..09-09, val 09-11..09-13, test 09-15..09-16 (score 0.196, better shares).
gap 3 leaves test = 09-16 only; gap 7 (ceil p90 span) is infeasible: no cut meets min-pos.

Q2 attempt span (days): overall p50 4.60, p90 6.02, p95 9.90, max 12.69. GATHER-SCATTER longest (p90 11.5).
Q3 out-of-order relay hops: overall 9.9%; CYCLE 20.6%, SCATTER-GATHER 9.7%, GATHER-SCATTER 7.6%, STACK 5.8%, RANDOM 2.7%.
Caveat: attempts last ~6 days but gap is 2 days, so attempts straddle cuts; use is_new_attempt flag (attempt_start >= val/test start).
Note: queries 2-3 use Patterns.txt rows directly (no transaction_id join needed locally).
