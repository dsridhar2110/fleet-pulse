// Bespoke SVG charts — pure server-rendered functions (no client JS, no chart
// library). Kept small and on-theme; every color comes from the design tokens.
import React from "react";

const W = 640;

function smoothPath(pts: [number, number][]): string {
  if (pts.length < 2) return "";
  let d = `M ${pts[0][0]},${pts[0][1]}`;
  for (let i = 1; i < pts.length; i++) {
    const [x0, y0] = pts[i - 1], [x1, y1] = pts[i];
    const cx = (x0 + x1) / 2;
    d += ` C ${cx},${y0} ${cx},${y1} ${x1},${y1}`;
  }
  return d;
}

/** Filled area + line for a single series. */
export function AreaChart({
  values, height = 150, color = "var(--data)", id,
}: { values: number[]; height?: number; color?: string; id: string }) {
  if (!values.length) return null;
  const H = height;
  const lo = Math.min(...values), hi = Math.max(...values);
  const span = hi - lo || 1;
  const pad = 10;
  const pts = values.map((v, i) => [
    (i / (values.length - 1 || 1)) * W,
    pad + (1 - (v - lo) / span) * (H - pad * 2),
  ] as [number, number]);
  const line = smoothPath(pts);
  const area = `${line} L ${W},${H} L 0,${H} Z`;
  const last = pts[pts.length - 1];
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" height={H} preserveAspectRatio="none" style={{ display: "block" }}>
      <defs>
        <linearGradient id={`g-${id}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.34" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      {[0.25, 0.5, 0.75].map((f) => (
        <line key={f} x1="0" x2={W} y1={H * f} y2={H * f} stroke="var(--border)" strokeWidth="1" strokeDasharray="3 5" opacity="0.5" />
      ))}
      <path d={area} fill={`url(#g-${id})`} />
      <path d={line} fill="none" stroke={color} strokeWidth="2.4" vectorEffect="non-scaling-stroke" />
      <circle cx={last[0]} cy={last[1]} r="3.5" fill={color} />
    </svg>
  );
}

/** Stacked area for the health trend (healthy / watch / critical). */
export function StackedArea({
  series, height = 190,
}: { series: { name: string; color: string; values: number[] }[]; height?: number }) {
  const n = series[0]?.values.length ?? 0;
  if (!n) return null;
  const H = height;
  const totals = Array.from({ length: n }, (_, i) => series.reduce((s, ser) => s + ser.values[i], 0));
  const max = Math.max(...totals) || 1;
  let base = new Array(n).fill(0);
  const layers = series.map((ser) => {
    const top = base.map((b, i) => b + ser.values[i]);
    const topPts = top.map((v, i) => [(i / (n - 1 || 1)) * W, (1 - v / max) * H] as [number, number]);
    const botPts = base.map((v, i) => [(i / (n - 1 || 1)) * W, (1 - v / max) * H] as [number, number]).reverse();
    const path = `M ${topPts.map((p) => p.join(",")).join(" L ")} L ${botPts.map((p) => p.join(",")).join(" L ")} Z`;
    base = top;
    return { path, color: ser.color };
  });
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" height={H} preserveAspectRatio="none" style={{ display: "block" }}>
      {layers.map((l, i) => <path key={i} d={l.path} fill={l.color} fillOpacity="0.82" />)}
    </svg>
  );
}

/** Donut with a centered label. */
export function Donut({
  items, size = 168, label, sub,
}: { items: { value: number; color: string }[]; size?: number; label?: string; sub?: string }) {
  const total = items.reduce((s, x) => s + x.value, 0) || 1;
  const r = size / 2 - 12, cx = size / 2, cy = size / 2, C = 2 * Math.PI * r;
  let offset = 0;
  return (
    <div style={{ position: "relative", width: size, height: size }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} style={{ transform: "rotate(-90deg)" }}>
        <circle cx={cx} cy={cy} r={r} fill="none" stroke="var(--surface-3)" strokeWidth="12" />
        {items.map((it, i) => {
          const frac = it.value / total;
          const dash = `${frac * C} ${C}`;
          const el = (
            <circle key={i} cx={cx} cy={cy} r={r} fill="none" stroke={it.color} strokeWidth="12"
              strokeDasharray={dash} strokeDashoffset={-offset * C} strokeLinecap="round" />
          );
          offset += frac;
          return el;
        })}
      </svg>
      {label && (
        <div style={{ position: "absolute", inset: 0, display: "grid", placeItems: "center", textAlign: "center" }}>
          <div>
            <div style={{ fontSize: "1.7rem", fontWeight: 700, letterSpacing: "-0.02em", fontVariantNumeric: "tabular-nums" }}>{label}</div>
            {sub && <div className="muted" style={{ fontSize: "0.72rem" }}>{sub}</div>}
          </div>
        </div>
      )}
    </div>
  );
}

/** Tiny inline survival curve (5 horizon points). */
export function Spark({ values, width = 92, height = 28, color = "var(--primary)" }: { values: number[]; width?: number; height?: number; color?: string }) {
  if (!values.length) return null;
  const lo = 0, hi = 1;
  const pts = values.map((v, i) => [(i / (values.length - 1 || 1)) * width, height - 3 - ((v - lo) / (hi - lo)) * (height - 6)] as [number, number]);
  const line = smoothPath(pts);
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} style={{ display: "block" }}>
      <path d={`${line} L ${width},${height} L 0,${height} Z`} fill={color} fillOpacity="0.14" />
      <path d={line} fill="none" stroke={color} strokeWidth="1.6" />
      <circle cx={pts[pts.length - 1][0]} cy={pts[pts.length - 1][1]} r="2.2" fill={color} />
    </svg>
  );
}

/** Multi-line chart (model metric trajectory across versions). */
export function MultiLine({
  series, labels, height = 200,
}: { series: { name: string; color: string; values: number[] }[]; labels: string[]; height?: number }) {
  const n = labels.length;
  const all = series.flatMap((s) => s.values);
  const lo = Math.min(...all) * 0.9, hi = Math.max(...all) * 1.05;
  const span = hi - lo || 1;
  const H = height, pad = 16;
  const xy = (v: number, i: number) => [(i / (n - 1 || 1)) * (W - 20) + 10, pad + (1 - (v - lo) / span) * (H - pad * 2)] as [number, number];
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" height={H} preserveAspectRatio="none" style={{ display: "block" }}>
      {[0, 0.5, 1].map((f) => (
        <line key={f} x1="0" x2={W} y1={pad + f * (H - pad * 2)} y2={pad + f * (H - pad * 2)} stroke="var(--border)" strokeDasharray="3 5" opacity="0.5" />
      ))}
      {series.map((s, si) => {
        const pts = s.values.map((v, i) => xy(v, i));
        return (
          <g key={si}>
            <path d={smoothPath(pts)} fill="none" stroke={s.color} strokeWidth="2.4" vectorEffect="non-scaling-stroke" />
            {pts.map((p, i) => <circle key={i} cx={p[0]} cy={p[1]} r="3" fill={s.color} />)}
          </g>
        );
      })}
    </svg>
  );
}
