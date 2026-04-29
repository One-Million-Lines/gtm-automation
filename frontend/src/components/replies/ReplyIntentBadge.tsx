import { Badge } from "@/components/ui/badge";
import type { ReplyIntent } from "@/lib/api";

const INTENT_COLORS: Record<ReplyIntent, string> = {
  positive:     "border-emerald-600 bg-emerald-500/15 text-emerald-300",
  negative:     "border-rose-700    bg-rose-500/20    text-rose-200",
  oof:          "border-amber-600   bg-amber-500/15   text-amber-200",
  unsubscribe:  "border-fuchsia-700 bg-fuchsia-500/20 text-fuchsia-200",
  info_request: "border-sky-600     bg-sky-500/15     text-sky-300",
  neutral:      "border-zinc-600    bg-zinc-500/15    text-zinc-300",
};

export function ReplyIntentBadge({
  intent,
  confidence,
}: {
  intent: ReplyIntent | null | undefined;
  confidence?: number | null;
}) {
  if (!intent) {
    return (
      <Badge variant="outline" className="border-border/40 text-muted-foreground">
        none
      </Badge>
    );
  }
  return (
    <Badge variant="outline" className={`border ${INTENT_COLORS[intent]} font-mono text-[10px]`}>
      {intent}
      {typeof confidence === "number" ? ` ${confidence.toFixed(2)}` : ""}
    </Badge>
  );
}
