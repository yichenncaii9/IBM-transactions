-- =====================================================================
-- Q1 Part 1: Cash-out ranking (descriptive, NO labels)
-- "Where does suspicious money end up?"
--
-- Idea: start from every transaction our rules flagged (Athena rules +
-- Neo4j rules), follow the money forward up to 2 more hops in time
-- order (each hop within 3 days), then rank the accounts it reaches by
-- how much traced money flows in and how little flows back out
-- ("sinks"), or leaves as Cash/Cheque.
--
-- Detection steps read ONLY v_detect_full (no is_laundering column).
-- Labels are used only in the final evaluation query (step 5).
--
-- Run each statement separately in Athena, workgroup is459.
-- Each one scans the transactions once, so it should stay under the
-- 2 GB per-query limit. If one gets cancelled for the limit, send me
-- the error.
-- =====================================================================


-- ---------------------------------------------------------------------
-- Step 1: hop 0 = accounts that RECEIVED a flagged transaction
-- ---------------------------------------------------------------------
CREATE TABLE is459_aml.q1_hop0
WITH (format = 'PARQUET', external_location = 's3://is459-g2t8-aml-897729121624/results/q1/hop0/') AS
WITH hits AS (
  SELECT transaction_id FROM is459_aml.rule_hits_full
  UNION
  SELECT transaction_id FROM is459_aml.rule_hits_neo4j_full
)
SELECT t.to_bank || '|' || t.to_account AS acct,
       min(t.txn_ts)                    AS first_ts,
       count(*)                         AS in_txns
FROM is459_aml.v_detect_full t
JOIN hits h ON t.transaction_id = h.transaction_id
GROUP BY 1;


-- ---------------------------------------------------------------------
-- Step 2: hop 1 = where hop-0 accounts sent money within 3 days
-- ---------------------------------------------------------------------
CREATE TABLE is459_aml.q1_hop1
WITH (format = 'PARQUET', external_location = 's3://is459-g2t8-aml-897729121624/results/q1/hop1/') AS
SELECT t.to_bank || '|' || t.to_account AS acct,
       min(t.txn_ts)                    AS first_ts,
       count(*)                         AS in_txns
FROM is459_aml.v_detect_full t
JOIN is459_aml.q1_hop0 h
  ON t.from_bank || '|' || t.from_account = h.acct
WHERE t.txn_ts >  h.first_ts
  AND t.txn_ts <= h.first_ts + INTERVAL '3' DAY
  AND t.to_bank || '|' || t.to_account <> h.acct      -- skip self-transfers
GROUP BY 1;


-- ---------------------------------------------------------------------
-- Step 3: hop 2 = one more hop from hop-1 accounts, same rules
-- ---------------------------------------------------------------------
CREATE TABLE is459_aml.q1_hop2
WITH (format = 'PARQUET', external_location = 's3://is459-g2t8-aml-897729121624/results/q1/hop2/') AS
SELECT t.to_bank || '|' || t.to_account AS acct,
       min(t.txn_ts)                    AS first_ts,
       count(*)                         AS in_txns
FROM is459_aml.v_detect_full t
JOIN is459_aml.q1_hop1 h
  ON t.from_bank || '|' || t.from_account = h.acct
WHERE t.txn_ts >  h.first_ts
  AND t.txn_ts <= h.first_ts + INTERVAL '3' DAY
  AND t.to_bank || '|' || t.to_account <> h.acct
GROUP BY 1;


-- ---------------------------------------------------------------------
-- Step 4: the ranking table
--   traced_in  = traced transactions arriving (all hops)
--   min_hop    = how close the account is to the flagged activity
--   out_txns   = everything the account sends out, over the full data
--   cash_out   = outgoing Cash / Cheque transactions (money leaving
--                the banking system)
--   sink_score = traced_in / (out_txns + 1): high = money arrives and
--                stays, or leaves as cash -> likely end point
-- (Counts, not amounts, because amounts are in different currencies.)
-- ---------------------------------------------------------------------
CREATE TABLE is459_aml.q1_cashout_rank
WITH (format = 'PARQUET', external_location = 's3://is459-g2t8-aml-897729121624/results/q1/cashout_rank/') AS
WITH reached AS (
  SELECT acct, 0 AS hop, in_txns FROM is459_aml.q1_hop0
  UNION ALL
  SELECT acct, 1 AS hop, in_txns FROM is459_aml.q1_hop1
  UNION ALL
  SELECT acct, 2 AS hop, in_txns FROM is459_aml.q1_hop2
),
r AS (
  SELECT acct, min(hop) AS min_hop, sum(in_txns) AS traced_in
  FROM reached GROUP BY acct
),
o AS (
  SELECT from_bank || '|' || from_account AS acct,
         count(*) AS out_txns,
         sum(CASE WHEN payment_format IN ('Cash', 'Cheque') THEN 1 ELSE 0 END) AS cash_out
  FROM is459_aml.v_detect_full
  GROUP BY 1
)
SELECT r.acct, r.min_hop, r.traced_in,
       coalesce(o.out_txns, 0) AS out_txns,
       coalesce(o.cash_out, 0) AS cash_out,
       CAST(r.traced_in AS double) / (coalesce(o.out_txns, 0) + 1) AS sink_score
FROM r LEFT JOIN o ON r.acct = o.acct;


-- Top 100 likely cash-out accounts (needs at least 3 traced inflows,
-- so one-off receivers don't dominate)
SELECT acct, min_hop, traced_in, out_txns, cash_out,
       round(sink_score, 2) AS sink_score
FROM is459_aml.q1_cashout_rank
WHERE traced_in >= 3
ORDER BY sink_score DESC, traced_in DESC
LIMIT 100;

-- Hop-count summary: how far from flagged activity do end points sit?
SELECT min_hop, count(*) AS accounts, sum(traced_in) AS traced_in
FROM is459_aml.q1_cashout_rank
GROUP BY 1 ORDER BY 1;


-- ---------------------------------------------------------------------
-- Step 5: EVALUATION (labels used only here)
-- Precision@100: of our top-100 end points, how many really received
-- laundering money? Compare with the base rate across all accounts.
-- ---------------------------------------------------------------------
WITH top100 AS (
  SELECT acct
  FROM is459_aml.q1_cashout_rank
  WHERE traced_in >= 3
  ORDER BY sink_score DESC, traced_in DESC
  LIMIT 100
),
launder_receivers AS (
  SELECT DISTINCT to_bank || '|' || to_account AS acct
  FROM is459_aml.transactions
  WHERE is_laundering = 1
),
all_receivers AS (
  SELECT count(DISTINCT to_bank || '|' || to_account) AS n
  FROM is459_aml.transactions
)
SELECT
  (SELECT count(*) FROM top100 t JOIN launder_receivers l ON t.acct = l.acct) AS top100_hits,
  round((SELECT count(*) FROM top100 t JOIN launder_receivers l ON t.acct = l.acct) / 100.0 * 100, 1)
                                                                      AS precision_at_100_pct,
  round(100.0 * (SELECT count(*) FROM launder_receivers) / (SELECT n FROM all_receivers), 3)
                                                                      AS base_rate_pct;
