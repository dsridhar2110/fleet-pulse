"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Activity, HardDrive, Radar, ClipboardCheck, TrendingUp, GitBranch } from "lucide-react";

const NAV = [
  { href: "/", label: "Model & Governance", icon: GitBranch },
  { href: "/machines", label: "Machines", icon: HardDrive },
  { href: "/predictions", label: "Predictions", icon: Radar },
  { href: "/decisions", label: "Decisions", icon: ClipboardCheck },
  { href: "/economics", label: "Economics", icon: TrendingUp },
  { href: "/overview", label: "Business Overview", icon: Activity },
];

export function Sidebar() {
  const path = usePathname();
  return (
    <aside className="sidebar">
      <div className="brand">
        <div className="brand-mark">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
            <path d="M3 12h4l2 6 4-14 2 8h6" />
          </svg>
        </div>
        <div>
          <div className="brand-name">Fleet Pulse</div>
          <div className="brand-sub">SERVICE COMMAND</div>
        </div>
      </div>

      <div className="nav-label">Command Center</div>
      {NAV.map(({ href, label, icon: Icon }) => {
        const active = href === "/" ? path === "/" : path.startsWith(href);
        return (
          <Link key={href} href={href} className={`nav-item${active ? " active" : ""}`}>
            <Icon className="nav-ico" />
            <span>{label}</span>
          </Link>
        );
      })}

      <div className="sidebar-foot">
        Independent portfolio project.<br />All data synthetic — not affiliated with any manufacturer.
      </div>
    </aside>
  );
}
