import { cn } from "@/lib/utils";
import type { RevisionStatus } from "@/lib/api";

const STYLES: Record<RevisionStatus, string> = {
  proposed: "bg-amber-500/15 text-amber-300 border-amber-500/30",
  active: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30",
  archived: "bg-zinc-500/15 text-zinc-300 border-zinc-500/30",
  rejected: "bg-rose-500/15 text-rose-300 border-rose-500/30",
};

export function RevisionStatusBadge({ status }: { status: string }) {
  const cls = STYLES[status as RevisionStatus] ?? "bg-zinc-500/15 text-zinc-300 border-zinc-500/30";
  return (
    <span className={cn("rounded border px-2 py-0.5 text-xs font-medium uppercase tracking-wide", cls)}>
      {status}
    </span>
  );
}
