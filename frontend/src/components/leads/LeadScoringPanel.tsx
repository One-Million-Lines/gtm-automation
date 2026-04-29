import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Award, RefreshCw, TrendingUp, Target } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  leadsApi,
  type LeadScoringDetail,
  type PriorityTier,
} from "@/lib/api";

const TIER_COLORS: Record<PriorityTier, string> = {
  A: "bg-emerald-500/20 text-emerald-300 border-emerald-600",
  B: "bg-sky-500/20 text-sky-300 border-sky-600",
  C: "bg-amber-500/20 text-amber-300 border-amber-600",
  D: "bg-zinc-500/20 text-zinc-300 border-zinc-600",
};

export function TierBadge({ tier }: { tier: PriorityTier | null | undefined }) {
  if (!tier) {
    return (
      <Badge variant="outline" className="border-border/40 text-muted-foreground">
        unscored
      </Badge>
    );
  }
  return (
    <Badge variant="outline" className={`border ${TIER_COLORS[tier]} font-mono`}>
      {tier}
    </Badge>
  );
}

function ScoreBar({
  value, label, color = "bg-emerald-500",
}: { value: number | null | undefined; label: string; color?: string }) {
  const v = Math.max(0, Math.min(1, value ?? 0));
  const pct = Math.round(v * 100);
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-[11px]">
        <span className="text-muted-foreground uppercase">{label}</span>
        <span className="font-mono">{pct}%</span>
      </div>
      <div className="bg-muted h-1.5 overflow-hidden rounded">
        <div className={`h-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

export function LeadScoringPanel({ leadId }: { leadId: number | null | undefined }) {
  const qc = useQueryClient();
  const enabled = !!leadId;

  const { data, isLoading } = useQuery({
    queryKey: ["lead-scoring", leadId],
    queryFn: () => leadsApi.getScoring(leadId!),
    enabled,
    staleTime: 10_000,
  });

  const rescore = useMutation({
    mutationFn: () => leadsApi.scoreLead(leadId!),
    onSuccess: (res) => {
      if (res.ok) {
        toast.success(
          `Scored: tier ${res.priority_tier} (${((res.combined_score ?? 0) * 100).toFixed(0)}%)`,
        );
      } else {
        toast.error(res.error || "score failed");
      }
      qc.invalidateQueries({ queryKey: ["lead-scoring", leadId] });
      qc.invalidateQueries({ queryKey: ["leads"] });
    },
    onError: (e: unknown) => toast.error((e as Error)?.message ?? "score failed"),
  });

  if (!enabled) return null;

  const expl = data?.scoring_explanation ?? null;
  const fitCriteria = expl?.fit?.criteria ?? {};
  const matched = expl?.fit?.matched ?? [];
  const missed = expl?.fit?.missed ?? [];
  const contribs = expl?.intent?.contributions ?? [];

  return (
    <div className="border-border/40 space-y-3 rounded border p-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-sm font-medium">
          <Award className="h-4 w-4 text-emerald-400" />
          Lead Scoring
          <TierBadge tier={data?.priority_tier ?? null} />
        </div>
        <Button
          size="sm"
          variant="outline"
          onClick={() => rescore.mutate()}
          disabled={rescore.isPending}
        >
          <RefreshCw className={`mr-1 h-3 w-3 ${rescore.isPending ? "animate-spin" : ""}`} />
          Re-score
        </Button>
      </div>

      {isLoading ? (
        <div className="text-muted-foreground text-xs">Loading…</div>
      ) : !data || data.combined_score == null ? (
        <div className="text-muted-foreground text-xs">
          Not scored yet. Click Re-score to compute.
        </div>
      ) : (
        <>
          <div className="grid grid-cols-3 gap-3">
            <ScoreBar label="fit" value={data.fit_score} color="bg-sky-500" />
            <ScoreBar label="intent" value={data.intent_score} color="bg-fuchsia-500" />
            <ScoreBar label="combined" value={data.combined_score} color="bg-emerald-500" />
          </div>

          {data.scored_at && (
            <div className="text-muted-foreground text-[10px]">
              scored at {data.scored_at} · scorer={expl?.scorer ?? "—"}
            </div>
          )}

          {Object.keys(fitCriteria).length > 0 && (
            <div className="space-y-1">
              <div className="text-muted-foreground flex items-center gap-1 text-[11px] uppercase">
                <Target className="h-3 w-3" /> Fit criteria
              </div>
              <ul className="space-y-1">
                {Object.entries(fitCriteria).map(([key, info]) => {
                  const m = !!info?.matched;
                  return (
                    <li
                      key={key}
                      className="flex items-center justify-between rounded border border-border/40 bg-muted/20 px-2 py-1 text-[11px]"
                    >
                      <span className="flex items-center gap-1.5">
                        <span
                          className={`inline-block h-2 w-2 rounded-full ${
                            m ? "bg-emerald-500" : "bg-zinc-600"
                          }`}
                        />
                        <span className="font-mono">{key}</span>
                        {info?.weight != null && (
                          <span className="text-muted-foreground">·w{(info.weight as number).toFixed(2)}</span>
                        )}
                      </span>
                      <span className={m ? "text-emerald-300" : "text-zinc-500"}>
                        {m ? "matched" : "missed"}
                        {info?.reason ? ` (${info.reason})` : ""}
                      </span>
                    </li>
                  );
                })}
              </ul>
              <div className="text-muted-foreground text-[10px]">
                matched: {matched.join(", ") || "—"} · missed: {missed.join(", ") || "—"}
              </div>
            </div>
          )}

          {contribs.length > 0 && (
            <div className="space-y-1">
              <div className="text-muted-foreground flex items-center gap-1 text-[11px] uppercase">
                <TrendingUp className="h-3 w-3" /> Signal contributions
              </div>
              <ul className="space-y-1">
                {contribs.map((c, i) => (
                  <li
                    key={`${c.signal_id ?? i}-${c.signal_type}`}
                    className="flex items-center justify-between rounded border border-border/40 bg-muted/20 px-2 py-1 text-[11px]"
                  >
                    <span className="font-mono">{c.signal_type ?? "—"}</span>
                    <span className="text-muted-foreground tabular-nums">
                      w{(c.weight ?? 0).toFixed(2)} · s{(c.strength ?? 0).toFixed(2)} · r
                      {(c.recency ?? 0).toFixed(2)} ={" "}
                      <span className="text-emerald-300">
                        {(c.contribution ?? 0).toFixed(3)}
                      </span>
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}
    </div>
  );
}
