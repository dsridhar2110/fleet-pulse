import { cn } from "@/lib/utils";
import type { Status } from "@/lib/types";
import { STATUS_LABEL } from "@/lib/format";

const STYLES: Record<Status, string> = {
  critical: "bg-critical/12 text-critical",
  watch: "bg-watch/14 text-watch",
  healthy: "bg-healthy/12 text-healthy",
};

const DOT: Record<Status, string> = {
  critical: "bg-critical",
  watch: "bg-watch",
  healthy: "bg-healthy",
};

export function StatusPill({ status, className }: { status: Status; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-semibold whitespace-nowrap",
        STYLES[status],
        className,
      )}
    >
      <span className={cn("size-1.5 rounded-full", DOT[status])} />
      {STATUS_LABEL[status]}
    </span>
  );
}
