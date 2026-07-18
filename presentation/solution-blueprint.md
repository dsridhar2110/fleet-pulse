# FleetPulse — Solution Blueprint (Cloud Slice + Three Modules)

> **What this document is:** the single narrative Deekshita walks into the interview with.
> It covers the problem, the data, the platform, the three modules we're building, who
> uses them, and — critically — **which JD topics this build covers that her existing
> projects don't**. Written to be spoken aloud: every technical term is used correctly,
> then explained in plain words.
>
> **Companion docs:** `fleet-pulse/CLAUDE.md` (build status & how to run) ·
> `reports/data-model-eda/` (data model deep-dive) · `interview-prep/` (question bank).
>
> *Independent interview-prep project. Not affiliated with, endorsed by, or using data
> from Siemens Healthineers. All data is synthetic.*

---

## 0. The five-minute story (start here)

If Deekshita gets five minutes with a hiring manager, this is the arc:

1. **The problem (30s).** "When a hospital scanner fails unexpectedly, everyone loses —
   the hospital cancels a day of patients, the manufacturer pays SLA penalties and sends
   an engineer in firefighting mode. One day of unplanned downtime costs roughly £25–30k.
   Your Customer Service organisation exists to prevent exactly this."
2. **The product (60s).** "So I built FleetPulse: a service-intelligence platform over a
   simulated fleet of 500 imaging machines. It turns raw machine logs into a ranked
   weekly inspection worklist, explains *why* each machine is risky, prices the decision
   in money, and gives the engineer an assistant that recalls similar past failures."
3. **The proof (2min).** Walk one machine end-to-end: telemetry drifting → model flags it
   → SHAP shows the drivers → impact engine shows cost avoided → copilot retrieves the
   matching historical ticket. One story, every module on screen.
4. **The stack (60s).** "The pipeline is the stack from your JD: Parquet on cloud
   storage, PySpark feature engineering on Databricks, Snowflake as the warehouse,
   Python models, a React dashboard. I ran every block for real on free/trial tiers."
5. **The humility close (30s).** "It's a toy next to your installed base — the physics is
   simulated and I documented every simplification. With real data, my first two weeks
   would be sitting with service engineers finding where my assumptions are wrong."

---

## 1. Problem statement

**Business problem.** Hospitals run mission-critical imaging equipment (MRI, CT, X-ray).
Failures are rare per machine but constant across a fleet — and today the service team
finds out when the phone rings. Logs exist; signal is buried in them. The cost asymmetry
is brutal: an unplanned outage costs ~£25–30k/day, while a proactive inspection visit
costs ~£600. Missing a failure is roughly **100× more expensive** than a wasted visit.

**The product's job.** Convert the fleet's machine logs into three things a Customer
Service organisation can act on:

1. **A ranked weekly worklist** — "inspect these 20 machines before they fail" (Module 1)
2. **An early-warning signal** for behaviour that doesn't match any known pattern (Module 2)
3. **Institutional memory on demand** — "we've seen this fault before; here's what fixed it" (Module 3)

**Where this sits at Siemens.** This is the Customer Service / Smart Remote Services
world: ~250k+ connected devices streaming logs, the Guardian Program promising proactive
service, teamplay Fleet giving customers fleet visibility. FleetPulse is a deliberate
miniature of that exact system — built independently, on synthetic data, as proof of
approach.

---

## 2. JD coverage — what THIS build adds (the gap-closure map)

Her existing projects already prove: Python/pandas, XGBoost + SHAP, PySpark + Parquet at
volume (MarketLens, 4.85M rows), SARIMA forecasting (911), NLP (arXiv), recommenders.
**This build exists to close what's missing.** Audited against the JD:

| JD topic | Status before this build | Covered here by |
|---|---|---|
| **Databricks** | Never executed — design-only answer | Feature pipeline run for real on **Databricks Free Edition** (serverless) |
| **Snowflake** | Never executed | Feature/score tables loaded + analytical SQL in a real **Snowflake on Azure UK South** trial account |
| **Azure Blob / ADF** | Never executed | Parquet zones mirrored to Blob if an Azure sub is opened; otherwise Databricks Volumes stand in, with the Blob/ADF mapping documented honestly |
| **Keras / TensorFlow deep learning** | No trained Keras/TF model anywhere | **Module 2: Keras autoencoder** anomaly detector on telemetry |
| **KQL (Kusto)** | Never touched | Telemetry loaded into a free **Azure Data Explorer** cluster; 5–6 real KQL queries (stretch goal) |
| **Model monitoring / drift** | Conceptual only | Designed into the blueprint: PSI/KS drift checks, weekly scoring cadence, retrain trigger — documented, not claimed as running |
| **Agentic AI** (bonus) | One light project | **Module 3: Engineer Copilot** — retrieval-augmented, tool-using assistant pattern |
| **Neo4j / graph** | Nothing built — weakest area | Named roadmap here; covered by the companion `service-graph` project on the same data |
| **CI/CD, TDD, GitHub** | Partial (tests exist) | Repo on GitHub with **GitHub Actions** running the test suite (leakage tests included) |

The rule we follow: **run it for real where a free tier exists; design it honestly where
it doesn't.** Section 11 keeps the two lists separate — that separation *is* the
credibility strategy.

---

## 3. The data

**What kind.** Machine logs from a simulated fleet — the same four families a real
service organisation holds: **telemetry** (daily sensor readings), **event logs**
(error codes), **service records** (failures, maintenance visits), and **free-text
service tickets** written by engineers.

**Source.** Generated by our own failure-physics simulator (`ml/src/fleetgen/`):
components draw Weibull lifetimes (wear-out curves), degradation leaks into sensors over
a 7–45 day window before most failures, ~15% of failures are sudden with no warning,
and data quality is deliberately imperfect (missing days, calibration offsets, noisy
error codes, inconsistent engineer shorthand). Every choice encodes a known real-world
phenomenon; every simplification is documented.

**Volume.**

| Table | Rows | Grain (one row =) | Key |
|---|---:|---|---|
| `fleet_master` | 500 | one machine | PK `machine_id` |
| `telemetry` | 1,041,129 | one machine-day-sensor reading | PK (`machine_id`,`date`,`sensor`) |
| `error_events` | 323,220 | one error-code emission | append-only log, no PK |
| `failures` | 440 | one component failure (ground truth) | PK (`machine_id`,`date`,`component`) |
| `maintenance` | 1,454 | one service visit | (`machine_id`,`date`,`type`) |
| `tickets` | 1,610 | one service ticket | no natural PK — deliberate realism |
| **Total** | **~1.37M rows** | ~60 MB as compressed Parquet | |

**Structure.** A **star schema**: `fleet_master` is the dimension table (who/where the
machines are); the five event tables are facts that join it **N:1 on `machine_id`**
(plain words: many events belong to one machine). Feature engineering aggregates events
**up to a scoring day t** into one row per machine-week — 24,867 rows × 226 features —
with the label "did it fail in the next 7 days?" taken from `failures` only. The
time-based split (train Jan–Aug, validate Sep–Oct, test Nov–Dec) plus a unit-tested
"no feature may see past day t" rule is what keeps the model leakage-free.

---

## 4. The platform & pipeline

The pipeline follows the **medallion architecture** — the raw→clean→consumable layering
convention used on Databricks (plain words: never overwrite your raw data; refine it in
stages):

```
Landing (raw Parquet)          — "bronze": immutable machine logs, partitioned by modality
      │  Azure Blob Storage in production · Databricks Volumes in our slice
      ▼
PySpark feature engineering    — "silver": cleaned, joined, aggregated to machine-week grain
      │  Databricks (Free Edition, serverless) — same DataFrame code as local
      ▼
Feature & score tables         — "gold": consumable, business-ready
      │  Snowflake (trial, Azure UK South) — analytical SQL layer
      ▼
Model training & batch scoring — Python: XGBoost (M1) · Keras autoencoder (M2)
      ▼
Serving artifacts              — scores, SHAP drivers, impact numbers → JSON
      ▼
FleetPulse dashboard           — Next.js/React "Service Command Center" (+ Copilot, M3)
```

**Orchestration** (what kicks each stage off): locally a Makefile DAG; in production
this is **Azure Data Factory** or Databricks Workflows on a weekly schedule — same DAG,
different scheduler. **Batch, not streaming** — scores refresh weekly because the
worklist decision is weekly; Event Hub streaming is roadmap, not requirement.

**Where KQL fits:** Azure Data Explorer (Kusto) is the tool a service engineer would use
to interrogate raw telemetry ad hoc ("show me error bursts for this machine in March").
Stretch goal: load telemetry into ADX's free cluster and keep 5–6 saved KQL queries.

---

## 5. Who uses it — three personas, three journeys

Modelled the way the Siemens Customer Service organisation is actually shaped:

**P1 — Service Operations Manager ("Priya", regional dispatch).**
*Monday 8am: "Which machines get my engineers this week?"*
Journey: opens the **Command Center** → reads the KPI band (critical / watch / healthy,
predicted failures) → scans the ranked worklist → filters to her region → assigns the
top risks to engineers. She cares about **precision** — every wasted visit is a day of
an engineer's time — and the **cost panel** that justifies her dispatch decisions.

**P2 — Field Service Engineer ("David", on the road).**
*"I've been assigned FP-MRI-0103 — what am I walking into?"*
Journey: opens the **machine detail page** → sees the telemetry drifting (helium level
falling for 3 weeks) → reads the top risk drivers (SHAP, in plain component language) →
asks the **Copilot** "have we seen this before?" → gets the 3 most similar historical
tickets and the part that fixed them → orders the part before driving out. He cares
about **why**, not the probability — and about not opening the machine blind.

**P3 — Customer Service Director ("Elena", owns the P&L and SLAs).**
*"Is predictive maintenance actually saving us money this quarter?"*
Journey: opens the **executive view** → fleet availability, failures caught early vs
missed, **cost avoided vs inspection spend** (the Business Impact Engine), SLA
performance trend. She cares about one number — **net savings** — and whether the
false-alarm rate is eroding engineer trust.

One build, three altitudes: same scores, rendered as a worklist (P1), an explanation
(P2), and a P&L line (P3).

---

## 6. Module 1 — Fleet Health & Failure Prediction (+ Business Impact Engine)

**Problem statement.** *Rank the fleet by probability of failure in the next 7 days, so
a bounded weekly inspection budget catches the most failures — and price the decision.*

- **Data in:** all six tables → 226 features per machine-week (rolling sensor stats and
  trends over 7/14/30-day windows, error-burst counts, maintenance recency, age, usage).
- **Model:** **XGBoost** classifier + **Platt calibration** (so "0.4" means 40% for
  real). Chosen over deep learning deliberately: tabular data, few positives, native
  missing-value handling, SHAP explainability.
- **Results (test window):** PR-AUC **0.48** vs random 0.013 · recall@20 **0.78** ·
  precision@20 0.23 · median lead time **3 days**. Reported as a worklist a service team
  can act on — never as "accuracy" (at 1.7% prevalence, accuracy is meaningless).
- **Business Impact Engine:** deterministic layer on top of the scores — expected loss
  per machine (risk × downtime days × £27k), cost avoided by the top-20 worklist,
  inspection spend, **net savings** — the numbers P1 defends and P3 reports.
- **Stack:** Python (pandas/PySpark/XGBoost/SHAP) · batch scoring on Databricks →
  Snowflake · frontend: Next.js/React Command Center reading a JSON API contract.
- **Status:** model built, tested, honest metrics in hand; cloud re-run + impact engine
  + dashboard wiring are this sprint's work.

## 7. Module 2 — Telemetry Anomaly Detection (deep learning)

**Problem statement.** *The classifier can only find failure patterns it has labels for.
Catch machines behaving abnormally in ways we've never labelled — the "unknown
unknowns" — and surface them as early warnings.*

- **Data in:** telemetry only (no labels needed — **unsupervised**). Sliding windows of
  per-sensor daily readings, normalised per machine (so a naturally-hot machine isn't
  forever "anomalous").
- **Model:** **Keras/TensorFlow autoencoder** — a neural network trained to compress and
  reconstruct *normal* telemetry; where reconstruction error spikes, the machine has
  left normal behaviour. Benchmarked against the simpler baselines we already have
  (z-score, IsolationForest) — if the autoencoder can't beat them, we say so.
- **Why it earns its place:** closes the JD's explicit Keras/TensorFlow gap with a
  *fitting* use (anomaly detection is the standard autoencoder application in predictive
  maintenance), and feeds the dashboard's "watch" tier between healthy and critical.
- **Stack:** Python/Keras trained offline · anomaly scores land in Snowflake beside the
  failure scores · frontend: anomaly timeline strip on the machine detail page.
- **Status:** not started — the deep-learning build of this sprint.

## 8. Module 3 — Engineer Copilot (RAG + agentic pattern)

**Problem statement.** *A field engineer's best asset is the memory of 49 colleagues'
past repairs — locked in 1,610 free-text tickets with inconsistent shorthand ("He level
low" / "helium lvl dropping" / "cryo issue"). Make it queryable in plain English.*

- **Data in:** ticket notes + failure/repair history + the model's per-machine SHAP
  drivers + small synthetic service-manual snippets.
- **How it works:** **Retrieval-Augmented Generation (RAG) pattern, retrieval-first**:
  ticket text → embeddings → local vector store (**ChromaDB**) → a question like *"why
  is FP-MRI-0103 high risk and what fixed this before?"* retrieves the machine's risk
  drivers **and** the most similar historical tickets, composed into an answer with
  citations. The **agentic** part: the copilot chooses which tools to call (risk lookup,
  ticket search, parts history) before answering — a tool-using agent, kept honest and
  simple. Generation layer (Azure OpenAI) is a documented plug-in point; the deployed
  version is retrieval-only so every answer is traceable to a real ticket.
- **Guardrail that matters in interview:** ticket text is written *after* failures — it
  feeds retrieval, **never** the classifier's features (that would be label leakage).
- **Stack:** Python (sentence-transformers + ChromaDB) · precomputed retrieval index ·
  frontend: chat-style panel on the machine page. **Neo4j knowledge graph** (machine →
  component → failure → ticket → engineer) is the named next step — same data, graph
  queries like "machines with failure patterns similar to FP-MRI-0103" — built in the
  companion `service-graph` project.
- **Status:** not started — planned after Module 2.

---

## 9. The API contract (how frontend talks to backend)

Today the dashboard is **fully static** — precomputed JSON, no server (cheap, secure,
demo-proof). The JSON files *are* the API contract; the FastAPI service version is the
documented production path. Same shapes either way:

| Call | Returns | Used by |
|---|---|---|
| `GET /api/fleet/summary` | KPI band: counts by status, predicted failures, availability | P1, P3 |
| `GET /api/machines?status=critical&sort=risk` | the ranked worklist | P1 |
| `GET /api/machines/{id}` | risk score + SHAP drivers + telemetry + ticket history | P2 |
| `GET /api/impact/weekly` | Business Impact Engine: cost avoided, spend, net savings | P1, P3 |
| `GET /api/anomalies?window=30d` | autoencoder early warnings | P1, P2 |
| `POST /api/copilot/ask` `{machine_id, question}` | answer + cited tickets/drivers | P2 |

---

## 10. Honesty ledger — ran for real vs designed

**Ran for real:** data generation & star schema · PySpark features (local + Databricks
Free) · Parquet zones · XGBoost + calibration + SHAP + leakage tests · Snowflake load +
SQL · Keras autoencoder (this sprint) · ChromaDB retrieval (this sprint) · Next.js
dashboard · GitHub + Actions CI.

**Designed, not run (say so proudly):** Azure Blob + ADF orchestration (mapping
documented; free tiers don't cover it cleanly) · Azure OpenAI generation layer ·
Event Hub streaming · model monitoring in production (PSI/KS drift design) · Neo4j
graph (companion project). *"I know exactly how it lands there, and here's the design"*
beats a hollow claim every time.

---

## 11. Build order (this sprint)

| # | Deliverable | Depends on |
|---|---|---|
| 1 | Business Impact Engine — ✅ computed & exported (`impact.py`; backtest 41/54 caught, net ≈ $2.66M); dashboard panel pending | nothing — scores exist |
| 2 | Databricks: run feature pipeline on Free Edition, screenshot + commit notebook | accounts ✅ (done 2026-07-07) |
| 3 | Snowflake: load features/scores, write the analytical SQL layer | 2 |
| 4 | Module 2: Keras autoencoder + baseline comparison + anomaly export | nothing |
| 5 | Module 3: ChromaDB retrieval index + copilot panel | nothing |
| 6 | Dashboard wiring: worklist, machine page, impact panel, anomaly strip | 1,4,5 |
| 7 | KQL stretch: ADX free cluster + saved queries | nothing |
| 8 | Case-study page + this blueprint as the send-ahead narrative | all |

> Snowflake trial expires ~**2026-08-06** — items 2–3 happen early, with screenshots
> captured as durable evidence.
