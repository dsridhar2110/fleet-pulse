import { getClock, getFleetSummary, getHealthTrend, getWorklist, getEvolutionLog, band } from "@/lib/queries";
import { Topbar, Stat, Pill, fmtMoney, fmtNum, fmtPct } from "@/components/dash/ui";
import { Donut, StackedArea, Spark } from "@/components/dash/charts";
import Link from "next/link";
import { ArrowUpRight, ShieldCheck } from "lucide-react";

export const dynamic = "force-dynamic";

export default async function Overview() {
  const [clock, s, trend, worklist, evo] = await Promise.all([
    getClock(), getFleetSummary(), getHealthTrend(), getWorklist(6), getEvolutionLog(),
  ]);
  const gov = evo.slice(-3).reverse();

  return (
    <>
      <Topbar title="Overview" currentDate={clock.current_date} />
      <div className="container grid" style={{ gap: 20 }}>

        <section className="hero">
          <div className="hero-eyebrow"><ShieldCheck size={14} /> 12 months live · continual learning under governance</div>
          <h2>Every scanner in the fleet, watched every single day.</h2>
          <p>
            A model scores {fmtNum(s.machines)} imaging machines across {fmtNum(s.customers)} customers for failure risk over
            five horizons, turns that risk into a weekly service worklist, and learns from what actually happens — with a
            human as the governor.
          </p>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 40, marginTop: 26, alignItems: "flex-end" }}>
            <div>
              <div className="hero-figure">{fmtMoney(s.cumulative_net_savings)}</div>
              <div className="muted" style={{ fontSize: "0.82rem", marginTop: 8 }}>net saved vs. doing nothing · last 12 months</div>
            </div>
            <div style={{ display: "flex", gap: 32 }}>
              <div>
                <div className="stat-value sm accent-data">{fmtPct(s.detection_rate)}</div>
                <div className="muted" style={{ fontSize: "0.78rem", marginTop: 6 }}>of failures caught</div>
              </div>
              <div>
                <div className="stat-value sm">{fmtNum(s.caught)}</div>
                <div className="muted" style={{ fontSize: "0.78rem", marginTop: 6 }}>proactive catches</div>
              </div>
            </div>
          </div>
        </section>

        <div className="grid grid-4">
          <Stat label="Machines under management" value={fmtNum(s.machines)}
            foot={<span className="delta-up"><ArrowUpRight size={13} /> +{s.new_this_month} onboarded this quarter</span>} />
          <Stat label="Critical now" value={<span style={{ color: "var(--critical)" }}>{s.critical}</span>}
            foot={<span className="muted">{s.watch} on watch · {fmtNum(s.healthy)} healthy</span>} />
          <Stat label="Fleet risk this week" value={fmtMoney(s.fleet_expected_loss)}
            foot={<span className="muted">expected downtime loss if unmanaged</span>} />
          <Stat label="Detection rate" tone="data" value={fmtPct(s.detection_rate)}
            foot={<span className="muted">{s.caught} caught · {s.missed} missed</span>} />
        </div>

        <div className="grid grid-2">
          <div className="card pad-lg">
            <div className="card-head">
              <div><div className="card-title">Fleet health, right now</div><div className="card-sub">7-day failure-risk bands</div></div>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 26, flexWrap: "wrap" }}>
              <Donut size={168} label={fmtNum(s.machines)} sub="machines"
                items={[
                  { value: s.critical, color: "var(--critical)" },
                  { value: s.watch, color: "var(--watch)" },
                  { value: s.healthy, color: "var(--healthy)" },
                ]} />
              <div style={{ display: "grid", gap: 12, flex: 1, minWidth: 160 }}>
                {[
                  { k: "Critical", v: s.critical, c: "var(--critical)", d: "inspect this week" },
                  { k: "Watch", v: s.watch, c: "var(--watch)", d: "trending up" },
                  { k: "Healthy", v: s.healthy, c: "var(--healthy)", d: "nominal" },
                ].map((r) => (
                  <div key={r.k} style={{ display: "flex", alignItems: "center", gap: 10 }}>
                    <i style={{ width: 10, height: 10, borderRadius: 3, background: r.c }} />
                    <span style={{ fontWeight: 600, minWidth: 66 }}>{r.k}</span>
                    <span className="tnum" style={{ fontWeight: 700 }}>{fmtNum(r.v)}</span>
                    <span className="muted" style={{ fontSize: "0.78rem", marginLeft: "auto" }}>{r.d}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div className="card pad-lg">
            <div className="card-head">
              <div><div className="card-title">Fleet health over time</div><div className="card-sub">machines by risk band, weekly</div></div>
              <div className="legend">
                <span><i style={{ background: "var(--healthy)" }} />Healthy</span>
                <span><i style={{ background: "var(--watch)" }} />Watch</span>
                <span><i style={{ background: "var(--critical)" }} />Critical</span>
              </div>
            </div>
            <StackedArea height={188} series={[
              { name: "healthy", color: "var(--healthy)", values: trend.map((t) => t.healthy) },
              { name: "watch", color: "var(--watch)", values: trend.map((t) => t.watch) },
              { name: "critical", color: "var(--critical)", values: trend.map((t) => t.critical) },
            ]} />
            <div style={{ display: "flex", justifyContent: "space-between", marginTop: 8 }} className="faint">
              <span style={{ fontSize: "0.7rem" }}>{trend[0]?.as_of_date.slice(0, 7)}</span>
              <span style={{ fontSize: "0.7rem" }}>{trend[trend.length - 1]?.as_of_date.slice(0, 7)}</span>
            </div>
          </div>
        </div>

        <div className="grid grid-2">
          <div className="card pad-lg">
            <div className="card-head">
              <div><div className="card-title">Highest risk this week</div><div className="card-sub">top of the service worklist</div></div>
              <Link href="/predictions" className="link">View all →</Link>
            </div>
            <div className="tbl-wrap">
              <table className="tbl">
                <thead><tr><th>Machine</th><th>Site</th><th>Survival curve</th><th className="num">7-day</th><th></th></tr></thead>
                <tbody>
                  {worklist.map((m) => (
                    <tr key={m.machine_id}>
                      <td className="mono"><Link href={`/machines/${m.machine_id}`} className="mlink">{m.machine_id}</Link></td>
                      <td style={{ maxWidth: 150, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }} className="muted">{m.hospital_name}</td>
                      <td><Spark values={[m.p7, m.p14, m.p30, m.p90, m.p180]} color={band(m.p7) === "critical" ? "var(--critical)" : "var(--watch)"} /></td>
                      <td className="num tnum" style={{ fontWeight: 700 }}>{fmtPct(m.p7)}</td>
                      <td><Pill band={band(m.p7)} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="card pad-lg">
            <div className="card-head">
              <div><div className="card-title">Model activity</div><div className="card-sub">recent learning & governance</div></div>
              <Link href="/" className="link">History →</Link>
            </div>
            <div style={{ display: "grid", gap: 12 }}>
              {gov.map((e) => (
                <div key={e.id} style={{ display: "flex", gap: 12, alignItems: "flex-start" }}>
                  <span className={`gov-badge ${e.action === "auto-approve" ? "gov-auto" : e.action === "approve" ? "gov-approve" : "gov-hold"}`}>{e.action}</span>
                  <div>
                    <div style={{ fontSize: "0.86rem", fontWeight: 550 }}>{e.event_type.replace(/_/g, " ").toLowerCase()}</div>
                    <div className="muted" style={{ fontSize: "0.78rem", marginTop: 2 }}>{e.note}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        <p className="faint" style={{ fontSize: "0.74rem", textAlign: "center", marginTop: 8 }}>
          Independent interview-prep project · all data synthetic · not affiliated with, endorsed by, or built on data from any manufacturer.
        </p>
      </div>
    </>
  );
}
