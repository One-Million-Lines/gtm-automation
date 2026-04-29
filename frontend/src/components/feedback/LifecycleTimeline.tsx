import type { LifecycleTransition } from "@/lib/api";
import { LifecycleStageBadge } from "./LifecycleStageBadge";

export function LifecycleTimeline({
  transitions,
}: {
  transitions: LifecycleTransition[];
}) {
  if (!transitions.length) {
    return <p className="text-sm text-zinc-400">No lifecycle transitions yet.</p>;
  }
  return (
    <ol className="space-y-3 border-l border-zinc-700 pl-4">
      {transitions.map((t) => (
        <li key={t.id} className="relative">
          <span className="absolute -left-5.25 top-1 h-2 w-2 rounded-full bg-violet-500" />
          <div className="flex flex-wrap items-center gap-2">
            {t.from_status && (
              <>
                <LifecycleStageBadge stage={t.from_status} />
                <span className="text-zinc-500">→</span>
              </>
            )}
            <LifecycleStageBadge stage={t.to_status} />
            {t.source && (
              <span className="text-[10px] uppercase text-zinc-500">{t.source}</span>
            )}
          </div>
          {t.reason && (
            <p className="mt-1 text-xs text-zinc-400">{t.reason}</p>
          )}
          <p className="mt-1 font-mono text-[10px] text-zinc-500">
            {(t.created_at || "").slice(0, 19).replace("T", " ")}
          </p>
        </li>
      ))}
    </ol>
  );
}
