import { promises as fs } from "fs";
import path from "path";
import type { FleetData, MachineDetail, Metrics, Driver } from "./types";

// Reads run at build time (static generation): the whole repo, including
// public/data, is present during `next build`, so the deployed site is fully
// static — no runtime filesystem access, no server, no model.
const DATA_DIR = path.join(process.cwd(), "public", "data");

async function readJson<T>(...segments: string[]): Promise<T> {
  const file = path.join(DATA_DIR, ...segments);
  return JSON.parse(await fs.readFile(file, "utf8")) as T;
}

export function getFleet(): Promise<FleetData> {
  return readJson<FleetData>("fleet.json");
}

export function getMetrics(): Promise<Metrics> {
  return readJson<Metrics>("metrics.json");
}

export function getGlobalDrivers(): Promise<Driver[]> {
  return readJson<Driver[]>("drivers_global.json");
}

export async function getMachine(id: string): Promise<MachineDetail | null> {
  try {
    return await readJson<MachineDetail>("machines", `${id}.json`);
  } catch {
    return null;
  }
}

export async function getAllMachineIds(): Promise<string[]> {
  const fleet = await getFleet();
  return fleet.machines.map((m) => m.id);
}
