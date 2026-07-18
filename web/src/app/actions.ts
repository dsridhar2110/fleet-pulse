"use server";

import { execFile } from "child_process";
import { promisify } from "util";
import path from "path";
import { revalidatePath } from "next/cache";

const pexec = promisify(execFile);

/**
 * Advance the simulated world clock by one day by running the Python tick
 * (`serve.tick`). Local-demo only — gated behind ALLOW_TICK because it spawns a
 * process and the ML stack isn't present on a serverless deploy. On Vercel this
 * returns a friendly message instead of running.
 */
export async function advanceDay(): Promise<{ ok: boolean; date?: string; error?: string }> {
  if (process.env.ALLOW_TICK !== "1") {
    return { ok: false, error: "Live advance runs on the local demo. On the hosted site the daily cron moves the clock." };
  }
  const mlDir = path.resolve(process.cwd(), "..", "ml");
  const py = path.join(mlDir, ".venv", "bin", "python");
  try {
    const { stdout } = await pexec(py, ["-m", "serve.tick", "--days", "1"], {
      cwd: mlDir,
      env: { ...process.env, PYTHONPATH: path.join(mlDir, "src") },
      timeout: 180_000,
      maxBuffer: 4 * 1024 * 1024,
    });
    const last = stdout.trim().split("\n").filter(Boolean).pop() || "{}";
    const result = JSON.parse(last);
    revalidatePath("/", "layout");
    return { ok: true, date: result.date };
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message.slice(0, 200) : "tick failed" };
  }
}
