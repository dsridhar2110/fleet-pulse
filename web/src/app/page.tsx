import { getClock, getModelVersions, getEvolutionLog, getModelCard } from "@/lib/queries";
import { Topbar, Stat, fmtPct, fmtDate } from "@/components/dash/ui";
import { MultiLine } from "@/components/dash/charts";
import { Info, MethodStrip } from "@/components/dash/info";

export const dynamic = "force-dynamic";

const dotClass: Record<string, string> = { "auto-approve": "auto", approve: "", hold: "hold", rollback: "rollback" };
const govClass: Record<string, string> = { "auto-approve": "gov-auto", approve: "gov-approve", hold: "gov-hold", rollback: "gov-rollback" };

export default async function Home() {
  const [clock, versions, evo, card] = await Promise.all([
    getClock(), getModelVersions(), getEvolutionLog(), getModelCard(),
  ]);
  const champ = versions.find((v) => v.status === "champion") ?? versions[versions.length - 1];
  const m = card?.metrics ?? { pr_auc_7d: 0, precision_at_20: 0, recall_at_20: 0, prevalence_7d: 0.008 };
  const labels = versions.map((v) => v.version);
  const anom = card?.modules?.m2?.benchmark ?? {};
  const ret = card?.modules?.m3?.metrics ?? {};

  return (
    <>
      <Topbar title="Model & Governance" currentDate={clock.current_date} />
      <div className="container grid" style={{ gap: 20 }}>

        <section className="hero">
          <div className="hero-eyebrow">Model card · continual learning · human-in-the-loop</div>
          <h2>The thinking behind Fleet Pulse.</h2>
          <p>
            Three modules — a supervised failure model, an unsupervised anomaly signal, and a retrieval
            copilot — under a governed champion/challenger loop. {card?.built}
          </p>
        </section>

        {/* Model card: canonical metrics with DS rationale on hover */}
        <div className="grid grid-4">
          <Stat label="Current champion" tone="primary" value={champ?.version ?? "—"} foot={<span className="muted">{champ?.algo} · trained {champ && fmtDate(champ.trained_to)}</span>} />
          <div className="card">
            <div className="stat-label" style={{ display: "flex", alignItems: "center", gap: 6 }}>PR-AUC (7-day) <Info text="Area under precision–recall. Chosen over ROC-AUC because at ~0.8% failure prevalence ROC-AUC is flattering; PR-AUC reflects performance on the rare positive class. Random baseline ≈ prevalence." /></div>
            <div className="stat-value accent-data">{m.pr_auc_7d.toFixed(3)}</div>
            <div className="stat-foot muted">vs ~{m.prevalence_7d} random · held-out</div>
          </div>
          <div className="card">
            <div className="stat-label" style={{ display: "flex", alignItems: "center", gap: 6 }}>Precision@20 <Info text="Of the 20 machines the team can inspect each week, the fraction that were genuine failures. A fixed-capacity metric — it matches how the service team actually works." /></div>
            <div className="stat-value">{fmtPct(m.precision_at_20)}</div>
            <div className="stat-foot muted">of the weekly worklist</div>
          </div>
          <div className="card">
            <div className="stat-label" style={{ display: "flex", alignItems: "center", gap: 6 }}>Recall@20 <Info text="Of all failures that occurred in a week, the fraction captured in the top-20 worklist. This is the number the operating point is tuned to maximise — catching failures matters more than avoiding false alarms." /></div>
            <div className="stat-value accent-data">{fmtPct(m.recall_at_20)}</div>
            <div className="stat-foot muted">failures caught in top-20</div>
          </div>
        </div>

        <MethodStrip label="TRADE-OFF">{card?.tradeoff}</MethodStrip>

        {/* The three modules */}
        <div>
          <div className="eyebrow" style={{ marginBottom: 10 }}>The three modules</div>
          <div className="grid grid-3">
            <div className="card pad-lg" style={{ borderTop: "3px solid var(--primary)" }}>
              <div className="chip" style={{ marginBottom: 10 }}>Module 1</div>
              <div className="card-title">{card?.modules?.m1?.name}</div>
              <p className="muted" style={{ fontSize: "0.84rem", margin: "8px 0 12px" }}>{card?.modules?.m1?.method}</p>
              <MethodStrip label="FEATURES">{card?.modules?.m1?.features}</MethodStrip>
              <div style={{ height: 8 }} />
              <MethodStrip label="VALIDATION">{card?.modules?.m1?.validation}</MethodStrip>
            </div>
            <div className="card pad-lg" style={{ borderTop: "3px solid var(--data)" }}>
              <div className="chip" style={{ marginBottom: 10 }}>Module 2</div>
              <div className="card-title">{card?.modules?.m2?.name}</div>
              <p className="muted" style={{ fontSize: "0.84rem", margin: "8px 0 12px" }}>
                Three detectors benchmarked on the fleet (PR-AUC). We ship the interpretable winner.
              </p>
              <div style={{ display: "grid", gap: 7 }}>
                {[["z-score alarm", anom.z_score_alarm, true], ["IsolationForest", anom.isolation_forest, false], ["autoencoder (196→16)", anom.linear_autoencoder_pca, false]].map(([k, v, ship]) => (
                  <div key={k as string} style={{ display: "flex", alignItems: "center", gap: 10, fontSize: "0.84rem" }}>
                    <span style={{ minWidth: 150 }} className={ship ? "" : "muted"}>{k as string}{ship ? " · shipped" : ""}</span>
                    <div className="bar-track" style={{ flex: 1 }}><div className={`bar-fill ${ship ? "ok" : ""}`} style={{ width: `${Math.min(100, (v as number) / 0.06 * 100)}%` }} /></div>
                    <span className="tnum" style={{ fontWeight: 700, minWidth: 42, textAlign: "right" }}>{(v as number)?.toFixed(3)}</span>
                  </div>
                ))}
              </div>
              <p className="faint" style={{ fontSize: "0.76rem", marginTop: 10 }}>{anom.note}</p>
            </div>
            <div className="card pad-lg" style={{ borderTop: "3px solid var(--data-3)" }}>
              <div className="chip" style={{ marginBottom: 10 }}>Module 3</div>
              <div className="card-title">{card?.modules?.m3?.name}</div>
              <p className="muted" style={{ fontSize: "0.84rem", margin: "8px 0 12px" }}>{ret.vectorizer} + cosine over {ret.n_tickets} tickets. No LLM.</p>
              <div style={{ display: "flex", gap: 22, margin: "4px 0 12px" }}>
                <div><div className="stat-value sm accent-data">{fmtPct(ret.precision_at_1 ?? 0)}</div><div className="faint" style={{ fontSize: "0.72rem" }}>P@1 (component match)</div></div>
                <div><div className="stat-value sm">{fmtPct(ret.majority_baseline ?? 0)}</div><div className="faint" style={{ fontSize: "0.72rem" }}>majority baseline</div></div>
              </div>
              <p className="faint" style={{ fontSize: "0.76rem" }}>{ret.note}</p>
            </div>
          </div>
        </div>

        {/* Performance trajectory */}
        <div className="card pad-lg">
          <div className="card-head">
            <div><div className="card-title">Performance trajectory</div><div className="card-sub">measured at each real quarterly retrain — the gate held challengers that didn&apos;t beat the champion</div></div>
            <div className="legend">
              <span><i style={{ background: "var(--data)" }} />Recall@20</span>
              <span><i style={{ background: "var(--primary)" }} />Precision@20</span>
              <span><i style={{ background: "var(--data-2)" }} />PR-AUC</span>
            </div>
          </div>
          <MultiLine labels={labels} height={200} series={[
            { name: "recall", color: "var(--data)", values: versions.map((v) => v.metrics.recall_at_20) },
            { name: "precision", color: "var(--primary)", values: versions.map((v) => v.metrics.precision_at_20) },
            { name: "prauc", color: "var(--data-2)", values: versions.map((v) => v.metrics.pr_auc) },
          ]} />
          <div style={{ display: "flex", justifyContent: "space-between", marginTop: 6 }}>
            {versions.map((v) => <span key={v.version} className="faint" style={{ fontSize: "0.7rem", fontFamily: "var(--font-mono)" }}>{v.version}</span>)}
          </div>
        </div>

        {/* Evolution timeline + lineage */}
        <div className="grid grid-2">
          <div className="card pad-lg">
            <div className="card-head"><div><div className="card-title">Model registry &amp; governance log</div><div className="card-sub">champion/challenger lineage — what changed, why, who signed off</div></div></div>
            <div className="timeline">
              {[...evo].reverse().map((e) => (
                <div className="tl-item" key={e.id}>
                  <span className={`tl-dot ${dotClass[e.action] ?? ""}`} />
                  <div className="tl-date">{fmtDate(e.ts)} · {e.trigger.replace(/_/g, " ")}</div>
                  <div className="tl-title">{e.event_type.replace(/_/g, " ")} {e.version && <span className="mono faint" style={{ fontWeight: 400 }}>→ {e.version}</span>}</div>
                  <div className="tl-note">{e.note}</div>
                  {e.action && (
                    <div className="gov">
                      <span className={`gov-badge ${govClass[e.action] ?? "chip"}`}>{e.action}</span>
                      <span className="muted">{e.rationale} <span className="faint">— {e.actor_role}</span></span>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>

          <div style={{ display: "grid", gap: 16, alignContent: "start" }}>
            <div className="card pad-lg">
              <div className="card-head"><div><div className="card-title">Version registry</div><div className="card-sub">stage · lineage · metric</div></div></div>
              <div style={{ display: "grid", gap: 10 }}>
                {[...versions].reverse().map((v) => (
                  <div key={v.version} style={{ display: "flex", alignItems: "center", gap: 12, padding: "11px 13px", borderRadius: 11, background: "var(--surface-2)", border: "1px solid var(--border)" }}>
                    <span className="mono" style={{ fontWeight: 700, color: v.status === "champion" ? "var(--primary-ink)" : "var(--muted)", minWidth: 42 }}>{v.version}</span>
                    {v.status === "champion" && <span className="gov-badge gov-auto">champion</span>}
                    {v.status === "challenger" && <span className="gov-badge gov-hold">held by gate</span>}
                    <span className="muted" style={{ fontSize: "0.78rem" }}>{fmtDate(v.trained_to)}</span>
                    <span className="tnum muted" style={{ marginLeft: "auto", fontSize: "0.8rem" }}>PR-AUC {v.metrics.pr_auc.toFixed(3)}</span>
                  </div>
                ))}
              </div>
            </div>
            <div className="card pad-lg">
              <div className="card-title" style={{ marginBottom: 6 }}>Monitoring &amp; guardrails</div>
              <p className="muted" style={{ fontSize: "0.8rem", marginBottom: 10 }}>Because outcomes mature daily, monitoring is a working loop — not slideware.</p>
              <ul style={{ display: "grid", gap: 9, fontSize: "0.82rem", listStyle: "none" }}>
                <li className="muted"><b style={{ color: "var(--text)" }}>Drift:</b> PSI / KS on features, calibration drift → retrain trigger</li>
                <li className="muted"><span className="gov-badge gov-auto" style={{ marginRight: 8 }}>auto</span>scheduled retrain · threshold ≤ ±10% · no metric regression</li>
                <li className="muted"><span className="gov-badge gov-approve" style={{ marginRight: 8 }}>human</span>bigger threshold move · feature removal · promotion after any regression</li>
                <li className="muted"><span className="gov-badge gov-rollback" style={{ marginRight: 8 }}>gate</span>a challenger that doesn&apos;t beat the champion is blocked &amp; rolled back</li>
              </ul>
            </div>
          </div>
        </div>

        <p className="faint" style={{ fontSize: "0.74rem" }}>
          Metrics are the champion&apos;s held-out numbers (single source of truth). Independent portfolio project · all data synthetic.
        </p>
      </div>
    </>
  );
}
