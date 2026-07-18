-- ============================================================================
-- FleetPulse on Snowflake — the analytical ("gold") layer
-- Run in a Workspace SQL file, section by section (select lines -> Cmd+Enter).
--
-- WHAT HAPPENED ON LOAD (and why section 0.5 exists):
-- The "Upload Local Files" wizard loaded each Parquet file as ONE semi-structured
-- VARIANT column (VARIANT_COL) instead of named columns. That's a legitimate
-- Snowflake pattern — VARIANT is how it treats JSON/semi-structured data as
-- first-class. Rather than re-uploading, we FLATTEN via views: extract each
-- field with path syntax (VARIANT_COL:"field") and cast it (::TYPE).
-- Interview note: dates inside the variant are epoch MICROSECONDS, so we use
-- TO_TIMESTAMP(value, 6). Knowing this dance is a real Parquet/Snowflake skill.
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 0. One-time setup (already run): database + schema + warehouse
-- ---------------------------------------------------------------------------
CREATE DATABASE IF NOT EXISTS FLEETPULSE;
CREATE SCHEMA IF NOT EXISTS FLEETPULSE.ANALYTICS;
USE SCHEMA FLEETPULSE.ANALYTICS;
USE WAREHOUSE COMPUTE_WH;

-- ---------------------------------------------------------------------------
-- 0.5 Flatten the VARIANT tables into typed views (run once)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW V_SCORES AS
SELECT
  VARIANT_COL:"machine_id"::STRING                       AS machine_id,
  TO_TIMESTAMP(VARIANT_COL:"date"::NUMBER, 6)::DATE      AS score_date,
  VARIANT_COL:"split"::STRING                            AS split,
  VARIANT_COL:"label"::NUMBER                            AS label,
  VARIANT_COL:"days_to_failure"::FLOAT                   AS days_to_failure,
  VARIANT_COL:"risk_raw"::FLOAT                          AS risk_raw,
  VARIANT_COL:"risk_calibrated"::FLOAT                   AS risk_calibrated
FROM SCORES;

CREATE OR REPLACE VIEW V_FLEET_MASTER AS
SELECT
  VARIANT_COL:"machine_id"::STRING                       AS machine_id,
  VARIANT_COL:"modality"::STRING                         AS modality,
  VARIANT_COL:"model"::STRING                            AS model,
  VARIANT_COL:"country"::STRING                          AS country,
  VARIANT_COL:"region"::STRING                           AS region,
  VARIANT_COL:"hospital_id"::STRING                      AS hospital_id,
  VARIANT_COL:"hospital_name"::STRING                    AS hospital_name,
  TO_TIMESTAMP(VARIANT_COL:"install_date"::NUMBER, 6)::DATE AS install_date,
  VARIANT_COL:"scans_per_day"::FLOAT                     AS scans_per_day,
  VARIANT_COL:"flaky_reporter"::BOOLEAN                  AS flaky_reporter
FROM FLEET_MASTER;

CREATE OR REPLACE VIEW V_FAILURES AS
SELECT
  VARIANT_COL:"machine_id"::STRING                       AS machine_id,
  TO_TIMESTAMP(VARIANT_COL:"failure_date"::NUMBER, 6)::DATE AS failure_date,
  VARIANT_COL:"component"::STRING                        AS component,
  VARIANT_COL:"sudden"::BOOLEAN                          AS sudden,
  VARIANT_COL:"downtime_days"::NUMBER                    AS downtime_days
FROM FAILURES;

-- features: we only flatten the columns the analytics need (232 exist)
CREATE OR REPLACE VIEW V_FEATURES AS
SELECT
  VARIANT_COL:"machine_id"::STRING                       AS machine_id,
  TO_TIMESTAMP(VARIANT_COL:"date"::NUMBER, 6)::DATE      AS score_date,
  VARIANT_COL:"modality"::STRING                         AS modality,
  VARIANT_COL:"age_years"::FLOAT                         AS age_years,
  VARIANT_COL:"err_warn_7d"::NUMBER                      AS err_warn_7d,
  VARIANT_COL:"days_since_pm"::NUMBER                    AS days_since_pm,
  VARIANT_COL:"label"::NUMBER                            AS label,
  VARIANT_COL:"split"::STRING                            AS split
FROM FEATURES_LABELED;

-- ---------------------------------------------------------------------------
-- 1. Sanity: did everything land?
-- ---------------------------------------------------------------------------
SELECT 'scores' AS tbl, COUNT(*) AS row_count FROM V_SCORES
UNION ALL SELECT 'features_labeled', COUNT(*) FROM V_FEATURES
UNION ALL SELECT 'fleet_master',     COUNT(*) FROM V_FLEET_MASTER
UNION ALL SELECT 'failures',         COUNT(*) FROM V_FAILURES;
-- expect: 24,867 / 24,867 / 500 / 440

-- ---------------------------------------------------------------------------
-- 2. Fleet risk snapshot — the KPI band, straight from the warehouse
-- ---------------------------------------------------------------------------
WITH latest AS (
  SELECT * FROM V_SCORES
  WHERE score_date = (SELECT MAX(score_date) FROM V_SCORES)
)
SELECT
  CASE WHEN risk_calibrated >= 0.20 THEN '1_critical'
       WHEN risk_calibrated >= 0.05 THEN '2_watch'
       ELSE '3_healthy' END                        AS status,
  COUNT(*)                                         AS machines,
  ROUND(AVG(risk_calibrated), 4)                   AS avg_risk
FROM latest
GROUP BY 1
ORDER BY 1;

-- ---------------------------------------------------------------------------
-- 3. This week's top-20 worklist — what the Command Center shows P1
-- ---------------------------------------------------------------------------
SELECT
  s.machine_id,
  f.modality,
  f.country,
  f.hospital_name,
  ROUND(s.risk_calibrated, 3)                          AS risk,
  ROUND(s.risk_calibrated * 2 * 27000, 0)              AS expected_loss_usd  -- p × median 2 downtime days × $27k
FROM V_SCORES s
JOIN V_FLEET_MASTER f USING (machine_id)
WHERE s.score_date = (SELECT MAX(score_date) FROM V_SCORES)
ORDER BY s.risk_calibrated DESC
LIMIT 20;

-- ---------------------------------------------------------------------------
-- 4. The backtest in PURE SQL — recall@20 recomputed in the warehouse
--    Should agree with the Python backtest: 41 caught / 54 ≈ 0.76
-- ---------------------------------------------------------------------------
WITH ranked AS (
  SELECT machine_id, score_date, label,
         ROW_NUMBER() OVER (PARTITION BY score_date ORDER BY risk_calibrated DESC) AS risk_rank
  FROM V_SCORES
  WHERE split = 'test'
)
SELECT
  COUNT_IF(label = 1)                                    AS failures_total,
  COUNT_IF(label = 1 AND risk_rank <= 20)                AS caught_in_top20,
  ROUND(caught_in_top20 / NULLIF(failures_total, 0), 3)  AS recall_at_20
FROM ranked;

-- ---------------------------------------------------------------------------
-- 5. Where does the fleet break? Failures by modality and component
-- ---------------------------------------------------------------------------
SELECT
  fm.modality,
  fa.component,
  COUNT(*)                                  AS failures,
  ROUND(AVG(fa.downtime_days), 2)           AS avg_downtime_days,
  SUM(fa.downtime_days) * 27000             AS downtime_cost_usd
FROM V_FAILURES fa
JOIN V_FLEET_MASTER fm USING (machine_id)
GROUP BY 1, 2
ORDER BY failures DESC;

-- ---------------------------------------------------------------------------
-- 6. Calibration check in SQL — do the probabilities mean what they say?
-- ---------------------------------------------------------------------------
SELECT
  WIDTH_BUCKET(risk_calibrated, 0, 0.5, 10)       AS risk_bucket,
  COUNT(*)                                        AS machine_weeks,
  ROUND(AVG(risk_calibrated), 3)                  AS avg_predicted_risk,
  ROUND(AVG(label), 3)                            AS actual_failure_rate
FROM V_SCORES
WHERE split = 'test'
GROUP BY 1
HAVING COUNT(*) > 20
ORDER BY 1;
-- reading: avg_predicted_risk ≈ actual_failure_rate per bucket = well calibrated

-- ---------------------------------------------------------------------------
-- 7. Age vs risk — is the model just ranking by age? (it shouldn't be)
-- ---------------------------------------------------------------------------
SELECT
  fl.modality,
  ROUND(fl.age_years)                         AS age_years,
  COUNT(*)                                    AS machine_weeks,
  ROUND(AVG(s.risk_calibrated), 4)            AS avg_risk,
  ROUND(AVG(s.label), 4)                      AS actual_rate
FROM V_FEATURES fl
JOIN V_SCORES s ON fl.machine_id = s.machine_id AND fl.score_date = s.score_date
GROUP BY 1, 2
HAVING COUNT(*) > 100
ORDER BY 1, 2;
