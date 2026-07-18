import React from "react";

/** Small hoverable "i" with a tooltip (CSS-only, SSR-safe). */
export function Info({ text }: { text: string }) {
  return (
    <span className="tip" tabIndex={0}>
      <span className="tip-i">i</span>
      <span className="tip-body">{text}</span>
    </span>
  );
}

/** A scannable technical annotation strip — "how this is computed", in DS language. */
export function MethodStrip({ label = "METHOD", children }: { label?: string; children: React.ReactNode }) {
  return (
    <div className="method-strip">
      <span className="method-tag">{label}</span>
      <div className="method-body">{children}</div>
    </div>
  );
}

/** Labels a metric with its DS rationale on hover. */
export function MetricNote({ children, text }: { children: React.ReactNode; text: string }) {
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 5 }}>
      {children}
      <Info text={text} />
    </span>
  );
}
