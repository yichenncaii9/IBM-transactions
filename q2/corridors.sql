-- Recovered from the project's Athena query history. Run in workgroup is459.
-- Prerequisites: is459_aml.transactions, bank_country, and eval_predictions_full.
-- Athena CTAS requires the S3 external_location to be empty before a rerun.

CREATE TABLE is459_aml.bank_country
WITH (format = 'PARQUET', external_location = 's3://is459-g2t8-aml-897729121624/results/q2/bank_country/') AS
WITH b AS (
  SELECT try_cast(bank_id AS bigint) AS bank_id, min(bank_name) AS bank_name,
         min(CASE
  WHEN regexp_like(bank_name, '^(Crytpo|Crypto) Bank') THEN 'Crypto (no country)'
  WHEN regexp_like(bank_name, '^.+ Bank #[0-9]+$') THEN regexp_extract(bank_name, '^(.+) Bank #[0-9]+$', 1)
  ELSE 'United States' END) AS bank_country, count(*) AS accounts
  FROM accounts_raw GROUP BY 1)
SELECT b.bank_id, b.bank_name, b.bank_country, b.accounts,
       CASE WHEN b.bank_country = 'Crypto (no country)' THEN 'crypto group (no country)'
            WHEN b.bank_country = 'United States' AND NOT regexp_like(b.bank_name, '^.+ Bank #[0-9]+$')
                 THEN 'assumed US (city bank name)'
            ELSE 'country in bank name' END AS country_source,
       s.basel_country,
       try_cast(s.basel_score AS double) AS basel_score,
       try_cast(s.basel_source_year AS integer) AS basel_source_year,
       (s.is_proxy_year = 'true') AS is_proxy_year
FROM b LEFT JOIN basel_scores s ON s.bank_country = b.bank_country;

-- This rule-hit union supplies alert counts in the corridor report.
CREATE TABLE is459_aml.eval_predictions_full
WITH (format = 'PARQUET', external_location = 's3://is459-g2t8-aml-897729121624/results/eval/predictions_full/') AS
SELECT transaction_id, array_join(array_sort(array_agg(DISTINCT rule_name)), '+') AS rules
FROM (SELECT transaction_id, rule_name FROM rule_hits_full
      UNION ALL SELECT transaction_id, rule_name FROM rule_hits_neo4j_full)
GROUP BY transaction_id;

CREATE TABLE is459_aml.q2_corridors
WITH (format = 'PARQUET', external_location = 's3://is459-g2t8-aml-897729121624/results/q2/corridors/') AS
SELECT f.bank_country AS from_country, t.bank_country AS to_country,
       count(*) AS txns,
       sum(x.is_laundering) AS laundering,
       count(p.transaction_id) AS flagged,
       count_if(p.transaction_id IS NOT NULL AND x.is_laundering = 1) AS caught,
       min(f.basel_score) AS from_basel_score, min(f.basel_source_year) AS from_basel_year,
       min(t.basel_score) AS to_basel_score,   min(t.basel_source_year) AS to_basel_year
FROM transactions x
JOIN bank_country f ON f.bank_id = try_cast(x.from_bank AS bigint)
JOIN bank_country t ON t.bank_id = try_cast(x.to_bank AS bigint)
LEFT JOIN eval_predictions_full p ON p.transaction_id = x.transaction_id
GROUP BY 1, 2;

CREATE TABLE is459_aml.q2_summary
WITH (format = 'PARQUET', external_location = 's3://is459-g2t8-aml-897729121624/results/q2/summary/') AS
WITH c AS (
  SELECT *,
         CASE WHEN from_country = 'Crypto (no country)' OR to_country = 'Crypto (no country)' THEN 'involves crypto'
              WHEN from_country = to_country THEN 'domestic'
              ELSE 'cross-border' END AS scope
  FROM q2_corridors)
SELECT 'scope' AS dimension, scope AS grp, sum(txns) AS txns, sum(laundering) AS laundering,
       sum(flagged) AS flagged, sum(caught) AS caught FROM c GROUP BY 1, 2
UNION ALL
SELECT 'destination Basel band', CASE WHEN to_basel_score IS NULL THEN 'no score (crypto)'
                            WHEN to_basel_score < 4.0 THEN '1 low (<4.0)'
                            WHEN to_basel_score < 5.0 THEN '2 medium (4.0-4.99)'
                            ELSE '3 high (>=5.0)' END, sum(txns), sum(laundering), sum(flagged), sum(caught)
FROM c GROUP BY 1, 2
UNION ALL
SELECT 'origin Basel band', CASE WHEN from_basel_score IS NULL THEN 'no score (crypto)'
                            WHEN from_basel_score < 4.0 THEN '1 low (<4.0)'
                            WHEN from_basel_score < 5.0 THEN '2 medium (4.0-4.99)'
                            ELSE '3 high (>=5.0)' END, sum(txns), sum(laundering), sum(flagged), sum(caught)
FROM c GROUP BY 1, 2;
