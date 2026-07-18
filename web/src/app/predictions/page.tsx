import { getClock, getWorklist, getFleetSummary } from "@/lib/queries";
import { Topbar, Stat, fmtNum, fmtPct } from "@/components/dash/ui";
import { WorklistTable } from "@/components/dash/worklist-table";

export const dynamic = "force-dynamic";

export default async function Predictions() {
  const [clock, rows, s] = await Promise.all([getClock(), getWorklist(500), getFleetSummary()]);
  return (
    <>
      <Topbar title="Predictions" currentDate={clock.current_date} />
      <div className="container grid" style={{ gap: 20 }}>
        <div className="grid grid-4">
          <Stat label="Machines scored" value={fmtNum(rows.length)} foot={<span className="muted">every day, all horizons</span>} />
          <Stat label="Critical (7-day)" value={<span style={{ color: "var(--critical)" }}>{s.critical}</span>} foot={<span className="muted">act this week</span>} />
          <Stat label="On watch" value={<span style={{ color: "var(--watch)" }}>{s.watch}</span>} foot={<span className="muted">trending up</span>} />
          <Stat label="Model recall @20" tone="data" value={fmtPct(0.866)} foot={<span className="muted">7-day, held-out</span>} />
        </div>

        <div className="card" style={{ padding: 18, display: "flex", gap: 18, flexWrap: "wrap", alignItems: "center" }}>
          <div style={{ fontSize: "0.84rem" }} className="muted">
            <b style={{ color: "var(--text)" }}>How to read this:</b> two models compose one survival curve per machine —
            XGBoost drives the 7 &amp; 14-day operational alerts; an XGBoost-AFT survival model drives the 30 / 90 / 180-day
            planning horizons. Probabilities are monotone (risk only accumulates over longer windows).
          </div>
        </div>

        <WorklistTable rows={rows} />

        <p className="faint" style={{ fontSize: "0.74rem" }}>
          Risk bands: critical ≥ {fmtPct(0.15)} · watch ≥ {fmtPct(0.05)} on the 7-day probability. Synthetic data.
        </p>
      </div>
    </>
  );
}
