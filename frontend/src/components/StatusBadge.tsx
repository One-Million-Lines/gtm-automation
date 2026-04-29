import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

const COLORS: Record<string, string> = {
  completed: "bg-green-600/20 text-green-300 border-green-600/40",
  partially_completed: "bg-amber-500/20 text-amber-200 border-amber-500/40",
  failed: "bg-red-600/20 text-red-300 border-red-600/40",
  running: "bg-blue-600/20 text-blue-300 border-blue-600/40",
  skipped: "bg-zinc-600/20 text-zinc-300 border-zinc-600/40",
  active: "bg-green-600/20 text-green-300 border-green-600/40",
  draft: "bg-zinc-500/20 text-zinc-200 border-zinc-500/40",
  archived: "bg-zinc-700/30 text-zinc-400 border-zinc-700/50",
};

export function StatusBadge({ status }: { status: string }) {
  return (
    <Badge variant="outline" className={cn("border", COLORS[status] || "")}>
      {status}
    </Badge>
  );
}
