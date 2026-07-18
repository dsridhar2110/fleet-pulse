import { sql } from "./db";

// Risk helpers live in a db-free module so client components can import them.
export { CRITICAL, WATCH, band } from "./risk";
import { CRITICAL, WATCH } from "./risk";

export type Clock = { current_date: string; start_date: string; window_months: number };

export async function getClock(): Promise<Clock> {
  const r = (await sql`SELECT value FROM world_meta WHERE key='clock'`) as { value: Clock }[];
  return r[0]?.value ?? { current_date: "", start_date: "", window_months: 36 };
}

export type FleetSummary = {
  machines: number; customers: number; new_this_month: number;
  critical: number; watch: number; healthy: number;
  fleet_expected_loss: number; cumulative_net_savings: number;
  caught: number; missed: number; false_alarm: number; detection_rate: number;
};

export async function getFleetSummary(): Promise<FleetSummary> {
  const rows = (await sql`
    WITH latest AS (SELECT max(as_of_date) d FROM predictions),
    p7 AS (
      SELECT p.machine_id, p.p_fail FROM predictions p, latest
      WHERE p.horizon_days=7 AND p.as_of_date=latest.d
    ),
    imp AS (SELECT * FROM impact_daily ORDER BY as_of_date DESC LIMIT 1),
    dec AS (
      SELECT
        count(*) FILTER (WHERE outcome='caught')::int caught,
        count(*) FILTER (WHERE outcome='missed')::int missed,
        count(*) FILTER (WHERE outcome='false_alarm')::int false_alarm
      FROM decisions WHERE status='resolved'
    )
    SELECT
      (SELECT count(*)::int FROM machines WHERE status='active') machines,
      (SELECT count(*)::int FROM customers) customers,
      (SELECT count(*)::int FROM machines WHERE commission_date >= (SELECT d FROM latest) - INTERVAL '90 days') new_this_month,
      (SELECT count(*)::int FROM p7 WHERE p_fail >= ${CRITICAL}) critical,
      (SELECT count(*)::int FROM p7 WHERE p_fail >= ${WATCH} AND p_fail < ${CRITICAL}) watch,
      (SELECT count(*)::int FROM p7 WHERE p_fail < ${WATCH}) healthy,
      (SELECT fleet_expected_loss::float FROM imp) fleet_expected_loss,
      (SELECT cumulative_net_savings::float FROM imp) cumulative_net_savings,
      dec.caught, dec.missed, dec.false_alarm
    FROM dec
  `) as any[];
  const r = rows[0];
  r.detection_rate = r.caught + r.missed > 0 ? r.caught / (r.caught + r.missed) : 0;
  return r as FleetSummary;
}

export type WorklistRow = {
  machine_id: string; modality: string; model: string; country: string;
  hospital_name: string; customer: string;
  p7: number; p14: number; p30: number; p90: number; p180: number;
};

export async function getWorklist(limit = 100): Promise<WorklistRow[]> {
  return (await sql`
    WITH latest AS (SELECT max(as_of_date) d FROM predictions),
    piv AS (
      SELECT machine_id,
        max(p_fail) FILTER (WHERE horizon_days=7)::float   p7,
        max(p_fail) FILTER (WHERE horizon_days=14)::float  p14,
        max(p_fail) FILTER (WHERE horizon_days=30)::float  p30,
        max(p_fail) FILTER (WHERE horizon_days=90)::float  p90,
        max(p_fail) FILTER (WHERE horizon_days=180)::float p180
      FROM predictions p, latest WHERE p.as_of_date=latest.d GROUP BY machine_id
    )
    SELECT piv.*, m.modality, m.model, m.country, m.hospital_name,
           COALESCE(c.name, m.hospital_name) customer
    FROM piv JOIN machines m USING (machine_id)
    LEFT JOIN customers c ON c.customer_id = m.customer_id
    ORDER BY piv.p7 DESC
    LIMIT ${limit}
  `) as WorklistRow[];
}

export type ImpactPoint = {
  as_of_date: string; cumulative_net_savings: number; worklist_net_savings: number;
  fleet_expected_loss: number; downtime_days_avoided: number;
};

export async function getEconomicsSeries(): Promise<ImpactPoint[]> {
  return (await sql`
    SELECT as_of_date::text,
      cumulative_net_savings::float, worklist_net_savings::float,
      fleet_expected_loss::float, downtime_days_avoided::float
    FROM impact_daily ORDER BY as_of_date
  `) as ImpactPoint[];
}

export async function getAssumptions(): Promise<Record<string, any>> {
  const r = (await sql`SELECT assumptions FROM impact_daily ORDER BY as_of_date DESC LIMIT 1`) as any[];
  return r[0]?.assumptions ?? {};
}

export type DecisionRow = {
  machine_id: string; as_of_date: string; horizon_days: number; action: string;
  risk_score: number; expected_savings: number; status: string; outcome: string;
  modality: string; hospital_name: string;
};

export async function getRecentDecisions(limit = 40, resolvedOnly = true): Promise<DecisionRow[]> {
  const rows = resolvedOnly
    ? await sql`
        SELECT d.machine_id, d.as_of_date::text, d.horizon_days, d.action, d.risk_score::float,
               d.expected_savings::float, d.status, d.outcome, m.modality, m.hospital_name
        FROM decisions d JOIN machines m USING (machine_id)
        WHERE d.status='resolved'
        ORDER BY d.as_of_date DESC, d.risk_score DESC LIMIT ${limit}`
    : await sql`
        SELECT d.machine_id, d.as_of_date::text, d.horizon_days, d.action, d.risk_score::float,
               d.expected_savings::float, d.status, d.outcome, m.modality, m.hospital_name
        FROM decisions d JOIN machines m USING (machine_id)
        ORDER BY d.as_of_date DESC, d.risk_score DESC LIMIT ${limit}`;
  return rows as DecisionRow[];
}

export type ModelVersion = {
  version: string; algo: string; trained_from: string; trained_to: string;
  threshold: number; metrics: Record<string, number>; hyperparams: Record<string, any>;
  parent_version: string | null; status: string; promoted_at: string;
};

export async function getModelVersions(): Promise<ModelVersion[]> {
  return (await sql`
    SELECT version, algo, trained_from::text, trained_to::text, threshold::float,
           metrics, hyperparams, parent_version, status, promoted_at::text
    FROM model_versions ORDER BY promoted_at
  `) as ModelVersion[];
}

export type EvolutionEvent = {
  id: number; ts: string; event_type: string; trigger: string; version: string | null;
  parent_version: string | null; change: any; metric_effect: any; note: string;
  actor_role: string; action: string; rationale: string;
};

export async function getEvolutionLog(): Promise<EvolutionEvent[]> {
  return (await sql`
    SELECT e.id, e.ts::text, e.event_type, e.trigger, e.version, e.parent_version,
           e.change, e.metric_effect, e.note,
           g.actor_role, g.action, g.rationale
    FROM evolution_log e
    LEFT JOIN governance_actions g ON g.evolution_event_id = e.id
    ORDER BY e.ts, e.id
  `) as EvolutionEvent[];
}

// Health trend: weekly count of machines in each band across the deployment window.
export type HealthPoint = { as_of_date: string; critical: number; watch: number; healthy: number };

export async function getHealthTrend(): Promise<HealthPoint[]> {
  return (await sql`
    WITH p7 AS (
      SELECT as_of_date, machine_id, p_fail FROM predictions WHERE horizon_days=7
    )
    SELECT as_of_date::text,
      count(*) FILTER (WHERE p_fail >= ${CRITICAL})::int critical,
      count(*) FILTER (WHERE p_fail >= ${WATCH} AND p_fail < ${CRITICAL})::int watch,
      count(*) FILTER (WHERE p_fail < ${WATCH})::int healthy
    FROM p7 GROUP BY as_of_date ORDER BY as_of_date
  `) as HealthPoint[];
}

export type MixRow = { modality: string; n: number };
export async function getModalityMix(): Promise<MixRow[]> {
  return (await sql`
    SELECT modality, count(*)::int n FROM machines WHERE status='active'
    GROUP BY modality ORDER BY n DESC
  `) as MixRow[];
}

// ---------------------------------------------------------------- machine detail
export type MachineDetail = {
  machine_id: string; modality: string; model: string; country: string; region: string;
  hospital_name: string; customer: string | null; install_date: string; commission_date: string;
  scans_per_day: number; flaky_reporter: boolean; status: string;
  p7: number; p14: number; p30: number; p90: number; p180: number;
};

export async function getMachine(id: string): Promise<MachineDetail | null> {
  const rows = (await sql`
    WITH latest AS (SELECT max(as_of_date) d FROM predictions),
    piv AS (
      SELECT
        max(p_fail) FILTER (WHERE horizon_days=7)::float p7,
        max(p_fail) FILTER (WHERE horizon_days=14)::float p14,
        max(p_fail) FILTER (WHERE horizon_days=30)::float p30,
        max(p_fail) FILTER (WHERE horizon_days=90)::float p90,
        max(p_fail) FILTER (WHERE horizon_days=180)::float p180
      FROM predictions p, latest WHERE p.as_of_date=latest.d AND p.machine_id=${id}
    )
    SELECT m.machine_id, m.modality, m.model, m.country, m.region, m.hospital_name,
           c.name customer, m.install_date::text, m.commission_date::text,
           m.scans_per_day::float, m.flaky_reporter, m.status,
           piv.p7, piv.p14, piv.p30, piv.p90, piv.p180
    FROM machines m LEFT JOIN customers c ON c.customer_id=m.customer_id, piv
    WHERE m.machine_id=${id}
  `) as MachineDetail[];
  return rows[0] ?? null;
}

export type TelemetryPoint = { date: string; readings: Record<string, number>; scans_count: number };
export async function getMachineTelemetry(id: string, days = 120): Promise<TelemetryPoint[]> {
  return (await sql`
    SELECT date::text, readings, scans_count::float
    FROM telemetry_daily
    WHERE machine_id=${id} AND date >= (SELECT max(date) FROM telemetry_daily) - ${days}::int
    ORDER BY date
  `) as TelemetryPoint[];
}

export type RiskPoint = { as_of_date: string; p_fail: number };
export async function getMachineRiskHistory(id: string): Promise<RiskPoint[]> {
  return (await sql`
    SELECT as_of_date::text, p_fail::float
    FROM predictions WHERE machine_id=${id} AND horizon_days=7 ORDER BY as_of_date
  `) as RiskPoint[];
}

export type TicketRow = {
  open_date: string; ticket_type: string; component: string | null;
  part_replaced: string | null; engineer_id: string | null; note_text: string | null;
};
export async function getMachineTickets(id: string, limit = 12): Promise<TicketRow[]> {
  return (await sql`
    SELECT open_date::text, ticket_type, component, part_replaced, engineer_id, note_text
    FROM tickets WHERE machine_id=${id} ORDER BY open_date DESC LIMIT ${limit}
  `) as TicketRow[];
}

export type EventRow = { date: string; kind: string; detail: string };
export async function getMachineEvents(id: string, limit = 12): Promise<EventRow[]> {
  return (await sql`
    (SELECT failure_date::text date, 'failure' kind, component || CASE WHEN sudden THEN ' · sudden' ELSE '' END detail
     FROM failures WHERE machine_id=${id})
    UNION ALL
    (SELECT date::text, maintenance_type kind, COALESCE(component,'routine') detail
     FROM maintenance WHERE machine_id=${id})
    ORDER BY date DESC LIMIT ${limit}
  `) as EventRow[];
}

// A few representative sensors per modality for the drill-down charts.
export const KEY_SENSORS: Record<string, string[]> = {
  MRI: ["helium_level", "compressor_temp", "vibration_rms"],
  CT: ["tube_current_var", "tube_temp", "gantry_vibration"],
  XRAY: ["filament_current", "tube_temp", "voltage_ripple"],
};
