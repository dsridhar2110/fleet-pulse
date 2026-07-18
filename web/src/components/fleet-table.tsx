"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { Search, ChevronRight } from "lucide-react";
import type { FleetMachine, Status } from "@/lib/types";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { StatusPill } from "@/components/status-pill";
import {
  MODALITY_LABEL,
  STATUS_LABEL,
  STATUS_ORDER,
  countryLabel,
  riskPct,
} from "@/lib/format";
import { cn } from "@/lib/utils";

const RISK_BAR = (risk: number) => {
  if (risk >= 0.2) return "bg-critical";
  if (risk >= 0.05) return "bg-watch";
  return "bg-primary/50";
};

export function FleetTable({ machines }: { machines: FleetMachine[] }) {
  const [q, setQ] = useState("");
  const [modality, setModality] = useState("all");
  const [country, setCountry] = useState("all");
  const [status, setStatus] = useState("all");

  const countries = useMemo(
    () => Array.from(new Set(machines.map((m) => m.country))).sort(),
    [machines],
  );
  const modalities = useMemo(
    () => Array.from(new Set(machines.map((m) => m.modality))).sort(),
    [machines],
  );

  const rows = useMemo(() => {
    const query = q.trim().toLowerCase();
    return machines
      .filter((m) => {
        if (modality !== "all" && m.modality !== modality) return false;
        if (country !== "all" && m.country !== country) return false;
        if (status !== "all" && m.status !== status) return false;
        if (
          query &&
          !m.id.toLowerCase().includes(query) &&
          !m.hospital.toLowerCase().includes(query) &&
          !m.model.toLowerCase().includes(query)
        )
          return false;
        return true;
      })
      .sort((a, b) => {
        const s = STATUS_ORDER[a.status] - STATUS_ORDER[b.status];
        return s !== 0 ? s : b.risk - a.risk;
      });
  }, [machines, q, modality, country, status]);

  return (
    <div className="rounded-xl border bg-card">
      {/* Toolbar */}
      <div className="flex flex-col gap-3 border-b p-4 md:flex-row md:items-center md:justify-between">
        <div>
          <h2 className="text-base font-semibold">Fleet worklist</h2>
          <p className="text-xs text-muted-foreground">
            Ranked by 7-day failure risk · {rows.length} of {machines.length} machines
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Machine, site, model…"
              className="h-9 w-full pl-8 md:w-52"
            />
          </div>
          <FilterSelect
            value={modality}
            onChange={setModality}
            placeholder="Modality"
            options={modalities.map((m) => ({ value: m, label: MODALITY_LABEL[m] ?? m }))}
          />
          <FilterSelect
            value={country}
            onChange={setCountry}
            placeholder="Country"
            options={countries.map((c) => ({ value: c, label: countryLabel(c) }))}
          />
          <FilterSelect
            value={status}
            onChange={setStatus}
            placeholder="Status"
            options={(["critical", "watch", "healthy"] as Status[]).map((s) => ({
              value: s,
              label: STATUS_LABEL[s],
            }))}
          />
        </div>
      </div>

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b text-left text-[11px] uppercase tracking-wider text-muted-foreground">
              <th className="px-4 py-2.5 font-semibold">Machine</th>
              <th className="px-4 py-2.5 font-semibold">Model</th>
              <th className="px-4 py-2.5 font-semibold">Site</th>
              <th className="px-4 py-2.5 font-semibold">7-day risk</th>
              <th className="px-4 py-2.5 font-semibold">Status</th>
              <th className="px-4 py-2.5 font-semibold">Likely issue</th>
              <th className="px-4 py-2.5"></th>
            </tr>
          </thead>
          <tbody>
            {rows.map((m) => (
              <tr
                key={m.id}
                className="group border-b last:border-0 transition-colors hover:bg-accent/40"
              >
                <td className="px-4 py-2.5">
                  <Link href={`/machines/${m.id}`} className="font-mono text-[13px] font-medium hover:text-primary">
                    {m.id}
                  </Link>
                </td>
                <td className="px-4 py-2.5 text-muted-foreground">{m.model}</td>
                <td className="px-4 py-2.5">
                  <div className="leading-tight">
                    <div>{m.hospital}</div>
                    <div className="text-xs text-muted-foreground">{countryLabel(m.country)}</div>
                  </div>
                </td>
                <td className="px-4 py-2.5">
                  <div className="flex items-center gap-2">
                    <div className="h-1.5 w-16 overflow-hidden rounded-full bg-muted">
                      <div
                        className={cn("h-full rounded-full", RISK_BAR(m.risk))}
                        style={{ width: `${Math.min(m.risk / 0.45, 1) * 100}%` }}
                      />
                    </div>
                    <span className="tnum font-medium">{riskPct(m.risk)}</span>
                  </div>
                </td>
                <td className="px-4 py-2.5">
                  <StatusPill status={m.status} />
                </td>
                <td className="px-4 py-2.5 text-muted-foreground">{m.likelyIssue}</td>
                <td className="px-4 py-2.5 text-right">
                  <Link
                    href={`/machines/${m.id}`}
                    className="inline-flex items-center text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100"
                    aria-label={`Open ${m.id}`}
                  >
                    <ChevronRight className="size-4" />
                  </Link>
                </td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={7} className="px-4 py-10 text-center text-muted-foreground">
                  No machines match these filters.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function FilterSelect({
  value,
  onChange,
  placeholder,
  options,
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder: string;
  options: { value: string; label: string }[];
}) {
  return (
    <Select value={value} onValueChange={(v) => onChange(v ?? "all")}>
      <SelectTrigger className="h-9 w-[130px]" size="sm">
        <SelectValue placeholder={placeholder} />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value="all">All {placeholder.toLowerCase()}s</SelectItem>
        {options.map((o) => (
          <SelectItem key={o.value} value={o.value}>
            {o.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
