import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export function Section({
  id,
  eyebrow,
  title,
  lede,
  children,
  tone = "light",
}: {
  id: string;
  eyebrow: string;
  title: string;
  lede?: ReactNode;
  children: ReactNode;
  tone?: "light" | "muted";
}) {
  return (
    <section
      id={id}
      className={cn(
        "scroll-mt-16 border-b border-border py-16 sm:py-20",
        tone === "muted" && "bg-muted/40",
      )}
    >
      <div className="mx-auto w-full max-w-5xl px-6">
        <p className="text-[0.72rem] font-semibold uppercase tracking-[0.14em] text-primary">
          {eyebrow}
        </p>
        <h2 className="mt-3 text-3xl font-semibold tracking-tight sm:text-[2rem]">{title}</h2>
        {lede ? (
          <div className="mt-4 max-w-[68ch] text-lg leading-relaxed text-muted-foreground">
            {lede}
          </div>
        ) : null}
        <div className="mt-10">{children}</div>
      </div>
    </section>
  );
}

export function Stat({
  value,
  label,
  sub,
  tone = "default",
}: {
  value: string;
  label: string;
  sub?: string;
  tone?: "default" | "critical" | "healthy" | "onDark";
}) {
  return (
    <div
      className={cn(
        "rounded-lg border p-5",
        tone === "onDark"
          ? "border-white/10 bg-white/[0.04]"
          : "border-border bg-card",
      )}
    >
      <p
        className={cn(
          "tnum text-3xl font-semibold tracking-tight",
          tone === "critical" && "text-critical",
          tone === "healthy" && "text-healthy",
          tone === "onDark" && "text-teal-bright",
          tone === "default" && "text-foreground",
        )}
      >
        {value}
      </p>
      <p
        className={cn(
          "mt-2 text-[0.7rem] font-semibold uppercase tracking-[0.12em]",
          tone === "onDark" ? "text-white/60" : "text-muted-foreground",
        )}
      >
        {label}
      </p>
      {sub ? (
        <p className={cn("mt-2 text-sm leading-snug", tone === "onDark" ? "text-white/70" : "text-muted-foreground")}>
          {sub}
        </p>
      ) : null}
    </div>
  );
}

/** Horizontal bar list. Used for model comparison and SHAP drivers — no chart
 *  library, so nothing to break at build time and nothing to theme twice. */
export function Bars({
  items,
  max,
  format = (v) => v.toFixed(3),
  caption,
}: {
  items: { label: string; value: number; highlight?: boolean; note?: string }[];
  max?: number;
  format?: (v: number) => string;
  caption?: string;
}) {
  const ceiling = max ?? Math.max(...items.map((i) => i.value)) * 1.15;
  return (
    <figure className="rounded-lg border border-border bg-card p-6">
      <div className="flex flex-col gap-4">
        {items.map((item) => (
          <div key={item.label} className="grid grid-cols-[minmax(9rem,14rem)_1fr_auto] items-center gap-4">
            <span
              className={cn(
                "text-sm leading-tight",
                item.highlight ? "font-semibold text-foreground" : "text-muted-foreground",
              )}
            >
              {item.label}
              {item.note ? (
                <span className="block text-xs font-normal text-muted-foreground/80">{item.note}</span>
              ) : null}
            </span>
            <div className="h-3 overflow-hidden rounded-full bg-muted">
              <div
                className={cn("h-full rounded-full", item.highlight ? "bg-primary" : "bg-chart-4/60")}
                style={{ width: `${Math.max((item.value / ceiling) * 100, 0.6)}%` }}
              />
            </div>
            <span
              className={cn(
                "tnum w-16 text-right text-sm",
                item.highlight ? "font-semibold text-foreground" : "text-muted-foreground",
              )}
            >
              {format(item.value)}
            </span>
          </div>
        ))}
      </div>
      {caption ? (
        <figcaption className="mt-6 border-t border-border pt-4 text-sm leading-relaxed text-muted-foreground">
          {caption}
        </figcaption>
      ) : null}
    </figure>
  );
}

export function Figure({ src, alt, caption }: { src: string; alt: string; caption: string }) {
  return (
    <figure className="overflow-hidden rounded-lg border border-border bg-card">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={src} alt={alt} className="w-full" />
      <figcaption className="border-t border-border px-5 py-4 text-sm leading-relaxed text-muted-foreground">
        {caption}
      </figcaption>
    </figure>
  );
}

/** Dark petrol block for the takeaway that must not be missed. */
export function Callout({ children }: { children: ReactNode }) {
  return (
    <div className="rounded-lg bg-ground px-6 py-5 text-ground-foreground">
      <div className="max-w-[70ch] text-base leading-relaxed [&_strong]:text-teal-bright">{children}</div>
    </div>
  );
}

/** Amber-ruled box. Reserved for caveats, assumptions and honest limits. */
export function Note({ title, children }: { title?: string; children: ReactNode }) {
  return (
    <div className="rounded-r-lg border-l-[3px] border-watch bg-watch/[0.06] px-5 py-4">
      {title ? (
        <p className="text-[0.7rem] font-semibold uppercase tracking-[0.12em] text-watch">{title}</p>
      ) : null}
      <div className="mt-1.5 max-w-[70ch] text-sm leading-relaxed text-foreground/80">{children}</div>
    </div>
  );
}

export function Pill({ tone, children }: { tone: "crit" | "watch" | "ok" | "neutral"; children: ReactNode }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium",
        tone === "crit" && "bg-critical/10 text-critical",
        tone === "watch" && "bg-watch/10 text-watch",
        tone === "ok" && "bg-healthy/10 text-healthy",
        tone === "neutral" && "bg-muted text-muted-foreground",
      )}
    >
      {children}
    </span>
  );
}
