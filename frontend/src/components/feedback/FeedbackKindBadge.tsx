import { Badge } from "@/components/ui/badge";
import type { FeedbackKind } from "@/lib/api";

const KIND_COLORS: Record<string, string> = {
  thumbs_up:         "border-emerald-600 bg-emerald-500/15 text-emerald-300",
  thumbs_down:       "border-rose-600    bg-rose-500/15    text-rose-300",
  lead_qualified:    "border-violet-600  bg-violet-500/15  text-violet-300",
  lead_disqualified: "border-zinc-600    bg-zinc-500/15    text-zinc-300",
  meeting_booked:    "border-sky-600     bg-sky-500/15     text-sky-300",
  won:               "border-emerald-700 bg-emerald-600/20 text-emerald-200",
  lost:              "border-rose-700    bg-rose-600/20    text-rose-200",
  unsubscribe:       "border-amber-600   bg-amber-500/15   text-amber-300",
  note:              "border-zinc-600    bg-zinc-500/10    text-zinc-300",
};

export function FeedbackKindBadge({ kind }: { kind: FeedbackKind | string }) {
  const k = String(kind).toLowerCase();
  const cls = KIND_COLORS[k] || KIND_COLORS.note;
  return (
    <Badge variant="outline" className={`border ${cls} font-mono text-[10px] uppercase`}>
      {k.replace(/_/g, " ")}
    </Badge>
  );
}
