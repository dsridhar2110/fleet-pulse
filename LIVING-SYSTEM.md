# Fleet Pulse — The Living System (pivot spec)

> **What changed.** Fleet Pulse v1 was a *one-shot batch*: generate a year of data once,
> score once, export static JSON, deploy a static case-study page. This document specifies
> the **v2 pivot to a living system** — a hosted feed that generates near-real telemetry
> **every day**, onboards **new customers and machines** over time, writes to a **real
> always-on database (Neon Postgres)**, produces **multi-horizon predictions** (7 / 14 / 30
> / 90 / 180 days), logs the **decisions a service team would take** and their realized
> outcomes, and presents all of it as a **decision dashboard for service-engineering
> managers** — past decisions and money saved, upcoming decisions and money at risk.
>
> The generator physics, the leakage discipline, and the honest-metrics posture from v1 are
> **kept**. The batch/static architecture is **replaced** by a stateful daily loop.
>
> **Disclaimer unchanged:** independent interview prep; synthetic data; not affiliated with,
> endorsed by, or built on data from Siemens Healthineers.

---

## 1. Locked decisions (from kickoff)

| Decision | Choice | Why |
|---|---|---|
| Scope | **Evolve fleet-pulse in place** | Keep the defensible generator + XGBoost + design system; add the living layer on top. |
| Live database | **Neon Postgres (always-on, free)** | The app reads it live 24/7; the daily job writes to it. Real SQL, sustainable, no metered trial. |
| Time model | **36 months of raw data · model deployed 12 months ago · real daily cron + manual "advance a day"** | 36mo backfill gives a reactive baseline + training corpus; the last 12mo is the *governed continual-learning* window we showcase; cron keeps it live; fast-forward makes it demo-able. |
| Horizons | **Hybrid: XGBoost (7/14d alerts) + survival model (30/90/180d planning)** | Alerting and capacity planning are different jobs; this is the realistic split and the deeper DS story. |
| Learning | **Champion/challenger continual learning under human governance** | The model retrains on matured outcomes (real weight change), adapts thresholds, proposes updates; a human governs promotion. Self-corrects, never acts unsupervised — the right posture for healthcare. |

**Chosen defaults (my call, change if you disagree):**
- **Daily job host:** GitHub Actions cron (Python) — free, real, lives in Deekshita's repo. It generates the day, scores, logs decisions, writes to Neon. The web app never runs Python.
- **App architecture:** Next.js with **server-side reads from Neon** (dynamic / ISR), deployed on Vercel. This replaces the build-time static JSON.
- **Model cadence:** **score every day, retrain weekly**, monitor drift continuously (we finally have a *stream of outcomes*, so monitoring is real, not conceptual — this closes a JD gap).
- **Git target:** `dsridhar2110` (current `gh` login is a different account; switch at push time).

---

## 2. The business framing (what the dashboard sells)

A service-engineering manager for a fleet of imaging scanners has one hard question every
week: **where do I send my limited engineers, and what will it cost me if I'm wrong?**

The living system answers it continuously:
- **Now:** how is every machine doing, and which are drifting toward failure?
- **Backward:** what did we decide over the last months — how many failures did we catch,
  how many false alarms did we eat, how much downtime did we avoid, **how much money did the
  model save vs doing nothing?**
- **Forward:** what does the model want us to do in the next 7 / 14 / 30 / 90 / 180 days —
  the operational worklist (dispatch now) and the planning view (budget parts & crews for
  the quarter), each with expected spend and expected savings.

The candidate signal: not just "I can train a model," but "**I understand the service
business, the economics of a false alarm vs a missed failure, and how a manager actually
uses this to make money-saving decisions.**"

---

## 3. Architecture

```
                         ┌──────────────────────────── GitHub Actions (daily cron) ─────────────────────────────┐
                         │                                                                                        │
   world state ──▶ 1. onboard new customers/machines (schedule)                                                   │
   (in Neon)            2. simulate ONE new day  → append telemetry / errors / failures / maintenance / tickets   │
                        3. update per-machine latent state (component ages, active precursors, rng)               │
                        4. recompute rolling features as-of the new day                                           │
                        5. score:  XGBoost → P(fail ≤7d, ≤14d)   ·   survival → P(fail ≤30/90/180d)               │
                        6. decision policy: build worklist, "dispatch" top-k, log decisions;                      │
                           resolve matured past decisions (did it actually fail in-horizon?)                      │
                        7. recompute economics (expected loss, net savings, downtime avoided)                     │
                        8. write everything back to Neon                                                          │
                         │                                                                                        │
                         └────────────────────────────────────────────────────────────────────────────────────┘
                                                        │
                                              Neon Postgres (always-on)
                                                        │
                                                        ▼
                              Next.js dashboard on Vercel (server reads Neon, live)
                              Fleet Health · Predictions · Decisions (past) · Decisions (upcoming) · Economics
```

- **Weekly** (separate workflow): retrain both models on all matured labels, version the
  model, run drift + performance monitoring, write a monitoring snapshot to Neon.
- **Model artifacts** are versioned in-repo (git); **all world state and facts live in Neon**.
- **Fast-forward:** the same `advance_day` job can be triggered manually (workflow_dispatch
  or a guarded API route) to step the clock live during a demo.

---

## 4. Neon schema (Postgres)

| Table | Grain | Purpose |
|---|---|---|
| `customers` | one row / hospital group | onboarding schedule → "new businesses arriving" |
| `machines` | one row / scanner | modality, model, install & commission dates, owning customer, status |
| `machine_state` | one row / machine (latest) | **latent simulator state**: per-component effective age, active precursor episodes, RNG state — what makes the sim *resumable* day to day |
| `telemetry_daily` | machine × day | the sensor fact table, appended every day |
| `error_events` | event | error-code emissions (mostly benign) |
| `failures` | event | actual failures with component + mode |
| `maintenance` | event | preventive + corrective visits |
| `tickets` | ticket | templated free-text engineer notes (feeds retrieval) |
| `predictions` | machine × as-of-day × horizon | P(fail) at 7/14/30/90/180d + model_version |
| `decisions` | decision | action taken (inspect/dispatch/defer), horizon, expected \$ savings, status, realized outcome |
| `impact_daily` | as-of-day | fleet expected loss, worklist net savings, downtime avoided, cumulative savings |
| `model_versions` | model version | champion/challenger lineage: algo, hyperparams snapshot, decision threshold, trained-on window, metrics (PR-AUC, precision@k, recall@k, lead time), parent_version, promotion status |
| `evolution_log` | model event | the self-learning timeline: RETRAIN · THRESHOLD_SHIFT · DRIFT_DETECTED · FEATURE_ADDED · CHALLENGER_PROMOTED · ROLLBACK — each with trigger (scheduled / drift / performance-decay / human), before→after change, metric effect |
| `governance_actions` | human action | the governor's log: approve / override / hold / rollback, actor role, rationale, which `evolution_log` event it governs |

The **latent-state** design is the technical heart: the generator becomes a resumable state
machine — load state as of day D, emit day D+1, persist new state. Failure physics
(Weibull hazard on effective age, precursor leakage, imperfect repair) are reused from v1's
`degradation.py` / `telemetry.py`, not rewritten.

---

## 5. Modeling — the hybrid

- **7 / 14-day alerts (operational):** the existing XGBoost classifier, extended to a 14-day
  label as well. This is the "who do I inspect this week" model — kept because it's proven,
  calibrated, SHAP-explained, and leakage-tested.
- **30 / 90 / 180-day planning:** a **survival / time-to-failure model** (XGBoost AFT or a
  discrete-time hazard model) that yields a coherent survival curve per machine, so
  P(fail ≤ 30/90/180d) all come from one fit. This is the "budget parts and crews for the
  quarter" model — a genuinely different and deeper technique to defend.
- **Honesty guardrails from v1 stay:** metrics too good = red flag; report precision@k,
  recall@k, lead time, calibration, and a cost-based threshold — never bare accuracy.
- **Monitoring (now real):** because outcomes mature daily, we log PSI/KS feature drift,
  calibration drift, and precision/recall decay on matured labels → retrain trigger. This
  converts the JD's "monitor models" from a talking point into a working loop.

### 5b. Continual learning under human governance (the deployment story)

Over the **last 12 months of deployment** the model doesn't sit still — it learns from what
actually happened and self-corrects, **with a human as the governor**. This is a
champion/challenger loop, not autonomous self-rewriting (that distinction is the honesty line
that wins the room, and it's the correct posture for a healthcare setting).

- **What the model does on its own path:** on schedule and on drift/decay triggers it trains a
  **challenger** on the newest matured outcomes — genuinely new tree weights & parameters —
  re-tunes its decision threshold to the current cost/prevalence, and can surface a **new
  feature** it found predictive. Each challenger is scored on a held-out recent window.
- **Where the human governs:** every promotion passes a **governance gate**. Inside guardrails
  (e.g. retrain on schedule, threshold move within ±10%, no metric regression) the challenger
  is **auto-approved**. Outside them — a bigger threshold move, a feature removal, or any
  metric regression — it is **held for human approval**, and the human can **approve, override,
  or roll back** with a logged rationale.
- **Concrete self-correction episodes** (simulated, dated, defensible), e.g.:
  - *False-alarm cluster on CT tubes* → drift detector fires → challenger retrains with a new
    arc-count feature → precision@20 +0.06 → **human approves** promotion.
  - *Challenger regresses on MRI recall* → auto-promotion blocked by the gate → **human holds**,
    rolls back to the champion.
- **Why it maps to the JD:** monitoring, validation strategy, model registry, human-in-the-loop,
  and "no autonomous action in a clinical setting" — all demonstrated as a *working loop*, not
  slideware. It is showcased and offered as a capability; the human stays the governor.

---

## 6. The dashboard (service-manager decision cockpit)

Clock header on every page: **"As of <sim date>"** + a **⏩ Advance a day** control.

1. **Fleet Health** — live KPIs (critical / watch / healthy, fleet expected loss, machines
   under management, new this month), status distribution, health trend over time.
2. **Predictions** — ranked machine risk with a **horizon selector (7/14/30/90/180d)**;
   per-machine drill-down: telemetry with failure markers, SHAP/risk drivers, survival curve.
3. **Decisions — Past** — timeline of decisions over the last months, each tagged
   **caught / false alarm / missed**, with downtime avoided and \$ saved; the running scoreboard.
4. **Decisions — Upcoming** — the forward worklist per horizon: *dispatch now* (7/14d) and
   *plan for the quarter* (30/90/180d), each with expected spend and expected savings.
5. **Economics** — cumulative net savings vs do-nothing, downtime days avoided, false-alarm
   cost, ROI, and the assumptions ledger (\$27k/day downtime, \$800/visit, etc.) shown openly.
6. **Model Evolution & Governance** — the 12-month self-learning story: a **performance
   trajectory** (precision@k / recall / lead-time climbing, with version markers), the
   **evolution timeline** (each retrain / threshold shift / new feature — its trigger, its
   before→after, its metric effect), and the **governance log** (what was auto-approved inside
   guardrails vs held, overridden, or rolled back by the human governor). This is the page that
   says "the model changed its own course over the year — under control."

**Design direction (updated 2026-07-18):** the **product dashboard gets its own modern
SaaS / Stripe-style visual identity** — hero moments, contemporary chart components, heavier
design architecture, story-first layout — *not* the petrol/teal report system. It is built to
*sell the story* and prove the business proposition, viewable locally first. (The petrol/teal
Fleet Pulse system in `design/` still governs case-study PDFs and static report artifacts —
the two are now deliberately separate: a polished product skin vs. a print/report identity.)

---

## 7. Build plan (phases)

| Phase | Deliverable | Needs Neon? |
|---|---|---|
| **P0** | This spec + phone-review artifact | no |
| **P1** | Neon schema DDL + DB access layer (SQLAlchemy), local-Postgres testable | build no / run yes |
| **P2** | **Incremental simulator** — refactor generator into a resumable `advance_day(state)`; unit-test that a day-by-day run matches a batch run | no |
| **P3** | Backfill script — seed **36 months** of history + customer/machine onboarding schedule into Neon | yes |
| **P4** | Feature + scoring in the daily loop: XGBoost 7/14d + survival 30/90/180d → `predictions` | yes |
| **P5** | Decision policy + outcome resolution + economics → `decisions`, `impact_daily` | yes |
| **P5b** | **Model-evolution replay** — simulate the 12-month champion/challenger + governance history → `model_versions`, `evolution_log`, `governance_actions` | yes |
| **P6** | Next.js dashboard reading Neon live (6 pages above, incl. Model Evolution & Governance) | yes |
| **P7** | GitHub Actions daily cron + weekly retrain/monitor + deploy to Vercel | yes |
| **P8** | Case-study refresh + interview-walkthrough HTML (the "living system" story) | no |

P1 and P2 are decision-safe and start immediately. P3+ light up the moment the Neon string
lands.

**Progress (2026-07-18):**
- **P0 ✅** — spec + phone-review artifact.
- **P2 ✅** — incremental simulator built & tested. `ml/src/sim/` (`common.py`, `physics.py`,
  `run.py`) is a resumable day-by-day state machine reusing the v1 failure physics. Latent
  state is JSON-serialisable (round-trips through `machine_state`). `tests/test_incremental_sim.py`
  (6 tests, all green) proves it reproduces the batch generator's statistical signature:
  **500 machines, 1.04M telemetry rows, 1.63% machine-week failure rate, ~12% sudden,
  precursor drift present before non-sudden failures, benign error volume dominant.**
- **P1 ✅ (built + live)** — `ml/src/db/schema.sql` (15 tables, 14 indexes; validated with the
  libpg_query Postgres parser) + `ml/src/db/engine.py`. **Neon provisioned via the Vercel
  marketplace** (store `neon-apricot-horizon`, connected to project `fleet-pulse`, PostgreSQL
  17.10); schema created live. Connection string in `ml/.env` (direct) + `web/.env.local`
  (pooled), both gitignored.
- **P3 ✅ (built), running** — `ml/src/sim/world.py` (customer base + growing fleet with an
  onboarding schedule) + `ml/src/db/io.py` (fast `execute_values` writers) + `ml/src/serve/backfill.py`
  (commissions the fleet, steps every day for 36 months, monthly flushes to Neon, persists
  latent state + world clock). Smoke-tested (3 months, 500 machines, 22s); full 36-month
  backfill in progress.
- **P4 ✅** — `ml/src/pipeline/features_live.py` (131 features from Neon) + `ml/src/models/train_live.py`
  (XGBoost 7/14d + XGBoost-AFT survival 30/90/180d → one monotone survival curve). 368,920
  predictions across 178 as-of dates. Held-out: 7d PR-AUC **0.509**, recall@20 **0.87**.
- **P5 ✅** — `ml/src/models/decisions.py` + `econ.py`: weekly worklists, resolved outcomes
  (caught/missed/false-alarm), economics → `decisions` (1,066), `impact_daily` (53 weeks).
  **$11.1M net saved, 97% detection, 13× ROI.**
- **P5b ✅** — `ml/src/models/evolution.py`: 5 model versions, 7 governed evolution events +
  governance actions; current champion anchored to the real measured metrics.
- **P6 ✅** — the **modern dark command-center dashboard** (`web/`), reading Neon live via
  `@neondatabase/serverless`. 5 pages (Overview · Predictions · Decisions · Economics ·
  Model & Governance), bespoke SVG charts, Stripe-style identity. Runs locally + builds clean.
  Fixed: a client-bundle crash (risk helpers split into `web/src/lib/risk.ts` so the Neon
  client never reaches the browser).
- **Deepen (2026-07-18/19):**
  - **Tick engine ✅** — `ml/src/serve/tick.py` advances the world one day: loads persisted
    latent state, simulates the day, appends to Neon, rescores (fast trailing-window features +
    saved model bundle `data/app/live_model.pkl`), rebuilds decisions, moves the clock. ~30s/day.
  - **Machine drill-down ✅** — `web/src/app/machines/[id]` — survival curve, 5-horizon risk,
    risk-over-time, live telemetry sensor charts, service tickets, failure/maintenance timeline.
    Machine IDs across the app link into it.
  - **Advance-a-day button ✅** — `web/src/app/actions.ts` server action runs the tick locally
    (gated by `ALLOW_TICK`); `advance-button.tsx` in the topbar. On the hosted site the daily
    cron moves the clock instead.
  - **Real quarterly retrains ✅** — `ml/src/serve/retrain_history.py` retrains at 5 cutoffs
    across the deployment year and feeds the *measured* metrics into `evolution.py` — the Model
    page trajectory is now real, not illustrative.
  - **Daily cron ✅** — `.github/workflows/daily-tick.yml` (advance one day, 06:00 UTC) +
    `weekly-retrain.yml` (retrain + refresh evolution + commit bundle). Activate on push +
    `DATABASE_URL` secret.
- **Next:** push to `dsridhar2110`, set the Actions `DATABASE_URL` secret, deploy `web/` public
  on Vercel (env already wired via the Neon integration).

---

## 8. What I need from you (from the phone)

1. **Neon connection string** — go to **neon.tech** → sign in (Deekshita's account) →
   create a free project (name it `fleet-pulse`) → copy the **pooled** connection string
   (`postgresql://...-pooler...neon.tech/...?sslmode=require`). Paste it here. That's the
   only credential that unblocks going live. *(Or say the word and I'll provision Neon via
   the Vercel marketplace integration under your account instead.)*
2. **Confirm the defaults in §1** (GitHub Actions cron, Next.js dynamic on Vercel, weekly
   retrain) — or redirect.
3. **Push account** — confirm the repo pushes to `dsridhar2110` (current `gh` login is
   `mkshamanth93-byte`; I'll switch before pushing).
