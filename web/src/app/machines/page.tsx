import { getClock, getWorklist, getFleetSummary, getModalityMix } from "@/lib/queries";
import { Topbar, Stat, fmtNum } from "@/components/dash/ui";
import { FleetBrowser } from "@/components/dash/fleet-browser";
import { MethodStrip } from "@/components/dash/info";

export const dynamic = "force-dynamic";

export default async function Machines() {
  const [clock, rows, s, mix] = await Promise.all([
    getClock(), getWorklist(500), getFleetSummary(), getModalityMix(),
  ]);
  return (
    <>
      <Topbar title="Machines" currentDate={clock.current_date} />
      <div className="container grid" style={{ gap: 20 }}>
        <div className="grid grid-4">
          <Stat label="Fleet size" value={fmtNum(s.machines)} foot={<span className="muted">{mix.map((m) => `${m.n} ${m.modality}`).join(" · ")}</span>} />
          <Stat label="Critical" value={<span style={{ color: "var(--critical)" }}>{s.critical}</span>} foot={<span className="muted">inspect this week</span>} />
          <Stat label="On watch" value={<span style={{ color: "var(--watch)" }}>{s.watch}</span>} foot={<span className="muted">trending up</span>} />
          <Stat label="Healthy" tone="data" value={fmtNum(s.healthy)} foot={<span className="muted">nominal</span>} />
        </div>

        <div>
          <div className="eyebrow" style={{ marginBottom: 8 }}>Fleet monitor</div>
          <h2 style={{ fontSize: "1.2rem", fontWeight: 640, letterSpacing: "-0.01em", marginBottom: 4 }}>Browse the installed base</h2>
          <p className="muted" style={{ fontSize: "0.86rem", marginBottom: 16 }}>
            Every machine under management. Filter by modality, health, or country — click any unit to open its full history.
          </p>
        </div>

        <MethodStrip label="HOW A MACHINE IS BANDED">
          Each card&apos;s band comes from the model&apos;s calibrated <b>P(fail ≤ 7d)</b>:
          <b> critical ≥ 0.15</b>, <b>watch ≥ 0.05</b>, else healthy — thresholds set by the
          cost asymmetry (a miss ≈ 100× a false alarm), not by eyeballing. Open any machine to see
          its <b>SHAP risk drivers</b> (why), its <b>z-score anomaly</b> signal, and <b>retrieved
          similar cases</b> — the three modules for one unit.
        </MethodStrip>

        <FleetBrowser rows={rows} />
      </div>
    </>
  );
}
