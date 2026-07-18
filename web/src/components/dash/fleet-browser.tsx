"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import type { WorklistRow } from "@/lib/queries";
import { band } from "@/lib/risk";
import { Pill, fmtPct } from "./ui";
import { Spark } from "./charts";

type BandKey = "all" | "critical" | "watch" | "healthy";
type SortKey = "risk" | "id" | "age";

export function FleetBrowser({ rows }: { rows: WorklistRow[] }) {
  const [q, setQ] = useState("");
  const [modality, setModality] = useState<string>("all");
  const [bnd, setBnd] = useState<BandKey>("all");
  const [country, setCountry] = useState<string>("all");
  const [sort, setSort] = useState<SortKey>("risk");

  const modalities = useMemo(() => ["all", ...Array.from(new Set(rows.map((r) => r.modality)))], [rows]);
  const countries = useMemo(() => ["all", ...Array.from(new Set(rows.map((r) => r.country))).sort()], [rows]);

  const view = useMemo(() => {
    const f = q.trim().toLowerCase();
    let v = rows.filter((r) => {
      if (modality !== "all" && r.modality !== modality) return false;
      if (country !== "all" && r.country !== country) return false;
      if (bnd !== "all" && band(r.p7) !== bnd) return false;
      if (f && !(r.machine_id.toLowerCase().includes(f) || r.hospital_name?.toLowerCase().includes(f) ||
        r.customer?.toLowerCase().includes(f))) return false;
      return true;
    });
    v = v.slice().sort((a, b) =>
      sort === "id" ? a.machine_id.localeCompare(b.machine_id) : b.p7 - a.p7);
    return v;
  }, [rows, q, modality, country, bnd, sort]);

  const counts = useMemo(() => ({
    critical: rows.filter((r) => band(r.p7) === "critical").length,
    watch: rows.filter((r) => band(r.p7) === "watch").length,
    healthy: rows.filter((r) => band(r.p7) === "healthy").length,
  }), [rows]);

  return (
    <div className="grid" style={{ gap: 16 }}>
      {/* Filter bar */}
      <div className="card" style={{ padding: 16, display: "flex", gap: 14, flexWrap: "wrap", alignItems: "center" }}>
        <input className="wl-search" style={{ width: 220 }} placeholder="Search machine, site, customer…" value={q} onChange={(e) => setQ(e.target.value)} />
        <div className="fgroup">
          {modalities.map((m) => (
            <button key={m} className={`fchip${modality === m ? " on" : ""}`} onClick={() => setModality(m)}>{m === "all" ? "All modalities" : m}</button>
          ))}
        </div>
        <div className="fgroup">
          {(["all", "critical", "watch", "healthy"] as BandKey[]).map((b) => (
            <button key={b} className={`fchip${bnd === b ? " on" : ""}`} onClick={() => setBnd(b)}>
              {b === "all" ? "All health" : b}{b !== "all" && <span className="faint"> {counts[b]}</span>}
            </button>
          ))}
        </div>
        <select className="wl-search" style={{ width: "auto" }} value={country} onChange={(e) => setCountry(e.target.value)}>
          {countries.map((c) => <option key={c} value={c}>{c === "all" ? "All countries" : c}</option>)}
        </select>
        <select className="wl-search" style={{ width: "auto", marginLeft: "auto" }} value={sort} onChange={(e) => setSort(e.target.value as SortKey)}>
          <option value="risk">Sort: highest risk</option>
          <option value="id">Sort: machine ID</option>
        </select>
      </div>

      {/* Grid of machines */}
      <div className="fleet-grid">
        {view.slice(0, 240).map((m) => {
          const b = band(m.p7);
          const c = b === "critical" ? "var(--critical)" : b === "watch" ? "var(--watch)" : "var(--healthy)";
          return (
            <Link key={m.machine_id} href={`/machines/${m.machine_id}`} className="mcard" style={{ borderLeft: `3px solid ${c}` }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 8 }}>
                <div>
                  <div className="mono" style={{ fontWeight: 650 }}>{m.machine_id}</div>
                  <div className="faint" style={{ fontSize: "0.74rem", marginTop: 2 }}>{m.modality} · {m.model}</div>
                </div>
                <Pill band={b} />
              </div>
              <div className="muted" style={{ fontSize: "0.78rem", marginTop: 9, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                {m.customer ?? m.hospital_name} · {m.country}
              </div>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: 10 }}>
                <Spark values={[m.p7, m.p14, m.p30, m.p90, m.p180]} width={90} height={26} color={c} />
                <div style={{ textAlign: "right" }}>
                  <div className="tnum" style={{ fontWeight: 700, fontSize: "1.05rem", color: c }}>{fmtPct(m.p7, m.p7 < 0.1 ? 1 : 0)}</div>
                  <div className="faint" style={{ fontSize: "0.66rem" }}>7-day risk</div>
                </div>
              </div>
            </Link>
          );
        })}
      </div>
      <p className="faint" style={{ fontSize: "0.76rem" }}>
        Showing {Math.min(view.length, 240)} of {view.length} matching machines{view.length > 240 ? " (refine to see more)" : ""}.
      </p>
    </div>
  );
}
