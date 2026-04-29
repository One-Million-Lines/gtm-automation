import { REPLY_INTENTS, type ReplyIntent } from "@/lib/api";

const INTENT_BAR: Record<ReplyIntent, string> = {
  positive:     "bg-emerald-500/60",
  negative:     "bg-rose-500/60",
  oof:          "bg-amber-500/60",
  unsubscribe:  "bg-fuchsia-500/60",
  info_request: "bg-sky-500/60",
  neutral:      "bg-zinc-500/60",
};

export function IntentBreakdown({ byIntent }: { byIntent: Record<string, number> }) {
  const total = REPLY_INTENTS.reduce((s, k) => s + (byIntent[k] || 0), 0);
  if (total === 0) {
    return (
      <div className="text-xs text-muted-foreground">no replies yet</div>
    );
  }
  return (
    <div className="space-y-1.5">
      {REPLY_INTENTS.map((k) => {
        const v = byIntent[k] || 0;
        const pct = total > 0 ? (v / total) * 100 : 0;
        return (
          <div key={k} className="space-y-0.5">
            <div className="flex justify-between text-xs">
              <span className="text-muted-foreground capitalize">{k.replace("_", " ")}</span>
              <span className="font-mono">
                {v}
                <span className="text-muted-foreground ml-2">{pct.toFixed(0)}%</span>
              </span>
            </div>
            <div className="h-2 bg-zinc-900/50 rounded overflow-hidden">
              <div className={`h-full ${INTENT_BAR[k]}`} style={{ width: `${pct}%` }} />
            </div>
          </div>
        );
      })}
    </div>
  );
}
