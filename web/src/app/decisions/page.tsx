import { getClock, getFleetSummary, getEconomicsSeries, getRecentDecisions, getWorklist, band } from "@/lib/queries";
import { Topbar, Stat, Pill, fmtMoney, fmtNum, fmtPct, fmtDate } from "@/components/dash/ui";
import { AreaChart } from "@/components/dash/charts";

export const dynamic = "force-dynamic";

const outcomeClass: Record<string, string> = {
  caught: "gov-approve", false_alarm: "gov-hold", missed: "gov-rollback", pending: "chip",
};

export default async function Decisions() {
  const [clock, s, econ, resolved, upcoming] = await Promise.all([
    getClock(), getFleetSummary(), getEconomicsSeries(), getRecentDecisions(24, true), getWorklist(20),
  ]);
  const dispatched = s.caught + s.false_alarm;

  return (
    <>
      <Topbar title="Decisions" currentDate={clock.current_date} />
      <div className="container grid" style={{ gap: 20 }}>

        <div className="grid grid-4">
          <Stat label="Failures caught" tone="data" value={fmtNum(s.caught)} foot={<span className="muted">proactive interventions</span>} />
          <Stat label="Missed" value={<span style={{ color: "var(--critical)" }}>{s.missed}</span>} foot={<span className="muted">{fmtPct(s.detection_rate)} detection rate</span>} />
          <Stat label="False alarms" value={<span style={{ color: "var(--watch)" }}>{fmtNum(s.false_alarm)}</span>} foot={<span className="muted">@ $800 each — cheap insurance</span>} />
          <Stat label="Net saved" tone="data" value={fmtMoney(s.cumulative_net_savings)} foot={<span className="muted">vs. reactive, 12 months</span>} />
        </div>

        <div className="card pad-lg">
          <div className="card-head">
            <div><div className="card-title">Cumulative net savings</div><div className="card-sub">what the decisions have banked, week by week</div></div>
            <div className="chip">{dispatched} inspections dispatched</div>
          </div>
          <AreaChart id="dec-cum" height={170} color="var(--data)" values={econ.map((e) => e.cumulative_net_savings)} />
          <div style={{ display: "flex", justifyContent: "space-between", marginTop: 8 }} className="faint">
            <span style={{ fontSize: "0.7rem" }}>{econ[0] && fmtDate(econ[0].as_of_date)}</span>
            <span style={{ fontSize: "0.7rem" }}>{econ[econ.length - 1] && fmtDate(econ[econ.length - 1].as_of_date)}</span>
          </div>
        </div>

        <div className="grid grid-2">
          {/* Past decisions */}
          <div className="card pad-lg">
            <div className="card-head">
              <div><div className="card-title">Decisions taken</div><div className="card-sub">resolved against what actually happened</div></div>
            </div>
            <div className="tbl-wrap">
              <table className="tbl">
                <thead><tr><th>Week</th><th>Machine</th><th className="num">Risk</th><th>Outcome</th></tr></thead>
                <tbody>
                  {resolved.map((d, i) => (
                    <tr key={i}>
                      <td className="muted" style={{ whiteSpace: "nowrap" }}>{fmtDate(d.as_of_date)}</td>
                      <td className="mono">{d.machine_id}<span className="tag-mod" style={{ marginLeft: 8 }}>{d.modality}</span></td>
                      <td className="num tnum">{fmtPct(d.risk_score, 0)}</td>
                      <td><span className={`gov-badge ${outcomeClass[d.outcome] ?? "chip"}`}>{d.outcome.replace("_", " ")}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Upcoming worklist */}
          <div className="card pad-lg">
            <div className="card-head">
              <div><div className="card-title">This week&apos;s worklist</div><div className="card-sub">dispatch now — top-20 by 7-day risk</div></div>
              <div className="chip">pending</div>
            </div>
            <div className="tbl-wrap">
              <table className="tbl">
                <thead><tr><th>#</th><th>Machine</th><th>Site</th><th className="num">7-day</th><th></th></tr></thead>
                <tbody>
                  {upcoming.map((m, i) => (
                    <tr key={m.machine_id}>
                      <td className="faint tnum">{i + 1}</td>
                      <td className="mono">{m.machine_id}</td>
                      <td className="muted" style={{ maxWidth: 140, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{m.hospital_name}</td>
                      <td className="num tnum" style={{ fontWeight: 700 }}>{fmtPct(m.p7)}</td>
                      <td><Pill band={band(m.p7)} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>

        <p className="faint" style={{ fontSize: "0.74rem" }}>
          Outcomes are resolved by checking whether each dispatched machine actually failed within its horizon. A false alarm
          costs one inspection (~$800); a missed failure costs unplanned downtime (~$27k/day) — the worklist is tuned to that asymmetry.
        </p>
      </div>
    </>
  );
}
