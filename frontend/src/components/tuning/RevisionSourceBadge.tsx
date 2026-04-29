import { cn } from "@/lib/utils";
import type { RevisionSource } from "@/lib/api";

const STYLES: Record<RevisionSource, string> = {
  manual: "bg-zinc-500/15 text-zinc-300 border-zinc-500/30",
  auto_tune: "bg-violet-500/15 text-violet-300 border-violet-500/30",
  rollback: "bg-sky-500/15 text-sky-300 border-sky-500/30",
};

export function RevisionSourceBadge({ source }: { source: string }) {
  const cls = STYLES[source as RevisionSource] ?? "bg-zinc-500/15 text-zinc-300 border-zinc-500/30";
  return (
    <span className={cn("rounded border px-2 py-0.5 text-xs font-medium", cls)}>
      {source}
    </span>
  );
}
