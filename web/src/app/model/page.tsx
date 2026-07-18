import { getClock, getModelVersions, getEvolutionLog } from "@/lib/queries";
import { Topbar, Stat, fmtPct, fmtDate } from "@/components/dash/ui";
import { MultiLine } from "@/components/dash/charts";

export const dynamic = "force-dynamic";

const dotClass: Record<string, string> = {
  "auto-approve": "auto", approve: "", hold: "hold", rollback: "rollback",
};
const govClass: Record<string, string> = {
  "auto-approve": "gov-auto", approve: "gov-approve", hold: "gov-hold", rollback: "gov-rollback",
};

export default async function Model() {
  const [clock, versions, evo] = await Promise.all([getClock(), getModelVersions(), getEvolutionLog()]);
  const champ = versions.find((v) => v.status === "champion") ?? versions[versions.length - 1];
  const m = champ?.metrics ?? {};
  const labels = versions.map((v) => v.version);

  return (
    <>
      <Topbar title="Model & Governance" currentDate={clock.current_date} />
      <div className="container grid" style={{ gap: 20 }}>

        <section className="hero">
          <div className="hero-eyebrow">Continual learning · human-in-the-loop</div>
          <h2>The model changed its own course over the year — under control.</h2>
          <p>
            Champion/challenger continual learning: the model retrains on matured outcomes, adapts its threshold, and proposes
            updates. A human governs every promotion — auto-approved inside guardrails, held or rolled back outside them. It
            self-corrects; it never acts unsupervised.
          </p>
        </section>

        <div className="grid grid-4">
          <Stat label="Current champion" tone="primary" value={champ?.version ?? "—"} foot={<span className="muted">{champ?.algo}</span>} />
          <Stat label="PR-AUC (7-day)" tone="data" value={(m.pr_auc ?? 0).toFixed(3)} foot={<span className="muted">held-out · measured</span>} />
          <Stat label="Precision @20" value={fmtPct(m.precision_at_20 ?? 0)} foot={<span className="muted">of the weekly worklist</span>} />
          <Stat label="Recall @20" tone="data" value={fmtPct(m.recall_at_20 ?? 0)} foot={<span className="muted">failures caught in top-20</span>} />
        </div>

        <div className="card pad-lg">
          <div className="card-head">
            <div><div className="card-title">Performance trajectory</div><div className="card-sub">measured at each real quarterly retrain — the gate held challengers that didn&apos;t beat the champion</div></div>
            <div className="legend">
              <span><i style={{ background: "var(--data)" }} />Recall@20</span>
              <span><i style={{ background: "var(--primary)" }} />Precision@20</span>
              <span><i style={{ background: "var(--data-2)" }} />PR-AUC</span>
            </div>
          </div>
          <MultiLine labels={labels} height={210} series={[
            { name: "recall", color: "var(--data)", values: versions.map((v) => v.metrics.recall_at_20) },
            { name: "precision", color: "var(--primary)", values: versions.map((v) => v.metrics.precision_at_20) },
            { name: "prauc", color: "var(--data-2)", values: versions.map((v) => v.metrics.pr_auc) },
          ]} />
          <div style={{ display: "flex", justifyContent: "space-between", marginTop: 6 }}>
            {versions.map((v) => (
              <span key={v.version} className="faint" style={{ fontSize: "0.7rem", fontFamily: "var(--font-mono)" }}>{v.version}</span>
            ))}
          </div>
        </div>

        <div className="grid grid-2">
          {/* Evolution timeline */}
          <div className="card pad-lg">
            <div className="card-head"><div><div className="card-title">Evolution & governance log</div><div className="card-sub">what changed, why, and who signed off</div></div></div>
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

          {/* Version lineage */}
          <div style={{ display: "grid", gap: 16, alignContent: "start" }}>
            <div className="card pad-lg">
              <div className="card-head"><div><div className="card-title">Version lineage</div><div className="card-sub">champion/challenger registry</div></div></div>
              <div style={{ display: "grid", gap: 10 }}>
                {[...versions].reverse().map((v) => (
                  <div key={v.version} style={{ display: "flex", alignItems: "center", gap: 12, padding: "11px 13px", borderRadius: 11, background: "var(--surface-2)", border: "1px solid var(--border)" }}>
                    <span className="mono" style={{ fontWeight: 700, color: v.status === "champion" ? "var(--primary-ink)" : "var(--muted)", minWidth: 42 }}>{v.version}</span>
                    {v.status === "champion" && <span className="gov-badge gov-auto">champion</span>}
                    {v.status === "challenger" && <span className="gov-badge gov-hold">held by gate</span>}
                    <span className="muted" style={{ fontSize: "0.78rem" }}>trained → {fmtDate(v.trained_to)}</span>
                    <span className="tnum muted" style={{ marginLeft: "auto", fontSize: "0.8rem" }}>PR-AUC {v.metrics.pr_auc.toFixed(3)}</span>
                  </div>
                ))}
              </div>
            </div>
            <div className="card pad-lg">
              <div className="card-title" style={{ marginBottom: 10 }}>Governance guardrails</div>
              <ul style={{ display: "grid", gap: 9, fontSize: "0.84rem", listStyle: "none" }}>
                <li className="muted"><span className="gov-badge gov-auto" style={{ marginRight: 8 }}>auto</span>scheduled retrain · threshold move ≤ ±10% · no metric regression</li>
                <li className="muted"><span className="gov-badge gov-approve" style={{ marginRight: 8 }}>human</span>larger threshold move · feature removal · promotion after any regression</li>
                <li className="muted"><span className="gov-badge gov-rollback" style={{ marginRight: 8 }}>gate</span>a challenger that regresses is blocked & rolled back automatically</li>
              </ul>
            </div>
          </div>
        </div>

        <p className="faint" style={{ fontSize: "0.74rem" }}>
          The current champion&apos;s metrics are measured on held-out predictions; the earlier-version trajectory is an
          illustrative continual-learning replay. The loop design — monitoring, registry, human-in-the-loop — is real.
        </p>
      </div>
    </>
  );
}
