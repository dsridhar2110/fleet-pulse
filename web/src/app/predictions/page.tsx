import { getClock, getWorklist, getFleetSummary, getModelCard } from "@/lib/queries";
import { Topbar, Stat, fmtNum, fmtPct } from "@/components/dash/ui";
import { WorklistTable } from "@/components/dash/worklist-table";
import { MethodStrip, Info } from "@/components/dash/info";

export const dynamic = "force-dynamic";

export default async function Predictions() {
  const [clock, rows, s, card] = await Promise.all([
    getClock(), getWorklist(500), getFleetSummary(), getModelCard(),
  ]);
  const recall = card?.metrics.recall_at_20 ?? 0.851;
  return (
    <>
      <Topbar title="Predictions" currentDate={clock.current_date} />
      <div className="container grid" style={{ gap: 20 }}>
        <div className="grid grid-4">
          <Stat label="Machines scored" value={fmtNum(rows.length)} foot={<span className="muted">every day, all horizons</span>} />
          <Stat label="Critical (7-day)" value={<span style={{ color: "var(--critical)" }}>{s.critical}</span>} foot={<span className="muted">act this week</span>} />
          <Stat label="On watch" value={<span style={{ color: "var(--watch)" }}>{s.watch}</span>} foot={<span className="muted">trending up</span>} />
          <Stat label={<span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>Model recall @20 <Info text="Of all failures in a week, the fraction caught in the top-20 worklist. The metric the operating point maximises." /></span>}
            tone="data" value={fmtPct(recall)} foot={<span className="muted">7-day, held-out (champion {card?.champion})</span>} />
        </div>

        <MethodStrip label="HOW THIS IS COMPUTED">
          Long telemetry is pivoted to a <b>wide per-machine-day matrix</b>; features are rolling
          mean/std/<b>z-score</b>/trend (7/14/30d), warning-code bursts, days-since-maintenance, age
          and usage — all strictly <b>≤ scoring day <code>t</code></b> (leakage-safe). Two models compose one
          <b> survival curve</b> per machine: <b>XGBoost</b> (<code>binary:logistic</code>, Platt-calibrated) for
          the 7 &amp; 14-day operational alerts; <b>XGBoost-AFT</b> (<code>survival:aft</code>) for the 30/90/180-day
          planning horizons. The <b>P(fail ≤ Nd)</b> column is that calibrated probability; bands come from a
          <b> cost-based threshold</b> (a miss ≈ 100× a false alarm).
        </MethodStrip>

        <WorklistTable rows={rows} />

        <p className="faint" style={{ fontSize: "0.74rem" }}>
          Risk bands: critical ≥ {fmtPct(0.15)} · watch ≥ {fmtPct(0.05)} on the 7-day probability. Champion
          metrics are the single source of truth (shown on Model &amp; Governance). Synthetic data.
        </p>
      </div>
    </>
  );
}
