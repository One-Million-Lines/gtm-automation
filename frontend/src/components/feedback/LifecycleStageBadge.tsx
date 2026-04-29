import { Badge } from "@/components/ui/badge";
import type { LifecycleStage } from "@/lib/api";

const STAGE_COLORS: Record<string, string> = {
  new:            "border-zinc-600    bg-zinc-500/15    text-zinc-300",
  contacted:      "border-sky-600     bg-sky-500/15     text-sky-300",
  engaged:        "border-violet-600  bg-violet-500/15  text-violet-300",
  qualified:      "border-amber-600   bg-amber-500/15   text-amber-300",
  meeting_booked: "border-cyan-600    bg-cyan-500/15    text-cyan-300",
  won:            "border-emerald-700 bg-emerald-600/20 text-emerald-200",
  lost:           "border-rose-700    bg-rose-600/20    text-rose-200",
  unsubscribed:   "border-orange-600  bg-orange-500/15  text-orange-300",
  disqualified:   "border-stone-600   bg-stone-500/15   text-stone-300",
};

export function LifecycleStageBadge({ stage }: { stage?: LifecycleStage | string | null }) {
  const s = String(stage || "new").toLowerCase();
  const cls = STAGE_COLORS[s] || STAGE_COLORS.new;
  return (
    <Badge variant="outline" className={`border ${cls} font-mono text-[10px] uppercase`}>
      {s.replace(/_/g, " ")}
    </Badge>
  );
}
