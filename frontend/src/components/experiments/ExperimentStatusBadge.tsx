import { Badge } from "@/components/ui/badge";

const STATUS_COLORS: Record<string, string> = {
  draft:     "border-zinc-600    bg-zinc-500/15    text-zinc-300",
  running:   "border-emerald-600 bg-emerald-500/15 text-emerald-300",
  paused:    "border-amber-600   bg-amber-500/15   text-amber-200",
  completed: "border-violet-600  bg-violet-500/15  text-violet-300",
  archived:  "border-zinc-700    bg-zinc-700/30    text-zinc-400",
};

export function ExperimentStatusBadge({ status }: { status?: string | null }) {
  const s = (status || "draft").toLowerCase();
  const cls = STATUS_COLORS[s] || STATUS_COLORS.draft;
  return (
    <Badge variant="outline" className={`border ${cls} font-mono text-[10px] uppercase`}>
      {s}
    </Badge>
  );
}
