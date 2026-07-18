import type { Status } from "./types";

export const COUNTRY_NAME: Record<string, string> = {
  DE: "Germany",
  US: "United States",
  GB: "United Kingdom",
  FR: "France",
  IN: "India",
  JP: "Japan",
  BR: "Brazil",
  AU: "Australia",
  ES: "Spain",
  CN: "China",
};

export const MODALITY_LABEL: Record<string, string> = {
  MRI: "MRI",
  CT: "CT",
  XRAY: "X-ray",
};

export const SENSOR_LABEL: Record<string, string> = {
  helium_level: "Helium level (%)",
  compressor_temp: "Compressor temp (°C)",
  gradient_temp: "Gradient temp (°C)",
  rf_power_var: "RF power variance",
  vibration_rms: "Vibration (mm/s)",
  chiller_flow: "Chiller flow (L/min)",
  tube_current_var: "Tube current variance",
  tube_temp: "Tube temp (°C)",
  detector_noise: "Detector noise",
  gantry_vibration: "Gantry vibration (mm/s)",
  cooling_margin: "Cooling margin (°C)",
  filament_current: "Filament current (A)",
  voltage_ripple: "Voltage ripple",
  scans_count: "Scans / day",
};

export function riskPct(risk: number): string {
  return `${(risk * 100).toFixed(0)}%`;
}

export const STATUS_LABEL: Record<Status, string> = {
  critical: "Critical",
  watch: "Watch",
  healthy: "Healthy",
};

export const STATUS_ORDER: Record<Status, number> = {
  critical: 0,
  watch: 1,
  healthy: 2,
};

export function countryLabel(code: string): string {
  return COUNTRY_NAME[code] ?? code;
}

export function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}
