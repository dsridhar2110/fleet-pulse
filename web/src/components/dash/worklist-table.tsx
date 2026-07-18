"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import type { WorklistRow } from "@/lib/queries";
import { band } from "@/lib/risk";
import { Pill, fmtPct } from "./ui";
import { Spark } from "./charts";

const HZ = [7, 14, 30, 90, 180] as const;
type H = (typeof HZ)[number];
const key = (h: H) => `p${h}` as keyof WorklistRow;

export function WorklistTable({ rows }: { rows: WorklistRow[] }) {
  const [h, setH] = useState<H>(7);
  const [q, setQ] = useState("");

  const view = useMemo(() => {
    const f = q.trim().toLowerCase();
    return rows
      .filter((r) => !f || r.machine_id.toLowerCase().includes(f) ||
        r.hospital_name?.toLowerCase().includes(f) || r.modality.toLowerCase().includes(f))
      .slice()
      .sort((a, b) => (b[key(h)] as number) - (a[key(h)] as number));
  }, [rows, h, q]);

  return (
    <div className="card pad-lg">
      <div className="card-head" style={{ flexWrap: "wrap", gap: 12 }}>
        <div>
          <div className="card-title">Service worklist</div>
          <div className="card-sub">ranked by failure risk within the selected horizon · {view.length} machines</div>
        </div>
        <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
          <input className="wl-search" placeholder="Search machine, site…" value={q}
            onChange={(e) => setQ(e.target.value)} />
          <div className="seg">
            {HZ.map((x) => (
              <button key={x} data-on={x === h} onClick={() => setH(x)}>{x}d</button>
            ))}
          </div>
        </div>
      </div>
      <div className="tbl-wrap">
        <table className="tbl">
          <thead>
            <tr>
              <th>Machine</th><th>Modality</th><th>Site</th><th>Country</th>
              <th>7→180d curve</th><th className="num">P(fail ≤ {h}d)</th><th>Status</th>
            </tr>
          </thead>
          <tbody>
            {view.slice(0, 120).map((m) => {
              const p = m[key(h)] as number;
              const b = band(m.p7);
              return (
                <tr key={m.machine_id}>
                  <td className="mono"><Link href={`/machines/${m.machine_id}`} className="mlink">{m.machine_id}</Link></td>
                  <td><span className="tag-mod">{m.modality}</span></td>
                  <td className="muted" style={{ maxWidth: 190, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{m.hospital_name}</td>
                  <td className="muted">{m.country}</td>
                  <td><Spark values={[m.p7, m.p14, m.p30, m.p90, m.p180]} color={b === "critical" ? "var(--critical)" : b === "watch" ? "var(--watch)" : "var(--healthy)"} /></td>
                  <td className="num">
                    <div style={{ display: "flex", alignItems: "center", gap: 9, justifyContent: "flex-end" }}>
                      <div className="bar-track" style={{ width: 64 }}>
                        <div className={`bar-fill ${b === "critical" ? "crit" : b === "watch" ? "watch" : "ok"}`} style={{ width: `${Math.max(3, p * 100)}%` }} />
                      </div>
                      <span className="tnum" style={{ fontWeight: 700, minWidth: 44 }}>{fmtPct(p, p < 0.1 ? 1 : 0)}</span>
                    </div>
                  </td>
                  <td><Pill band={b} /></td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
