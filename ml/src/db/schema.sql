-- Fleet Pulse — the Living System · Neon Postgres schema (canonical DDL).
-- Idempotent: safe to run repeatedly. The daily job writes here; the Next.js
-- dashboard reads here. All data is synthetic (see project disclaimer).

-- ========================================================================== --
--  Fleet master (grows over time via customer onboarding)
-- ========================================================================== --
CREATE TABLE IF NOT EXISTS customers (
    customer_id     TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    country         TEXT NOT NULL,
    region          TEXT NOT NULL,
    segment         TEXT,                       -- e.g. IDN / hospital / imaging-centre
    onboarded_date  DATE NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS machines (
    machine_id      TEXT PRIMARY KEY,
    customer_id     TEXT REFERENCES customers(customer_id),
    modality        TEXT NOT NULL,              -- MRI / CT / XRAY
    model           TEXT NOT NULL,
    country         TEXT NOT NULL,
    region          TEXT NOT NULL,
    hospital_name   TEXT,
    install_date    DATE NOT NULL,              -- when the unit was first installed
    commission_date DATE NOT NULL,              -- when it entered THIS fleet's monitoring
    scans_per_day   REAL NOT NULL,
    flaky_reporter  BOOLEAN NOT NULL DEFAULT false,
    status          TEXT NOT NULL DEFAULT 'active',   -- active / retired
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_machines_customer ON machines(customer_id);
CREATE INDEX IF NOT EXISTS idx_machines_modality ON machines(modality);

-- Latent simulator state — one current row per machine. This is what makes the
-- simulation resumable day-to-day (component ages, scheduled failures, RNG).
CREATE TABLE IF NOT EXISTS machine_state (
    machine_id      TEXT PRIMARY KEY REFERENCES machines(machine_id),
    as_of_date      DATE NOT NULL,
    state           JSONB NOT NULL,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ========================================================================== --
--  Daily facts (appended every simulated day)
-- ========================================================================== --
-- Wide telemetry: one row per machine-day, sensor readings as JSONB (sensors
-- differ by modality). Far fewer rows than long format, ideal for a live DB.
CREATE TABLE IF NOT EXISTS telemetry_daily (
    machine_id      TEXT NOT NULL REFERENCES machines(machine_id),
    date            DATE NOT NULL,
    modality        TEXT NOT NULL,
    scans_count     REAL,
    readings        JSONB NOT NULL,             -- {sensor: value, ...}
    PRIMARY KEY (machine_id, date)
);
CREATE INDEX IF NOT EXISTS idx_telemetry_date ON telemetry_daily(date);

CREATE TABLE IF NOT EXISTS error_events (
    id              BIGSERIAL PRIMARY KEY,
    machine_id      TEXT NOT NULL REFERENCES machines(machine_id),
    date            DATE NOT NULL,
    error_code      TEXT NOT NULL,
    family          TEXT NOT NULL,
    severity        TEXT NOT NULL               -- info / warning / critical
);
CREATE INDEX IF NOT EXISTS idx_errors_machine_date ON error_events(machine_id, date);
CREATE INDEX IF NOT EXISTS idx_errors_date ON error_events(date);

CREATE TABLE IF NOT EXISTS failures (
    id              BIGSERIAL PRIMARY KEY,
    machine_id      TEXT NOT NULL REFERENCES machines(machine_id),
    failure_date    DATE NOT NULL,
    component       TEXT NOT NULL,
    sudden          BOOLEAN NOT NULL,
    downtime_days   INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_failures_machine ON failures(machine_id, failure_date);
CREATE INDEX IF NOT EXISTS idx_failures_date ON failures(failure_date);

CREATE TABLE IF NOT EXISTS maintenance (
    id              BIGSERIAL PRIMARY KEY,
    machine_id      TEXT NOT NULL REFERENCES machines(machine_id),
    date            DATE NOT NULL,
    maintenance_type TEXT NOT NULL,             -- scheduled / corrective
    component       TEXT
);
CREATE INDEX IF NOT EXISTS idx_maint_machine ON maintenance(machine_id, date);

CREATE TABLE IF NOT EXISTS tickets (
    ticket_id       BIGSERIAL PRIMARY KEY,
    machine_id      TEXT NOT NULL REFERENCES machines(machine_id),
    open_date       DATE NOT NULL,
    close_date      DATE,
    ticket_type     TEXT NOT NULL,              -- corrective / preventive / no_fault_found
    component       TEXT,
    part_replaced   TEXT,
    engineer_id     TEXT,
    downtime_days   INTEGER NOT NULL DEFAULT 0,
    note_text       TEXT
);
CREATE INDEX IF NOT EXISTS idx_tickets_machine ON tickets(machine_id, open_date);

-- ========================================================================== --
--  Model outputs
-- ========================================================================== --
-- Multi-horizon risk. XGBoost supplies 7/14d; survival model supplies 30/90/180d.
CREATE TABLE IF NOT EXISTS predictions (
    machine_id      TEXT NOT NULL REFERENCES machines(machine_id),
    as_of_date      DATE NOT NULL,
    horizon_days    INTEGER NOT NULL,           -- 7 / 14 / 30 / 90 / 180
    p_fail          REAL NOT NULL,
    model_version   TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (machine_id, as_of_date, horizon_days, model_version)
);
CREATE INDEX IF NOT EXISTS idx_pred_asof ON predictions(as_of_date, horizon_days);

-- The service team's decision log, with realized outcomes for the backward view.
CREATE TABLE IF NOT EXISTS decisions (
    decision_id     BIGSERIAL PRIMARY KEY,
    machine_id      TEXT NOT NULL REFERENCES machines(machine_id),
    as_of_date      DATE NOT NULL,
    horizon_days    INTEGER NOT NULL,
    action          TEXT NOT NULL,              -- inspect / dispatch / defer
    risk_score      REAL,
    expected_cost   REAL,
    expected_savings REAL,
    status          TEXT NOT NULL DEFAULT 'open',   -- open / dispatched / resolved
    outcome         TEXT NOT NULL DEFAULT 'pending',-- caught / false_alarm / missed / pending
    outcome_date    DATE,
    model_version   TEXT,
    rationale       TEXT
);
CREATE INDEX IF NOT EXISTS idx_decisions_asof ON decisions(as_of_date);
CREATE INDEX IF NOT EXISTS idx_decisions_machine ON decisions(machine_id, as_of_date);

CREATE TABLE IF NOT EXISTS impact_daily (
    as_of_date              DATE PRIMARY KEY,
    fleet_expected_loss     REAL,
    worklist_size           INTEGER,
    worklist_net_savings    REAL,
    downtime_days_avoided    REAL,
    do_nothing_cost         REAL,
    cumulative_net_savings   REAL,
    assumptions             JSONB
);

-- ========================================================================== --
--  Model evolution & governance (the 12-month continual-learning story)
-- ========================================================================== --
CREATE TABLE IF NOT EXISTS model_versions (
    version         TEXT PRIMARY KEY,           -- v1, v2, ...
    algo            TEXT NOT NULL,              -- xgboost / survival-aft / ...
    trained_from    DATE,
    trained_to      DATE,
    hyperparams     JSONB,
    threshold       REAL,
    metrics         JSONB,                      -- {pr_auc, precision_at_k, recall_at_k, lead_time}
    parent_version  TEXT REFERENCES model_versions(version),
    status          TEXT NOT NULL DEFAULT 'challenger', -- champion / challenger / retired
    promoted        BOOLEAN NOT NULL DEFAULT false,
    promoted_at     DATE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS evolution_log (
    id              BIGSERIAL PRIMARY KEY,
    ts              DATE NOT NULL,
    event_type      TEXT NOT NULL,   -- RETRAIN / THRESHOLD_SHIFT / DRIFT_DETECTED /
                                     -- FEATURE_ADDED / CHALLENGER_PROMOTED / ROLLBACK
    trigger         TEXT NOT NULL,   -- scheduled / drift / performance_decay / human
    version         TEXT REFERENCES model_versions(version),
    parent_version  TEXT REFERENCES model_versions(version),
    change          JSONB,           -- {field, before, after}
    metric_effect   JSONB,           -- {metric, before, after, delta}
    note            TEXT
);
CREATE INDEX IF NOT EXISTS idx_evolution_ts ON evolution_log(ts);

CREATE TABLE IF NOT EXISTS governance_actions (
    id              BIGSERIAL PRIMARY KEY,
    ts              DATE NOT NULL,
    evolution_event_id BIGINT REFERENCES evolution_log(id),
    actor_role      TEXT NOT NULL,   -- service-DS-lead / service-eng-manager
    action          TEXT NOT NULL,   -- approve / override / hold / rollback / auto-approve
    rationale       TEXT
);
CREATE INDEX IF NOT EXISTS idx_governance_ts ON governance_actions(ts);

-- ========================================================================== --
--  Data-science depth surfaces (Module 1 drivers, Module 2 anomaly, Module 3 retrieval)
-- ========================================================================== --
-- Module 1 — per-machine risk drivers (SHAP top contributions on the current day).
CREATE TABLE IF NOT EXISTS risk_drivers (
    machine_id      TEXT PRIMARY KEY REFERENCES machines(machine_id),
    as_of_date      DATE NOT NULL,
    drivers         JSONB NOT NULL     -- [{feature, value, contribution, direction}, ...]
);

-- Module 2 — per-machine unsupervised anomaly signal (the shipped z-score winner,
-- plus the linear-autoencoder reconstruction error for the comparison).
CREATE TABLE IF NOT EXISTS anomaly_daily (
    machine_id      TEXT PRIMARY KEY REFERENCES machines(machine_id),
    as_of_date      DATE NOT NULL,
    zscore_anomaly  REAL,              -- shipped signal: max |z| across sensors vs healthy baseline
    recon_error     REAL,              -- linear-AE (PCA-16) reconstruction error
    is_anomaly      BOOLEAN,           -- z-score over the healthy-percentile threshold
    top_sensor      TEXT               -- sensor driving the anomaly
);

-- Module 3 — per-machine retrieved similar historical tickets (TF-IDF + cosine).
CREATE TABLE IF NOT EXISTS ticket_neighbors (
    machine_id      TEXT PRIMARY KEY REFERENCES machines(machine_id),
    query_text      TEXT,
    neighbors       JSONB NOT NULL     -- [{ticket_id, machine_id, similarity, component, note}, ...]
);

-- Small key/value for world bookkeeping (current sim date, world epoch, etc.).
-- Also stores 'model_card' — the single source of truth for headline metrics + method text.
CREATE TABLE IF NOT EXISTS world_meta (
    key             TEXT PRIMARY KEY,
    value           JSONB NOT NULL,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
