import type { FunnelStep } from "@/lib/api";

const STAGES: { key: keyof FunnelStep; label: string; color: string }[] = [
  { key: "discovered", label: "Discovered", color: "bg-zinc-500/40" },
  { key: "scored",     label: "Scored",     color: "bg-sky-500/40" },
  { key: "approved",   label: "Approved",   color: "bg-indigo-500/40" },
  { key: "sent",       label: "Sent",       color: "bg-blue-500/40" },
  { key: "opened",     label: "Opened",     color: "bg-emerald-500/40" },
  { key: "replied",    label: "Replied",    color: "bg-violet-500/40" },
  { key: "positive",   label: "Positive",   color: "bg-fuchsia-500/40" },
];

export function FunnelChart({ funnel }: { funnel: FunnelStep }) {
  const max = Math.max(1, ...STAGES.map((s) => funnel[s.key] || 0));
  return (
    <div className="space-y-1.5">
      {STAGES.map((s, i) => {
        const v = funnel[s.key] || 0;
        const pct = (v / max) * 100;
        const prev = i === 0 ? null : funnel[STAGES[i - 1].key] || 0;
        const conv = prev && prev > 0 ? ((v / prev) * 100).toFixed(1) + "%" : "—";
        return (
          <div key={s.key} className="space-y-0.5">
            <div className="flex justify-between text-xs">
              <span className="text-muted-foreground">{s.label}</span>
              <span className="font-mono">
                {v}
                <span className="text-muted-foreground ml-2">{conv}</span>
              </span>
            </div>
            <div className="h-3 bg-zinc-900/50 rounded overflow-hidden">
              <div
                className={`h-full ${s.color}`}
                style={{ width: `${pct}%` }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}
