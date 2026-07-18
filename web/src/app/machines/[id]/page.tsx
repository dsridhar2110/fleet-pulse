import { notFound } from "next/navigation";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import {
  getClock, getMachine, getMachineTelemetry, getMachineRiskHistory,
  getMachineTickets, getMachineEvents, getRiskDrivers, getAnomaly, getTicketNeighbors, KEY_SENSORS,
} from "@/lib/queries";
import { band } from "@/lib/risk";
import { Topbar, Pill, fmtPct, fmtDate, fmtNum } from "@/components/dash/ui";
import { AreaChart, Spark } from "@/components/dash/charts";
import { Info, MethodStrip } from "@/components/dash/info";

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
  const [clock, tel, risk, tickets, events, drivers, anomaly, neighbors] = await Promise.all([
    getClock(), getMachineTelemetry(id, 120), getMachineRiskHistory(id),
    getMachineTickets(id), getMachineEvents(id),
    getRiskDrivers(id), getAnomaly(id), getTicketNeighbors(id),
  ]);
  const maxContrib = Math.max(0.01, ...drivers.map((d) => Math.abs(d.contribution)));
  const zPct = anomaly ? Math.min(100, (anomaly.zscore_anomaly / 5) * 100) : 0;

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
            <div className="card-head"><div><div className="card-title" style={{ display: "flex", alignItems: "center", gap: 7 }}>Failure risk — survival curve <Info text="S(t) = P(failure ≤ t). Reads left→right across horizons and is monotone non-decreasing because risk only accumulates over longer windows. 7/14-day points come from the XGBoost classifier; 30/90/180-day from the XGBoost-AFT survival model." /></div><div className="card-sub">P(fail ≤ horizon) at 7 / 14 / 30 / 90 / 180 days</div></div></div>
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

        {/* Modules 1 & 2 converge for this machine */}
        <div className="grid grid-2">
          <div className="card pad-lg">
            <div className="card-head"><div><div className="card-title" style={{ display: "flex", alignItems: "center", gap: 7 }}><span className="chip">M1</span> Why this machine <Info text="SHAP values decompose the model's log-odds for THIS machine into per-feature contributions. Positive = pushes risk up. This is how the supervised model 'explains' a prediction — the feature-extraction story made visible." /></div><div className="card-sub">top risk drivers · SHAP contributions</div></div></div>
            <div style={{ display: "grid", gap: 11 }}>
              {drivers.length === 0 && <p className="muted">No driver data.</p>}
              {drivers.map((d, i) => {
                const up = d.contribution > 0;
                return (
                  <div key={i} style={{ display: "grid", gap: 5 }}>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.84rem" }}>
                      <span>{d.feature}</span>
                      <span className="tnum" style={{ color: up ? "var(--critical)" : "var(--healthy)", fontWeight: 600 }}>{up ? "+" : ""}{d.contribution.toFixed(2)}</span>
                    </div>
                    <div className="bar-track"><div className="bar-fill" style={{ width: `${(Math.abs(d.contribution) / maxContrib) * 100}%`, background: up ? "linear-gradient(90deg,#ff7a7a,var(--critical))" : "linear-gradient(90deg,#5ee6bd,var(--healthy))" }} /></div>
                  </div>
                );
              })}
            </div>
          </div>

          <div className="card pad-lg">
            <div className="card-head"><div><div className="card-title" style={{ display: "flex", alignItems: "center", gap: 7 }}><span className="chip">M2</span> Anomaly signal <Info text="Unsupervised, model-free. The max |z-score| of any sensor vs this machine's own healthy baseline. On the fleet, this z-score alarm beat the IsolationForest and the 196→16 autoencoder on PR-AUC — and unlike them it names the culprit sensor. Shown as an independent corroboration of the supervised risk." /></div><div className="card-sub">z-score vs healthy baseline · the shipped detector</div></div></div>
            {anomaly ? (
              <>
                <div style={{ display: "flex", alignItems: "center", gap: 18, marginBottom: 14 }}>
                  <div><div className="stat-value" style={{ color: anomaly.is_anomaly ? "var(--watch)" : "var(--healthy)" }}>{anomaly.zscore_anomaly.toFixed(1)}σ</div><div className="faint" style={{ fontSize: "0.72rem" }}>peak sensor deviation</div></div>
                  <div style={{ flex: 1 }}>
                    <div className="bar-track" style={{ height: 9 }}><div className="bar-fill" style={{ width: `${zPct}%`, background: anomaly.is_anomaly ? "linear-gradient(90deg,#ffca6b,var(--watch))" : "linear-gradient(90deg,#5ee6bd,var(--healthy))" }} /></div>
                    <div style={{ display: "flex", justifyContent: "space-between", marginTop: 5 }} className="faint"><span style={{ fontSize: "0.68rem" }}>0σ</span><span style={{ fontSize: "0.68rem" }}>alarm ≥ 3σ</span><span style={{ fontSize: "0.68rem" }}>5σ</span></div>
                  </div>
                </div>
                <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
                  <span className={`pill ${anomaly.is_anomaly ? "pill-watch" : "pill-healthy"}`}>{anomaly.is_anomaly ? "anomalous" : "within normal"}</span>
                  {anomaly.top_sensor && <span className="chip">driver: {anomaly.top_sensor.replace(/_/g, " ")}</span>}
                  <span className="chip">AE recon err {anomaly.recon_error.toFixed(3)}</span>
                </div>
                <p className="faint" style={{ fontSize: "0.76rem", marginTop: 12 }}>
                  Unsupervised anomaly is a weak predictor alone (PR-AUC ~0.04) — its value is as an interpretable, model-independent second opinion alongside the supervised risk above.
                </p>
              </>
            ) : <p className="muted">No anomaly signal.</p>}
          </div>
        </div>

        {/* Module 3 — retrieval */}
        {neighbors && neighbors.neighbors.length > 0 && (
          <div className="card pad-lg">
            <div className="card-head"><div><div className="card-title" style={{ display: "flex", alignItems: "center", gap: 7 }}><span className="chip">M3</span> Similar past cases <Info text="TF-IDF + cosine similarity over historical ticket symptoms (never the resolutions — that would leak the fix). Retrieval, not generation: no LLM, fully measurable. P@1 ≈ 0.87 vs a 0.41 majority baseline; misses are lexical, which is the measured case for embeddings next." /></div><div className="card-sub">TF-IDF retrieval over the fleet&apos;s ticket history — “{neighbors.query_text}”</div></div></div>
            <div className="grid grid-3">
              {neighbors.neighbors.map((n, i) => (
                <div key={i} style={{ padding: "12px 14px", borderRadius: 11, background: "var(--surface-2)", border: "1px solid var(--border)" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 7 }}>
                    <span className="mono faint" style={{ fontSize: "0.74rem" }}>{n.machine_id}</span>
                    <span className="chip">{(n.similarity * 100).toFixed(0)}% match</span>
                  </div>
                  <div style={{ fontSize: "0.82rem" }}>{n.note}</div>
                  {n.component && <div className="faint" style={{ fontSize: "0.72rem", marginTop: 6 }}>component: {n.component}</div>}
                </div>
              ))}
            </div>
          </div>
        )}

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
