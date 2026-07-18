import { notFound } from "next/navigation";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import {
  getClock, getMachine, getMachineTelemetry, getMachineRiskHistory,
  getMachineTickets, getMachineEvents, KEY_SENSORS,
} from "@/lib/queries";
import { band } from "@/lib/risk";
import { Topbar, Pill, fmtPct, fmtDate, fmtNum } from "@/components/dash/ui";
import { AreaChart, Spark } from "@/components/dash/charts";

export const dynamic = "force-dynamic";

const SENSOR_LABEL: Record<string, string> = {
  helium_level: "Helium level (%)", compressor_temp: "Compressor temp (°C)", vibration_rms: "Vibration (mm/s)",
  tube_current_var: "Tube current var", tube_temp: "Tube temp (°C)", gantry_vibration: "Gantry vibration (mm/s)",
  filament_current: "Filament current (A)", voltage_ripple: "Voltage ripple",
};

export default async function MachinePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const machine = await getMachine(id);
  if (!machine) notFound();
  const [clock, tel, risk, tickets, events] = await Promise.all([
    getClock(), getMachineTelemetry(id, 120), getMachineRiskHistory(id),
    getMachineTickets(id), getMachineEvents(id),
  ]);

  const b = band(machine.p7);
  const bandColor = b === "critical" ? "var(--critical)" : b === "watch" ? "var(--watch)" : "var(--healthy)";
  const horizons = [
    { h: "7d", p: machine.p7 }, { h: "14d", p: machine.p14 }, { h: "30d", p: machine.p30 },
    { h: "90d", p: machine.p90 }, { h: "180d", p: machine.p180 },
  ];
  const sensors = (KEY_SENSORS[machine.modality] ?? []).map((s) => ({
    key: s, label: SENSOR_LABEL[s] ?? s,
    values: tel.map((t) => t.readings?.[s]).filter((v): v is number => typeof v === "number"),
  })).filter((s) => s.values.length > 4);
  const ageYears = ((Date.parse(clock.current_date) - Date.parse(machine.install_date)) / 3.15576e10).toFixed(1);

  return (
    <>
      <Topbar title="Machine" currentDate={clock.current_date} />
      <div className="container grid" style={{ gap: 20 }}>
        <Link href="/predictions" className="link" style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
          <ArrowLeft size={14} /> Back to worklist
        </Link>

        {/* Header */}
        <div className="card pad-lg" style={{ borderTop: `3px solid ${bandColor}` }}>
          <div style={{ display: "flex", justifyContent: "space-between", flexWrap: "wrap", gap: 16, alignItems: "flex-start" }}>
            <div>
              <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
                <h2 style={{ fontSize: "1.5rem", fontWeight: 680, letterSpacing: "-0.02em" }} className="mono">{machine.machine_id}</h2>
                <Pill band={b} />
                <span className="chip">{machine.modality} · {machine.model}</span>
              </div>
              <p className="muted" style={{ marginTop: 8, fontSize: "0.9rem" }}>
                {machine.customer ?? machine.hospital_name} · {machine.country} · commissioned {fmtDate(machine.commission_date)}
              </p>
            </div>
            <div style={{ display: "flex", gap: 26, flexWrap: "wrap" }}>
              {[
                ["Age", `${ageYears} yrs`], ["Utilisation", `${fmtNum(Math.round(machine.scans_per_day))} scans/day`],
                ["Installed", fmtDate(machine.install_date)], ["Reporting", machine.flaky_reporter ? "flaky" : "reliable"],
              ].map(([k, v]) => (
                <div key={k}><div className="stat-label" style={{ fontSize: "0.68rem" }}>{k}</div><div style={{ fontWeight: 600, marginTop: 4 }}>{v}</div></div>
              ))}
            </div>
          </div>
        </div>

        {/* Risk */}
        <div className="grid grid-2">
          <div className="card pad-lg">
            <div className="card-head"><div><div className="card-title">Failure risk — survival curve</div><div className="card-sub">probability of failure within each horizon</div></div></div>
            <div style={{ display: "flex", justifyContent: "center", padding: "8px 0 16px" }}>
              <Spark values={[machine.p7, machine.p14, machine.p30, machine.p90, machine.p180]} width={280} height={72} color={bandColor} />
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(5,1fr)", gap: 8 }}>
              {horizons.map((x) => (
                <div key={x.h} style={{ textAlign: "center", padding: "10px 4px", borderRadius: 10, background: "var(--surface-2)", border: "1px solid var(--border)" }}>
                  <div className="faint mono" style={{ fontSize: "0.68rem" }}>{x.h}</div>
                  <div className="tnum" style={{ fontWeight: 700, fontSize: "1.05rem", marginTop: 3, color: x.p >= 0.15 ? "var(--critical)" : x.p >= 0.05 ? "var(--watch)" : "var(--text)" }}>{fmtPct(x.p, x.p < 0.1 ? 1 : 0)}</div>
                </div>
              ))}
            </div>
          </div>

          <div className="card pad-lg">
            <div className="card-head"><div><div className="card-title">7-day risk over time</div><div className="card-sub">how this machine&apos;s risk has evolved</div></div></div>
            {risk.length > 2
              ? <AreaChart id={`risk-${id}`} height={170} color={bandColor} values={risk.map((r) => r.p_fail)} />
              : <p className="muted" style={{ padding: "40px 0", textAlign: "center" }}>Not enough history yet.</p>}
          </div>
        </div>

        {/* Telemetry */}
        <div>
          <div className="card-title" style={{ marginBottom: 12 }}>Telemetry — last 120 days</div>
          <div className="grid grid-3">
            {sensors.map((s) => {
              const cur = s.values[s.values.length - 1];
              return (
                <div key={s.key} className="card">
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 10 }}>
                    <span className="muted" style={{ fontSize: "0.8rem" }}>{s.label}</span>
                    <span className="tnum" style={{ fontWeight: 700 }}>{cur?.toFixed(1)}</span>
                  </div>
                  <AreaChart id={`sen-${s.key}`} height={90} color="var(--data-2)" values={s.values} />
                </div>
              );
            })}
          </div>
        </div>

        {/* History */}
        <div className="grid grid-2">
          <div className="card pad-lg">
            <div className="card-head"><div><div className="card-title">Service tickets</div><div className="card-sub">engineer notes (free text → the retrieval layer)</div></div></div>
            <div style={{ display: "grid", gap: 10 }}>
              {tickets.length === 0 && <p className="muted">No tickets on record.</p>}
              {tickets.map((t, i) => (
                <div key={i} style={{ padding: "10px 12px", borderRadius: 10, background: "var(--surface-2)", border: "1px solid var(--border)" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
                    <span className={`gov-badge ${t.ticket_type === "corrective" ? "gov-rollback" : t.ticket_type === "preventive" ? "gov-auto" : "gov-hold"}`}>{t.ticket_type.replace("_", " ")}</span>
                    <span className="faint" style={{ fontSize: "0.74rem" }}>{fmtDate(t.open_date)}</span>
                  </div>
                  <div style={{ fontSize: "0.84rem", marginTop: 7 }}>{t.note_text}</div>
                  {(t.part_replaced || t.engineer_id) && (
                    <div className="faint" style={{ fontSize: "0.74rem", marginTop: 5 }}>
                      {t.part_replaced && <>part: {t.part_replaced} · </>}{t.engineer_id}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>

          <div className="card pad-lg">
            <div className="card-head"><div><div className="card-title">Failure &amp; maintenance history</div><div className="card-sub">what has happened to this unit</div></div></div>
            <div className="timeline">
              {events.length === 0 && <p className="muted">No events on record.</p>}
              {events.map((e, i) => (
                <div className="tl-item" key={i}>
                  <span className={`tl-dot ${e.kind === "failure" ? "rollback" : e.kind === "corrective" ? "hold" : "auto"}`} />
                  <div className="tl-date">{fmtDate(e.date)}</div>
                  <div className="tl-title" style={{ textTransform: "capitalize" }}>{e.kind} <span className="faint mono" style={{ fontWeight: 400 }}>· {e.detail}</span></div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
