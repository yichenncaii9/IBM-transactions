-- =====================================================================
-- Q1b: time-based split for the GBM (Athena, workgroup is459)
-- Run each statement separately. Labels are used here only to SIZE and
-- EVALUATE the split, never as model features.
--
-- ASSUMED names (rename to yours):
--   is459_aml.transactions    : transaction_id, txn_ts, from_bank, from_account,
--                               to_bank, to_account, is_laundering
--   is459_aml.pattern_txns    : attempt_id, attempt_type, transaction_id
--                               (Patterns.txt parsed, one row per txn)
--   is459_aml.gbm_candidates  : transaction_id of the ~700k filtered rows
-- =====================================================================


-- 1. Per-day rows and positives -> save as daily_counts.csv for choose_cuts.py
--    Run once on the full data, once on the candidate set (swap the comment).
SELECT date(t.txn_ts)          AS day,
       count(*)                AS n_rows,
       sum(t.is_laundering)    AS n_pos
FROM is459_aml.transactions t
-- JOIN is459_aml.gbm_candidates c ON c.transaction_id = t.transaction_id
GROUP BY 1
ORDER BY 1;


-- 2. How long attempts last -> choose the gap G.
--    Take G = ceil(p90 span in days); p95 if you can afford the lost days.
WITH a AS (
  SELECT p.attempt_id, p.attempt_type,
         date_diff('hour', min(t.txn_ts), max(t.txn_ts)) / 24.0 AS span_days
  FROM is459_aml.pattern_txns p
  JOIN is459_aml.transactions t ON t.transaction_id = p.transaction_id
  GROUP BY 1, 2
)
SELECT attempt_type,
       count(*)                              AS attempts,
       round(approx_percentile(span_days, 0.5), 2)  AS p50_days,
       round(approx_percentile(span_days, 0.9), 2)  AS p90_days,
       round(approx_percentile(span_days, 0.95), 2) AS p95_days,
       round(max(span_days), 2)              AS max_days
FROM a
GROUP BY ROLLUP (attempt_type)
ORDER BY attempt_type NULLS LAST;


-- 3. Out-of-order hops: for each laundering txn whose sender also RECEIVED
--    money inside the same attempt, did any of that money arrive first?
--    out_of_order_pct = share of such hops where it did not.
WITH x AS (
  SELECT p.attempt_id, p.attempt_type, t.transaction_id, t.txn_ts,
         t.from_bank || '|' || t.from_account AS src,
         t.to_bank   || '|' || t.to_account   AS dst
  FROM is459_aml.pattern_txns p
  JOIN is459_aml.transactions t ON t.transaction_id = p.transaction_id
),
hop AS (
  SELECT o.attempt_type, o.transaction_id,
         max(CASE WHEN i.txn_ts <= o.txn_ts THEN 1 ELSE 0 END) AS has_earlier_inflow
  FROM x o
  JOIN x i ON i.attempt_id = o.attempt_id AND i.dst = o.src
          AND i.transaction_id <> o.transaction_id
  GROUP BY 1, 2
)
SELECT attempt_type,
       count(*) AS relay_hops,
       round(100.0 * sum(1 - has_earlier_inflow) / count(*), 1) AS out_of_order_pct
FROM hop
GROUP BY ROLLUP (attempt_type)
ORDER BY attempt_type NULLS LAST;


-- 4. Split table. Fill the dates from choose_cuts.py output.
--    split = train | gap1 | val | gap2 | test | tail
--    attempt_start / is_new_attempt feed the two-recall report.
CREATE TABLE is459_aml.gbm_split
WITH (format = 'PARQUET',
      external_location = 's3://is459-g2t8-aml-897729121624/results/q1b/split/') AS
WITH att AS (
  SELECT p.transaction_id, p.attempt_id,
         min(t.txn_ts) OVER (PARTITION BY p.attempt_id) AS attempt_start
  FROM is459_aml.pattern_txns p
  JOIN is459_aml.transactions t ON t.transaction_id = p.transaction_id
)
SELECT t.transaction_id,
       CASE
         WHEN date(t.txn_ts) <  DATE '2022-09-08' THEN 'train'   -- TRAIN_END + 1
         WHEN date(t.txn_ts) <  DATE '2022-09-10' THEN 'gap1'    -- VAL_START
         WHEN date(t.txn_ts) <  DATE '2022-09-12' THEN 'val'     -- VAL_END + 1
         WHEN date(t.txn_ts) <  DATE '2022-09-14' THEN 'gap2'    -- TEST_START
         WHEN date(t.txn_ts) <= DATE '2022-09-16' THEN 'test'    -- TEST_END
         ELSE 'tail'
       END AS split,
       a.attempt_id,
       a.attempt_start,
       -- honest-recall flag: attempt began after training data ended
       CASE WHEN a.attempt_start >= TIMESTAMP '2022-09-08 00:00:00' THEN 1 ELSE 0 END
         AS is_new_attempt
FROM is459_aml.transactions t
LEFT JOIN att a ON a.transaction_id = t.transaction_id;


-- 5. Check the split: rows, positives, prevalence per part.
SELECT s.split, count(*) AS n_rows, sum(t.is_laundering) AS n_pos,
       round(100.0 * avg(t.is_laundering), 3) AS prev_pct,
       sum(CASE WHEN t.is_laundering = 1 AND s.attempt_id IS NULL THEN 1 ELSE 0 END)
         AS pos_without_attempt
FROM is459_aml.gbm_split s
JOIN is459_aml.transactions t ON t.transaction_id = s.transaction_id
GROUP BY 1
ORDER BY min(t.txn_ts);
