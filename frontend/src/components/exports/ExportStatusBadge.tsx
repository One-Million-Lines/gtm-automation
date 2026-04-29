import { Badge } from "@/components/ui/badge";

const STATUS_COLORS: Record<string, string> = {
  pending:   "border-zinc-600    bg-zinc-500/15    text-zinc-300",
  building:  "border-sky-600     bg-sky-500/15     text-sky-300",
  ready:     "border-violet-600  bg-violet-500/15  text-violet-300",
  delivered: "border-emerald-600 bg-emerald-500/15 text-emerald-300",
  failed:    "border-rose-600    bg-rose-500/15    text-rose-300",
};

export function ExportStatusBadge({ status }: { status?: string | null }) {
  const s = (status || "pending").toLowerCase();
  const cls = STATUS_COLORS[s] || STATUS_COLORS.pending;
  return (
    <Badge variant="outline" className={`border ${cls} font-mono text-[10px] uppercase`}>
      {s}
    </Badge>
  );
}
