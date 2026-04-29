import { Badge } from "@/components/ui/badge";

const COLORS: Record<string, string> = {
  filesystem: "border-zinc-600   bg-zinc-500/15   text-zinc-300",
  hubspot:    "border-orange-600 bg-orange-500/15 text-orange-300",
  salesforce: "border-sky-600    bg-sky-500/15    text-sky-300",
};

export function ExportDestinationBadge({ destination }: { destination?: string | null }) {
  const d = (destination || "filesystem").toLowerCase();
  const cls = COLORS[d] || COLORS.filesystem;
  return (
    <Badge variant="outline" className={`border ${cls} font-mono text-[10px] uppercase`}>
      {d}
    </Badge>
  );
}
