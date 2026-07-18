import { getClock, getFleetSummary, getEconomicsSeries, getAssumptions } from "@/lib/queries";
import { Topbar, Stat, fmtMoney, fmtNum, fmtPct, fmtDate } from "@/components/dash/ui";
import { AreaChart } from "@/components/dash/charts";

export const dynamic = "force-dynamic";

export default async function Economics() {
  const [clock, s, econ, a] = await Promise.all([
    getClock(), getFleetSummary(), getEconomicsSeries(), getAssumptions(),
  ]);
  const avoided = econ.reduce((t, e) => t + (e.downtime_days_avoided || 0), 0);
  const dispatched = s.caught + s.false_alarm;
  const programCost = dispatched * (a.proactive_visit_cost ?? 800);
  const roi = programCost > 0 ? s.cumulative_net_savings / programCost : 0;

  return (
    <>
      <Topbar title="Economics" currentDate={clock.current_date} />
      <div className="container grid" style={{ gap: 20 }}>

        <section className="hero">
          <div className="hero-eyebrow">Business case · 12 months</div>
          <h2>The model pays for the whole service program, many times over.</h2>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 44, marginTop: 24, alignItems: "flex-end" }}>
            <div>
              <div className="hero-figure">{fmtMoney(s.cumulative_net_savings)}</div>
              <div className="muted" style={{ fontSize: "0.82rem", marginTop: 8 }}>net saved vs. reactive maintenance</div>
            </div>
            <div style={{ display: "flex", gap: 32 }}>
              <div><div className="stat-value sm accent-primary">{roi.toFixed(0)}×</div><div className="muted" style={{ fontSize: "0.78rem", marginTop: 6 }}>return on inspection spend</div></div>
              <div><div className="stat-value sm">{fmtNum(Math.round(avoided))}</div><div className="muted" style={{ fontSize: "0.78rem", marginTop: 6 }}>downtime days avoided</div></div>
            </div>
          </div>
        </section>

        <div className="grid grid-4">
          <Stat label="Net saved" tone="data" value={fmtMoney(s.cumulative_net_savings)} foot={<span className="muted">after inspection cost</span>} />
          <Stat label="Program cost" value={fmtMoney(programCost)} foot={<span className="muted">{fmtNum(dispatched)} inspections × ${a.proactive_visit_cost ?? 800}</span>} />
          <Stat label="Downtime avoided" value={`${fmtNum(Math.round(avoided))} days`} foot={<span className="muted">@ {fmtMoney(a.downtime_cost_per_day ?? 27000)}/day</span>} />
          <Stat label="Return on spend" tone="primary" value={`${roi.toFixed(0)}×`} foot={<span className="muted">savings ÷ program cost</span>} />
        </div>

        <div className="card pad-lg">
          <div className="card-head">
            <div><div className="card-title">Cumulative net savings</div><div className="card-sub">the running total the program has banked</div></div>
          </div>
          <AreaChart id="econ-cum" height={180} color="var(--data)" values={econ.map((e) => e.cumulative_net_savings)} />
          <div style={{ display: "flex", justifyContent: "space-between", marginTop: 8 }} className="faint">
            <span style={{ fontSize: "0.7rem" }}>{econ[0] && fmtDate(econ[0].as_of_date)}</span>
            <span style={{ fontSize: "0.7rem" }}>{econ[econ.length - 1] && fmtDate(econ[econ.length - 1].as_of_date)}</span>
          </div>
        </div>

        <div className="grid grid-2">
          <div className="card pad-lg">
            <div className="card-head"><div><div className="card-title">Weekly value captured</div><div className="card-sub">net savings per worklist</div></div></div>
            <AreaChart id="econ-weekly" height={150} color="var(--primary)" values={econ.map((e) => e.worklist_net_savings)} />
          </div>

          <div className="card pad-lg">
            <div className="card-head"><div><div className="card-title">Assumptions ledger</div><div className="card-sub">every number traces back to these — shown openly</div></div></div>
            <div style={{ display: "grid", gap: 0 }}>
              {[
                ["Unplanned downtime", fmtMoney(a.downtime_cost_per_day ?? 27000) + " / day", "lost scanning revenue"],
                ["Proactive visit", fmtMoney(a.proactive_visit_cost ?? 800), "planned inspection / pre-emptive repair"],
                ["Planned downtime", (a.planned_downtime_days ?? 0.5) + " days", "when a failure is caught early"],
                ["Weekly worklist", (a.worklist_k ?? 20) + " machines", "inspections the team can action"],
              ].map(([k, v, d], i) => (
                <div key={i} style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", padding: "12px 0", borderBottom: i < 3 ? "1px solid var(--border)" : "none" }}>
                  <div><div style={{ fontWeight: 550, fontSize: "0.88rem" }}>{k}</div><div className="muted" style={{ fontSize: "0.76rem" }}>{d}</div></div>
                  <div className="tnum" style={{ fontWeight: 700 }}>{v}</div>
                </div>
              ))}
            </div>
            <p className="faint" style={{ fontSize: "0.74rem", marginTop: 14 }}>
              Order-of-magnitude and synthetic. A caught failure converts unplanned downtime into a short planned visit;
              savings = avoided unplanned downtime − the visit cost.
            </p>
          </div>
        </div>
      </div>
    </>
  );
}
