import { Pill } from "./primitives";

type Row = {
  machine_id: string;
  modality: string;
  country: string;
  hospital_name: string;
  risk_calibrated: number;
  expected_loss_usd: number;
};

const usd = (v: number) => `$${Math.round(v).toLocaleString("en-US")}`;

function tone(risk: number): "crit" | "watch" | "ok" {
  if (risk >= 0.1) return "crit";
  if (risk >= 0.02) return "watch";
  return "ok";
}

export function Worklist({ rows, asOf }: { rows: Row[]; asOf: string }) {
  return (
    <figure className="overflow-hidden rounded-lg border border-border bg-card">
      <div className="flex flex-wrap items-baseline justify-between gap-2 border-b border-border px-5 py-4">
        <p className="text-[0.7rem] font-semibold uppercase tracking-[0.12em] text-muted-foreground">
          This week&rsquo;s inspection worklist
        </p>
        <p className="tnum text-xs text-muted-foreground">week of {asOf}</p>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="border-b border-border text-left text-[0.68rem] uppercase tracking-[0.1em] text-muted-foreground">
              <th className="px-5 py-3 font-semibold">#</th>
              <th className="px-5 py-3 font-semibold">Machine</th>
              <th className="px-5 py-3 font-semibold">Site</th>
              <th className="px-5 py-3 text-right font-semibold">7-day risk</th>
              <th className="px-5 py-3 text-right font-semibold">Expected loss</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={r.machine_id} className="border-b border-border/60 last:border-0">
                <td className="tnum px-5 py-3 text-muted-foreground">{i + 1}</td>
                <td className="px-5 py-3">
                  <span className="font-mono text-primary">{r.machine_id}</span>{" "}
                  <Pill tone="neutral">{r.modality}</Pill>
                </td>
                <td className="px-5 py-3 text-muted-foreground">
                  {r.hospital_name}
                </td>
                <td className="px-5 py-3 text-right">
                  <Pill tone={tone(r.risk_calibrated)}>
                    <span className="tnum">{(r.risk_calibrated * 100).toFixed(1)}%</span>
                  </Pill>
                </td>
                <td className="tnum px-5 py-3 text-right font-medium">{usd(r.expected_loss_usd)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <figcaption className="border-t border-border px-5 py-4 text-sm leading-relaxed text-muted-foreground">
        The actual output of the model: 20 machines, ranked, costed. Expected loss is calibrated risk ×
        downtime cost — so the list is ordered by money at stake, not by raw probability. Note how fast it
        decays: the top two machines carry a third of the fleet&rsquo;s expected loss, and by row 10 the model is
        telling you these are not worth a visit. Knowing where to <em>stop</em> reading is the point.
      </figcaption>
    </figure>
  );
}
