"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import { Activity, LayoutDashboard, LineChart, MessageSquareText } from "lucide-react";

const NAV = [
  { href: "/", label: "Command Center", icon: LayoutDashboard },
  { href: "/model", label: "Model & Evaluation", icon: LineChart },
  { href: "/assistant", label: "Service Assistant", icon: MessageSquareText },
];

export function AppShell({ asOf, children }: { asOf: string; children: React.ReactNode }) {
  const pathname = usePathname();

  return (
    <div className="flex min-h-screen">
      {/* Sidebar */}
      <aside className="hidden w-60 shrink-0 flex-col bg-sidebar text-sidebar-foreground md:flex">
        <div className="flex items-center gap-2.5 px-5 py-5">
          <span className="flex size-8 items-center justify-center rounded-md bg-sidebar-primary/15 text-sidebar-primary">
            <Activity className="size-5" strokeWidth={2.4} />
          </span>
          <div className="leading-tight">
            <div className="text-sm font-bold tracking-wide text-white">Fleet Pulse</div>
            <div className="text-[10px] uppercase tracking-[0.16em] text-sidebar-foreground/60">
              Service Intelligence
            </div>
          </div>
        </div>

        <nav className="flex flex-col gap-1 px-3 py-2">
          {NAV.map(({ href, label, icon: Icon }) => {
            const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
            return (
              <Link
                key={href}
                href={href}
                className={cn(
                  "flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors",
                  active
                    ? "bg-sidebar-accent text-white font-medium"
                    : "text-sidebar-foreground/80 hover:bg-sidebar-accent/60 hover:text-white",
                )}
              >
                <Icon className="size-4" />
                {label}
              </Link>
            );
          })}
        </nav>

        <div className="mt-auto px-5 py-4 text-[11px] leading-relaxed text-sidebar-foreground/50">
          Independent portfolio demo. Not affiliated with Siemens Healthineers. Synthetic data.
        </div>
      </aside>

      {/* Main */}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-20 flex h-14 items-center justify-between border-b bg-card/95 px-5 backdrop-blur md:px-8">
          <div className="flex items-center gap-2 md:hidden">
            <Activity className="size-5 text-primary" strokeWidth={2.4} />
            <span className="font-bold">Fleet Pulse</span>
          </div>
          <div className="hidden text-sm text-muted-foreground md:block">
            Predictive service intelligence for a simulated imaging fleet
          </div>
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <span className="size-2 animate-pulse rounded-full bg-healthy" />
            <span className="tnum">Fleet as of {asOf}</span>
          </div>
        </header>
        <main className="flex-1 px-5 py-6 md:px-8 md:py-8">{children}</main>
      </div>
    </div>
  );
}
