import { cn } from "@/lib/utils";
import type { FleetSummary } from "@/lib/types";

function Kpi({
  label,
  value,
  sub,
  accent,
  bar,
}: {
  label: string;
  value: string;
  sub: string;
  accent?: string;
  bar?: number;
}) {
  return (
    <div className="rounded-xl border bg-card p-4 md:p-5">
      <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
        {label}
      </div>
      <div className={cn("mt-2 text-3xl font-bold tracking-tight tnum", accent)}>{value}</div>
      <div className="mt-1 text-xs text-muted-foreground">{sub}</div>
      {bar !== undefined && (
        <div className="mt-3 h-1.5 w-full overflow-hidden rounded-full bg-muted">
          <div
            className={cn("h-full rounded-full", accent ? accent.replace("text-", "bg-") : "bg-primary")}
            style={{ width: `${Math.max(bar, 2)}%` }}
          />
        </div>
      )}
    </div>
  );
}

export function KpiCards({ summary }: { summary: FleetSummary }) {
  const flagged = summary.critical + summary.watch;
  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      <Kpi
        label="Fleet size"
        value={summary.machines.toLocaleString()}
        sub="connected scanners monitored"
      />
      <Kpi
        label="Critical"
        value={summary.critical.toString()}
        sub="≥20% risk of failure in 7 days"
        accent="text-critical"
        bar={(summary.critical / summary.machines) * 100 * 6}
      />
      <Kpi
        label="Watch"
        value={summary.watch.toString()}
        sub="5–20% risk — monitor closely"
        accent="text-watch"
        bar={(summary.watch / summary.machines) * 100 * 6}
      />
      <Kpi
        label="This week's worklist"
        value={flagged.toString()}
        sub="machines to review before failure"
        accent="text-primary"
      />
    </div>
  );
}
