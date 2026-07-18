const LINKS = [
  { href: "#problem", label: "The problem" },
  { href: "#data", label: "The data" },
  { href: "#module-1", label: "Failure prediction" },
  { href: "#module-2", label: "Anomaly detection" },
  { href: "#module-3", label: "Engineer copilot" },
  { href: "#stack", label: "The stack" },
  { href: "#next", label: "What I'd build next" },
];

export function Nav() {
  return (
    <nav
      aria-label="Sections"
      className="sticky top-0 z-20 border-b border-white/10 bg-ground/95 backdrop-blur"
    >
      <div className="mx-auto w-full max-w-5xl px-6">
        <ul className="-mx-1.5 flex items-center gap-1 overflow-x-auto py-2.5 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
          {LINKS.map((l) => (
            <li key={l.href} className="shrink-0">
              <a
                href={l.href}
                className="block whitespace-nowrap rounded-md px-3.5 py-2 text-base font-medium text-teal-bright/85 transition-colors hover:bg-white/10 hover:text-teal-bright"
              >
                {l.label}
              </a>
            </li>
          ))}
        </ul>
      </div>
    </nav>
  );
}
