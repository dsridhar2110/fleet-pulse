# Fleet Pulse — Project Context (CLAUDE.md)

> Single source of truth for this repository. Read this first. It captures the
> business problem, the architecture, the 7-day plan with every build touchpoint,
> how to run each stage, the real results, and the current status.

---

## 0. What this is (in one paragraph)

**Fleet Pulse** is an end-to-end **predictive-maintenance product for a simulated
medical-imaging service fleet**. It generates a realistic synthetic fleet of 500
scanners (MRI / CT / X-ray), turns their telemetry and service logs into features,
trains a model that scores each machine's **probability of failing within 7 days**,
and presents the result as a real web product — a *"Service Command Center."* It is
an **independent portfolio project built to prepare for an interview** (see §1). It is
**not affiliated with, endorsed by, or built on data from Siemens Healthineers**; all
data is synthetic and all brand styling is an independent concept.

---

## 1. Why this exists (the objective)

Built to turn around **Deekshita's interview for Data Scientist — Customer Service
(R&D), Siemens Healthineers, Bangalore (Job ID 511928)**. The team almost certainly
builds predictive-maintenance / service analytics over the global installed base of
imaging equipment (the "Smart Remote Services / Guardian / teamplay Fleet" world).

**Strategy:** walk in having already built a working miniature of that exact system,
present it with humility ("a toy next to your real system; here's what building it
taught me, and here's what I'd ask your team"), and **send the case study + live demo
link to the recruiter 1–2 days before the interview.**

**Locked decisions:**
- **Location/posting:** Bangalore (Job ID 511928).
- **GenAI assistant scope:** **retrieval-only** (answers from ticket/manual history; no live LLM call).
- **Delivery tactic:** **send ahead** (case study PDF + live demo link before the interview).

**Two audiences for this repo:** the candidate (data scientist, defends it in the
interview) and her coordinator (business/full-stack, presents & explains it). Keep
docs understandable to both — business framing on top, technical depth underneath.

---

## 2. The business problem

When a scanner goes down unexpectedly, three parties lose at once:
- **The hospital** — 20–40 patient scans cancelled that day; diagnoses delayed.
- **Siemens** — SLA penalty + an engineer dispatched reactively (slow, expensive).
- **The service team** — thousands of logs, no signal; they learn it broke when the phone rings.

Rough economics used throughout (order-of-magnitude, disclosed as assumptions):
- Unplanned downtime ≈ **$27k/day** in lost scanning revenue.
- A proactive inspection visit ≈ **$800**.
- A missed failure therefore costs **~100×** a wasted inspection.
- ~**250,000+** connected Siemens devices worldwide generate logs.

**The product's job:** turn machine logs into a **short, ranked, actionable weekly
worklist** — "which machines to inspect before they fail" — at an acceptable
false-alarm cost.

---

## 3. Repository layout (monorepo)

```
fleet-pulse/
├── CLAUDE.md                 ← this file (master context)
├── .gitignore                ← ignores .venv, node_modules, .next, raw/feature data
├── design/                   ← DESIGN SYSTEM for all reports (see §12)
│   ├── DESIGN-SYSTEM.md          ← the report guardrails contract
│   ├── report.css                ← shared stylesheet every report links/inlines
│   ├── fleetpulse.mplstyle        ← matplotlib style so EDA charts match
│   └── templates/report-template.html
├── .claude/skills/fleetpulse-report/SKILL.md  ← "make a report" → auto-follows the design system
├── reports/                  ← put generated reports here: reports/<name>/index.html (+ img/)
├── presentation/
│   └── fleet-pulse-brief.html  ← the plan/brief (business-facing, standalone HTML)
├── ml/                       ← the Python ENGINE (data science)  [BUILT]
│   ├── Makefile              ← one target per pipeline stage; sets Spark env vars
│   ├── requirements.txt
│   ├── config/
│   │   ├── fleet_config.yaml     ← fleet size, modality mix, countries, data-quality knobs
│   │   └── failure_modes.yaml    ← component failure physics (Weibull + precursors) — SHOW THIS IN INTERVIEW
│   ├── src/
│   │   ├── fleetgen/         ← synthetic data generator (pure pandas/numpy)
│   │   │   ├── fleet_master.py   ← machines, models, hospitals, countries, install dates
│   │   │   ├── degradation.py    ← hazard + precursor engine (the defensibility core)
│   │   │   ├── telemetry.py      ← daily sensor emission, noise, missingness, calibration offsets
│   │   │   ├── events.py         ← error-code events + maintenance records
│   │   │   ├── tickets.py         ← service tickets with templated free-text engineer notes
│   │   │   └── generate.py        ← CLI: orchestrates the above → data/raw (prints gate stats)
│   │   ├── pipeline/
│   │   │   ├── features_spark.py  ← PySpark feature engineering over Parquet
│   │   │   ├── labels.py          ← leakage-safe 7-day labels + time-based split
│   │   │   └── export_web.py      ← exports JSON artifacts into web/public/data
│   │   └── models/
│   │       ├── train_xgb.py       ← XGBoost + Platt calibration; writes scores + model
│   │       ├── baseline_anomaly.py← z-score / IsolationForest / age-rank baselines
│   │       ├── evaluate.py        ← PR-AUC, precision@k, calibration, cost, lead-time → docs/img
│   │       └── explain.py         ← SHAP global + per-machine top drivers
│   ├── tests/
│   │   ├── test_generator.py     ← failure-rate band, age→failure, benign-noise checks
│   │   └── test_no_leakage.py    ← asserts no feature uses data after the scoring day
│   ├── data/                     ← generated (gitignored except data/app artifacts)
│   │   ├── raw/                   ← telemetry/, error_events, failures, maintenance, tickets, fleet_master
│   │   ├── features/             ← feature_table.parquet, labeled.parquet
│   │   └── app/                  ← model + scores + metrics + shap (committed)
│   └── docs/img/                 ← evaluation charts (PR curves, calibration, cost, lead-time)
└── web/                      ← the PRODUCT (Next.js + shadcn)  [IN PROGRESS — Day 2]
    ├── public/data/          ← precomputed JSON the UI reads (fleet.json, metrics.json, machines/*.json)
    └── src/
        ├── app/              ← layout.tsx (app shell), page.tsx (command center), globals.css (theme)
        ├── components/       ← app-shell, kpi-cards, fleet-table, status-pill, ui/ (shadcn)
        └── lib/              ← data.ts (reads public/data), types.ts, format.ts, utils.ts
```

---

## 4. Architecture & data flow

```
config/*.yaml
      │
      ▼
fleetgen.generate ──► ml/data/raw/          (telemetry, error_events, failures, maintenance, tickets, fleet_master)
      │
      ▼
features_spark.py ──► ml/data/features/feature_table.parquet   (24,867 rows × 226 cols)
labels.py         ──► ml/data/features/labeled.parquet         (adds label, days_to_failure, split)
      │
      ▼
train_xgb.py      ──► ml/data/app/{xgb_model.json, scores.parquet, model_meta.json}
baseline_anomaly  ──► ml/data/app/baseline_scores.parquet
explain.py        ──► ml/data/app/{shap_global.parquet, shap_per_machine.parquet}
evaluate.py       ──► ml/data/app/metrics.json + ml/docs/img/*.png
      │
      ▼
export_web.py     ──► web/public/data/{fleet.json, metrics.json, drivers_global.json, machines/<id>.json}
      │
      ▼
Next.js (web/)  reads JSON at build time  ──►  static site  ──►  Vercel
```

**Design principle:** the generator is **pandas** (fast iteration); the feature job is
**PySpark** (that's the JD skill being demonstrated); **DuckDB** is the serving/analytics
stand-in. The deployed web app is **fully static** — it runs no Python, Spark, or model;
it only reads precomputed JSON.

### Tech-stack mapping (say this proactively in the interview)
| JD / Siemens stack | Fleet Pulse uses | Why it maps 1:1 |
|---|---|---|
| Azure Blob + Parquet | local partitioned Parquet | same format & partition layout; swap path to `abfss://` |
| Databricks / PySpark | PySpark 4 (local mode) | identical DataFrame code; runs unmodified on a cluster |
| Snowflake / Kusto | DuckDB | same analytical SQL over columnar data |
| Azure Data Factory | Makefile-staged pipeline | same DAG of ingestion → transform → train → score |
| NLP / GenAI | embeddings + retrieval (planned) | same retrieval-augmented pattern (retrieval-only) |
| Neo4j / Agentic AI | roadmapped, not built | honest future work — do NOT over-claim |

---

## 5. Data creation — touchpoints & design decisions

All numbers are **simulation choices motivated by failure-physics intuition, not
measurements of real equipment.** The generator WILL be probed in interview; the
defense is "every choice encodes a known phenomenon, and I can name what it omits."

- **Fleet:** 500 machines — 45% CT / 35% MRI / 20% X-ray, 10 countries, install years 2015–2024.
- **Failure model:** each component draws a **Weibull lifetime** on its *effective age*
  (shape k ≈ 1.8–2.5 → wear-out). CT/X-ray tubes are **usage-driven** (age by scan
  volume, not calendar). Corrective repair is **imperfect** (age resets to ~20%, not 0);
  preventive maintenance shaves ~10% off age. Config: `failure_modes.yaml`.
- **Precursors:** before a non-sudden failure, degradation **leaks into sensors** over a
  randomized 7–45 day window (helium boil-off drift, arc-count bursts, vibration trend).
  **~15% of failures are sudden (no precursor)**, plus **false-precursor** episodes that
  drift and recover — so the task is genuinely hard (prevents a fake-perfect model).
- **Class balance:** ~**1.7% of machine-weeks** are failures (target band 1–3%). Real
  rates are lower; event frequency is upsampled so one year is trainable (disclosed).
- **Data quality:** 3% missing telemetry days (15% for flaky machines), per-machine
  calibration offsets, mostly-benign error-code volume (so "error-burst" features are earned).
- **Grain:** daily (~1.04M telemetry rows) — Spark-worthy, laptop-iterable. Pipeline is grain-agnostic.
- **Tickets:** templated free text with inconsistent engineer shorthand
  ("He level low" / "helium lvl dropping" / "cryo issue") — motivates the NLP/retrieval layer.

### Leakage traps (documented + tested — this is the interview flex)
1. **Failure-day tautology** — the failure day emits critical codes + a ticket. Features
   are strictly ≤ scoring day *t*; the label window is `(t, t+7]`, so a positive's
   failure lies strictly after *t*.
2. **Post-failure ticket text** — written after the failure; may feed retrieval, never the classifier.
3. **Dispatch-before-failure** — in real service data the repair dispatch can predate the
   "failure" timestamp; clean in the generator but **named as the trap to hunt in real data**.
4. **Random splits** — memorize machine trajectories. **Time-based split is mandatory**
   (train Jan–Aug, val Sep–Oct, test Nov–Dec). `tests/test_no_leakage.py` asserts no
   feature uses data after *t*.

---

## 6. Model creation — spec & results

- **Prediction:** P(machine fails within 7 days). **Grain:** one score per machine per week.
- **Model:** XGBoost (tabular, few positives, native missing-value handling for
  modality-specific sensors, SHAP explainability). Chosen over deep learning deliberately.
- **Calibration:** **Platt (sigmoid)**, not isotonic — with only ~50 validation positives,
  isotonic overfits into coarse step plateaus (fake-looking 0.64/1.00 scores); Platt stays smooth.
- **Split:** time-based (train Jan–Aug / val Sep–Oct / test Nov–Dec).

### Results (test window, Nov–Dec) — honest, defensible
| Metric | Value | Reading |
|---|---|---|
| PR-AUC (XGBoost) | **0.48** | vs random baseline ~0.013 |
| PR-AUC baselines | z-score 0.20 · IsolationForest 0.07 · age-rank 0.03 | model ~2× best simple rule |
| ROC-AUC | 0.94 | footnote only — flattering at 1.3% prevalence |
| Precision@20 | **0.23** | of 20 weekly inspections, ~1-in-4-5 catches a real failure |
| Recall@20 | **0.78** | a top-20 worklist captures 78% of that week's failures |
| Brier | 0.009 | well-calibrated |
| Median lead time | **3 days** | enough to schedule an engineer + pre-position the part |

**Evaluation framing (the seniority signal):** don't report "accuracy." Report a
**weekly worklist a service team can act on** — precision@k, lead time, calibration, and
a **cost-based threshold** (missed:visit ≈ 100:1). Charts live in `ml/docs/img/`.

**SHAP discipline:** global + per-machine top drivers; caveat aloud — "SHAP explains the
model, not the physics; on real data I'd validate those reasons *with service engineers*."

---

## 7. The product (web/)

- **Stack:** Next.js 16 (App Router) · React 19 · Tailwind v4 · shadcn/ui · Recharts (charts, Day 3+) · Geist font.
- **Theme:** Siemens Healthineers-inspired **petrol/teal clinical** identity. Tokens in
  `src/app/globals.css` (`--primary` teal, dark petrol `--ground`/sidebar, semantic
  `--critical`/`--watch`/`--healthy`).
- **Data:** read at **build time** from `web/public/data/*` via `src/lib/data.ts` (fs). The
  site is fully static; machine detail pages fetch `/data/machines/<id>.json` client-side.
- **Current screens:**
  - **Command Center (`/`)** — KPI cards + interactive **fleet worklist** (search, filter by
    modality/country/status, ranked by risk). Components: `kpi-cards`, `fleet-table`, `status-pill`.
  - **`/model`** (planned, Day 4) — evaluation as a product page.
  - **`/machines/[id]`** (planned, Day 3) — telemetry charts, risk drivers, ticket history.
  - **`/assistant`** (planned, Day 5) — retrieval-only service assistant.

---

## 8. The 7-day plan (touchpoints)

| Day | Phase | Touchpoints / deliverable | Status |
|---|---|---|---|
| **1** | **Engine** | `fleetgen/*` → raw data · `features_spark.py` + `labels.py` → features · `train_xgb.py` + `baseline_anomaly.py` + `evaluate.py` + `explain.py` → model & metrics · `export_web.py` → JSON. Tests pass. | ✅ Done |
| **2** | **Product shell** | Next.js + shadcn, petrol/teal theme, app shell, **Command Center** (KPIs + fleet worklist). | 🚧 In progress |
| **3** | **Drill-down** | `/machines/[id]`: telemetry charts w/ failure markers, per-machine SHAP drivers, ticket history. | ⬜ Planned |
| **4** | **Proof** | `/model`: PR curves, precision@k, calibration, cost curve, lead-time — as a clean product page. | ⬜ Planned |
| **5** | **Assistant + deploy** | Retrieval-only assistant over tickets/manuals; deploy to **Vercel** (static). | ⬜ Planned |
| **6** | **Presentation** | Case-study PDF (problem, approach, honest limits, questions for the team) + 3-min walkthrough video; **send-ahead** email to recruiter. | ⬜ Planned |
| **7** | **Rehearse** | Fresh-clone run-through, fix rough edges, rehearse 3-min walkthrough + hard-question answers. | ⬜ Planned |

---

## 9. How to run

### Prerequisites (macOS, already set up on the build machine)
- **Python 3.13** (Homebrew) · venv at `ml/.venv`
- **Java 17** — `brew install openjdk@17` (PySpark needs it)
- **libomp** — `brew install libomp` (XGBoost needs it)
- **Node 22** (Homebrew) for `web/`

### Engine (ml/)
The Makefile sets `JAVA_HOME`, `PYSPARK_PYTHON`, `PYSPARK_DRIVER_PYTHON`, `PYTHONPATH`.
Spark workers MUST use the venv Python — do not rely on system Python 3.9.
```bash
cd ml
make setup        # create venv + install requirements (first time)
make data         # fleetgen → data/raw   (prints failure-rate gate stats)
make features     # PySpark features + leakage-safe labels
make train        # XGBoost + baselines + evaluation + SHAP → data/app + docs/img
make test         # pytest (generator sanity + no-leakage)
# then export JSON for the web app:
PYTHONPATH=$PWD/src .venv/bin/python src/pipeline/export_web.py
```
Manual env (if running scripts directly, not via make):
```bash
export JAVA_HOME=/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home
export PYSPARK_PYTHON=$PWD/.venv/bin/python PYSPARK_DRIVER_PYTHON=$PWD/.venv/bin/python
export PYTHONPATH=$PWD/src
```

### Product (web/)
```bash
cd web
npm install       # first time (create-next-app already ran)
npm run dev       # local dev server
npm run build     # static build (reads public/data at build time)
```
Deploy: Vercel, root directory `web/`. Everything is precomputed; no server needed.

**Regeneration order after any data/model change:** `make data → make features →
make train → export_web.py`, then rebuild `web/`.

---

## 10. Key facts & guardrails

- **Do not over-claim realism.** Always "physically-motivated synthetic data with
  documented simplifications." Keep a ready "what it doesn't capture" list: real error
  taxonomies (thousands, hierarchical), software-version heterogeneity, site effects,
  dispatch-driven label noise, multi-failure interactions.
- **Metrics too good = red flag.** If PR-AUC > ~0.9, the data is too easy; add sudden
  failures / noise. Our ~0.48 with recall@20 = 0.78 is the believable, defensible zone.
- **Regulatory awareness (one line):** human-in-the-loop dispatch, model monitoring, no
  autonomous action — this never drives a clinical/safety decision.
- **Honesty close (the line that wins the room):** "With your real fleet, my first two
  weeks would be sitting with service engineers finding where my generator's assumptions
  are wrong — that's the fastest way to make the model trustworthy."

---

## 11. Current status & immediate next steps

> **LIVE (2026-07-13): https://fleetpulse-service.vercel.app** — single-page case study
> (problem → data & complexity → Modules 1/2/3 → stack → limits). Public, no auth.
> Deployed from `web/` on Vercel (account `mkshamanth-4013`, project `fleet-pulse`).
> Deployment Protection was ON by default and has been **disabled** — re-check after any
> project re-create, or recruiters hit a Vercel login wall.
>
> **Module 3 (Engineer Copilot) is now BUILT** — `ml/src/models/retrieval.py`: TF-IDF +
> cosine over the symptom half of 440 corrective tickets (indexing the full note would
> leak the resolution). Ships as a 187KB JSON the browser scores itself — no LLM, no API
> key, no server. Mirrored scorer in `web/src/lib/retrieval.ts`; **the two must stay in
> lockstep** (same stoplist, tokenizer, sublinear-tf, L2 norm).
> Honest results: leave-one-out **1.000** (worthless — the templated corpus is a near
> string-match), held-out paraphrases **P@1 0.636**, top-10 consensus **0.682**, vs a
> majority-class baseline of **0.452**. Every miss is lexical, not conceptual
> ("grinding noise" → detector, because it shares the token *noise*) → the measured
> argument for embeddings.
>
> **Evaluation bug found & fixed (worth retelling in interview):** the Python eval ranked
> all 440 tickets and took the top one — but an all-out-of-vocabulary query scores 0.0
> against every ticket, and argsort on an all-zero array still returns ticket 0. It was
> scoring a coin flip as a hit and had inflated P@1 from 0.636 to 0.682. Caught by making
> the browser and the pipeline score the same 22 queries and demanding they agree (they
> now agree 22/22). No match must mean no match.

- **Engine:** ✅ built, tested, exporting JSON. As-of snapshot week = **2025-12-22**
  (13 critical / 8 watch / 479 healthy).
- **Business Impact Engine:** ✅ `src/models/impact.py` → `impact.json` (ml/data/app +
  web/public/data). Current-week view: fleet expected loss ~$107k, top-20 worklist
  expected net savings ~$33.5k/week. Test-window backtest: **41/54 failures caught,
  104 downtime days avoided, net savings ~$2.66M ≈ 77.6% of do-nothing downtime cost**
  (assumptions disclosed in the JSON: $27k/day, $800/visit, planned-visit conversion).
- **Product:** ✅ **built, run, deployed.** `web/src/app/page.tsx` is the single-page case
  study (was still the create-next-app starter until 2026-07-13). The old Command Center
  components (`fleet-table`, `kpi-cards`, `app-shell`) remain in `web/src/components/` but
  are **not wired to any route** — they are the raw material for a `/fleet` page if a live
  worklist app is ever wanted. `fleet-table.tsx` had a type error that broke `next build`
  (fixed).
- **Known data bug (unfixed):** `web/public/data/machines/*.json` contain literal `NaN`,
  which is invalid JSON and will throw on `JSON.parse` in a browser. Harmless today (the
  case-study page never reads them) but **must be fixed before any machine drill-down
  page** — `export_web.py` needs `json.dumps(..., allow_nan=False)` and null-coercion.
- **Git:** repo initialized on `main`, **0 commits** (everything untracked). No GitHub remote yet.
- **Housekeeping:** `ml/data/app/calibrator_x.npy` & `calibrator_y.npy` are stale (from the
  pre-Platt isotonic version) — safe to delete.

**Next up (Day 2 finish):** run `web` dev server, verify the Command Center renders,
fix any wiring, then proceed to Day 3 (machine drill-down with Recharts).

---

## 11b. Cloud workspaces (the real-stack slice)

Trial/free accounts created 2026-07-07 under **Deekshita's email** for running the
pipeline on the genuine JD stack (no passwords here — she holds credentials):

- **Databricks Free Edition** (serverless, free forever):
  `https://dbc-67afbecf-53fd.cloud.databricks.com`
- **Snowflake** (30-day trial from 2026-07-07 — ~$400 credits, Enterprise edition,
  **Azure UK South**): `https://app.snowflake.com/sxnmtgc/ne36164`
  (account `RU03385`, identifier `sxnmtgc-ne36164`)

Status:
- **Databricks: ✅ DONE (2026-07-07)** — `notebooks/databricks_features.ipynb` ran on
  Serverless over the uploaded volume (`/Volumes/workspace/default/fleetpulse`),
  reproduced the local result exactly (24,867 × 226), registered
  `workspace.default.fleetpulse_features`, Spark SQL query verified. Upload bundle:
  `ml/data/databricks_upload/`. Screenshots = evidence pack.
- **Snowflake: ✅ DONE (2026-07-07)** — 4 Parquet files loaded (scores,
  features_labeled, fleet_master, failures); wizard landed them as VARIANT →
  flattened into typed views (epoch-microsecond `TO_TIMESTAMP(v,6)` casts);
  analytical layer `ml/sql/snowflake_analytics.sql` ran (KPI snapshot, priced
  worklist, **recall@20 recomputed in pure SQL ≈ 0.76** — matches Python,
  calibration by bucket). Potholes hit & fixed: `rows` reserved word; wrong-file
  load caught via row-count verification. Interview stories live in
  `presentation/interview-walkthrough.html` (v1, Module 1 + cloud slice).
- **Module 2 (Keras autoencoder): ✅ DONE (2026-07-11)** — trained on **Databricks
  serverless** (`notebooks/databricks_autoencoder.ipynb`; local TF hangs in managed
  shells on this Mac — known quirk, don't retry locally). 196→64→16→64→196 dense on
  healthy train windows (14d × 14 sensors, z-scored). **Honest result: test PR-AUC
  0.111** — 9× random, > IsolationForest (0.074), **< z-score alarm (0.202)** and
  XGBoost (0.479). Reported openly; roadmap: max per-sensor error, per-modality,
  LSTM-AE. Artifacts: `data/app/anomaly_scores.parquet`, `anomaly_metrics.json`;
  teaching notebook `autoencoder_anomaly.ipynb` (loads results, no local TF).
- **Pending ask (user, 2026-07-07):** a "use cases" interview-walkthrough HTML for
  FleetPulse — **v2 exists** (`presentation/interview-walkthrough.html`, Modules 1–2
  + cloud); final refresh after Module 3 + dashboard.

Honest interview line: "Databricks serverless + Snowflake-on-Azure; in production
this would be Azure Databricks in the customer's tenant."

## 12. Reports & the design system (IMPORTANT for every artifact)

Every report, EDA writeup, case study, presentation, storyboard, one-pager, or snippet
produced in this repo MUST share one visual identity — the Fleet Pulse petrol/teal
clinical system, the same one used by `web/` and `presentation/`. This is enforced, not
optional.

- **The contract:** `design/DESIGN-SYSTEM.md` — palette, type, layout, chart rules, voice,
  the required footer disclaimer. Read it before authoring anything visual.
- **The stylesheet:** `design/report.css` — link it (or inline it for standalone sharing).
  Never fork it or add ad-hoc colors/fonts.
- **The starting point:** copy `design/templates/report-template.html` →
  `reports/<name>/index.html`; put figures in `reports/<name>/img/`.
- **Charts:** `plt.style.use("design/fleetpulse.mplstyle")` so every EDA/eval figure is on-palette.
- **The skill:** `.claude/skills/fleetpulse-report/SKILL.md` — in Cursor/Claude Code, asking
  to "make a report / EDA / case study" loads this and auto-applies the system.

Hard rules: teal is the only accent (red/amber/green = state only); system fonts only (no
CDN); tabular figures for numbers/IDs; business framing first; disclose synthetic data;
keep the footer disclaimer. When unsure, copy an existing report.

## 13. Related context (candidate)

Deekshita: 7 yrs enterprise software/service delivery (OpenText ECM; delivered a $1.5M
FIFA WC 2022 programme) + MSc Data Science (Monash, completed Jan 2026). Strong on
Python (pandas, scikit-learn, XGBoost), SQL, PySpark, time-series, NLP; no prior
production-ML deployment. Narrative: *"I've lived the enterprise-service side; I built
the data-science side for your exact problem."*
