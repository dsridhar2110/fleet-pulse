import React from "react";
import { AdvanceButton } from "./advance-button";

export function fmtMoney(n: number, cents = false): string {
  const a = Math.abs(n);
  if (a >= 1e9) return `$${(n / 1e9).toFixed(2)}B`;
  if (a >= 1e6) return `$${(n / 1e6).toFixed(2)}M`;
  if (a >= 1e3) return `$${(n / 1e3).toFixed(a >= 1e5 ? 0 : 1)}k`;
  return `$${n.toFixed(cents ? 2 : 0)}`;
}
export const fmtNum = (n: number) => n.toLocaleString("en-US");
export const fmtPct = (n: number, d = 0) => `${(n * 100).toFixed(d)}%`;
export const fmtDate = (s: string) =>
  new Date(s + (s.length === 10 ? "T00:00:00" : "")).toLocaleDateString("en-US", {
    day: "numeric", month: "short", year: "numeric",
  });

export function Topbar({ title, currentDate }: { title: string; currentDate: string }) {
  return (
    <header className="topbar">
      <div>
        <div className="crumb">FLEET PULSE / {title.toUpperCase()}</div>
        <h1>{title}</h1>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
        {process.env.ALLOW_TICK === "1" && <AdvanceButton />}
        <div className="clock">
          <span className="dot" />
          Live · as of&nbsp;<b>{currentDate ? fmtDate(currentDate) : "—"}</b>
        </div>
      </div>
    </header>
  );
}

export function Stat({
  label, value, foot, tone,
}: {
  label: string; value: React.ReactNode; foot?: React.ReactNode;
  tone?: "data" | "primary" | "default";
}) {
  const cls = tone === "data" ? "stat-value accent-data" : tone === "primary" ? "stat-value accent-primary" : "stat-value";
  return (
    <div className="card">
      <div className="stat-label">{label}</div>
      <div className={cls}>{value}</div>
      {foot && <div className="stat-foot">{foot}</div>}
    </div>
  );
}

export function Pill({ band, children }: { band: "critical" | "watch" | "healthy"; children?: React.ReactNode }) {
  return <span className={`pill pill-${band}`}>{children ?? band}</span>;
}

export function SectionHeading({ eyebrow, title, sub }: { eyebrow?: string; title: string; sub?: string }) {
  return (
    <div style={{ marginBottom: 16 }}>
      {eyebrow && <div className="eyebrow" style={{ marginBottom: 8 }}>{eyebrow}</div>}
      <h2 style={{ fontSize: "1.2rem", fontWeight: 640, letterSpacing: "-0.01em" }}>{title}</h2>
      {sub && <p className="muted" style={{ fontSize: "0.86rem", marginTop: 4 }}>{sub}</p>}
    </div>
  );
}
