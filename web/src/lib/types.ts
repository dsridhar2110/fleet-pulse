export type Status = "critical" | "watch" | "healthy";
export type Modality = "CT" | "MRI" | "XRAY";

export interface FleetMachine {
  id: string;
  modality: Modality;
  model: string;
  country: string;
  region: string;
  hospital: string;
  risk: number;
  status: Status;
  likelyIssue: string;
  ageYears: number;
}

export interface FleetSummary {
  machines: number;
  critical: number;
  watch: number;
  healthy: number;
  modalities: Modality[];
  countries: string[];
}

export interface FleetData {
  asOf: string;
  summary: FleetSummary;
  machines: FleetMachine[];
}

export interface TelemetryPoint {
  d: string;
  [sensor: string]: number | string;
}

export interface Ticket {
  date: string;
  type: string;
  component: string | null;
  part: string | null;
  engineer: string;
  note: string;
}

export interface RiskPoint {
  d: string;
  risk: number;
}

export interface FailureMark {
  date: string;
  component: string;
  sudden: boolean;
}

export interface MaintenanceMark {
  date: string;
  type: string;
}

export interface Driver {
  driver: string;
  contribution: number;
}

export interface MachineDetail {
  id: string;
  modality: Modality;
  model: string;
  country: string;
  region: string;
  hospital: string;
  installDate: string;
  ageYears: number;
  risk: number;
  status: Status;
  sensors: string[];
  telemetry: TelemetryPoint[];
  riskHistory: RiskPoint[];
  tickets: Ticket[];
  failures: FailureMark[];
  maintenance: MaintenanceMark[];
  drivers: Driver[];
}

export interface Metrics {
  prevalence_test: number;
  "prauc::XGBoost (calibrated)": number;
  "prauc::Rolling z-score alarm": number;
  "prauc::IsolationForest": number;
  "prauc::Rank by machine age": number;
  "rocauc::XGBoost": number;
  precision_at_20: number;
  recall_at_20: number;
  brier: number;
  best_threshold_ratio100: number;
  median_lead_days: number | null;
  intercepted_at_best_t: number;
  test_positives: number;
}
