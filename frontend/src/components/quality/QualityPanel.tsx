import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { ShieldCheck, ShieldAlert, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { qualityApi, type QualityRuleResult } from "@/lib/api";

function ScoreBar({ score }: { score: number }) {
  const pct = Math.max(0, Math.min(1, score)) * 100;
  const color =
    score >= 0.8 ? "bg-emerald-500" : score >= 0.6 ? "bg-amber-500" : "bg-rose-500";
  return (
    <div className="bg-muted/30 border-border/40 h-1.5 w-full overflow-hidden rounded border">
      <div
        className={`h-full ${color} transition-all`}
        style={{ width: `${pct.toFixed(1)}%` }}
      />
    </div>
  );
}

export function RuleChip({ r }: { r: QualityRuleResult }) {
  const cls = r.passed
    ? "border-emerald-600 bg-emerald-500/15 text-emerald-300"
    : r.severity === "critical"
      ? "border-rose-700 bg-rose-500/20 text-rose-200"
      : "border-amber-700 bg-amber-500/15 text-amber-200";
  return (
    <TooltipProvider delayDuration={150}>
      <Tooltip>
      <TooltipTrigger asChild>
        <Badge
          variant="outline"
          className={`border font-mono text-[10px] ${cls} cursor-help`}
        >
          {r.passed ? "✓" : "✗"} {r.rule}
        </Badge>
      </TooltipTrigger>
      <TooltipContent side="top" className="max-w-xs">
        <div className="text-xs">
          <div className="font-semibold">
            {r.rule} — {r.passed ? "pass" : `fail (${r.severity ?? "info"})`}
          </div>
          <div className="text-muted-foreground mt-0.5">{r.reason}</div>
        </div>
      </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}

export function QualityPanel({
  messageId,
  onChecked,
}: {
  messageId: number | null | undefined;
  onChecked?: () => void;
}) {
  const qc = useQueryClient();
  const enabled = !!messageId;

  const q = useQuery({
    queryKey: ["quality", messageId],
    queryFn: () => qualityApi.getForMessage(messageId!),
    enabled,
    staleTime: 5_000,
  });

  const run = useMutation({
    mutationFn: () => qualityApi.check(messageId!),
    onSuccess: (res) => {
      if (res.ok) {
        toast.success(
          `Quality check ${res.passed ? "passed" : "failed"} (score ${res.score.toFixed(2)})`,
        );
        qc.invalidateQueries({ queryKey: ["quality", messageId] });
        qc.invalidateQueries({ queryKey: ["quality-list"] });
        onChecked?.();
      } else {
        toast.error(res.error || "quality check failed");
      }
    },
    onError: (e: unknown) => toast.error((e as Error)?.message ?? "quality check failed"),
  });

  if (!enabled) return null;

  const latest = q.data?.latest ?? null;
  const passed = !!latest && !!latest.passed;
  const rules: QualityRuleResult[] = (latest?.rule_results ?? []) as QualityRuleResult[];

  return (
    <div className="border-border/40 space-y-2 rounded border p-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-sm font-medium">
          {passed ? (
            <ShieldCheck className="h-4 w-4 text-emerald-400" />
          ) : (
            <ShieldAlert className="h-4 w-4 text-amber-400" />
          )}
          Quality
          {latest ? (
            <Badge
              variant="outline"
              className={`border font-mono text-[10px] ${
                passed
                  ? "border-emerald-600 bg-emerald-500/15 text-emerald-300"
                  : "border-rose-700 bg-rose-500/20 text-rose-200"
              }`}
            >
              {passed ? "passed" : "failed"} · {latest.score.toFixed(2)}
            </Badge>
          ) : (
            <Badge variant="outline" className="border-border/40 text-muted-foreground">
              not checked
            </Badge>
          )}
          {q.data && q.data.count > 0 && (
            <span className="text-muted-foreground text-[10px]">
              · {q.data.count} run{q.data.count === 1 ? "" : "s"}
            </span>
          )}
        </div>
        <Button
          size="sm"
          variant="outline"
          onClick={() => run.mutate()}
          disabled={run.isPending}
        >
          <RefreshCw className={`mr-1 h-3 w-3 ${run.isPending ? "animate-spin" : ""}`} />
          {latest ? "Re-check" : "Run check"}
        </Button>
      </div>

      {latest ? (
        <>
          <ScoreBar score={latest.score} />
          <div className="flex flex-wrap gap-1">
            {rules.map((r, i) => (
              <RuleChip key={i} r={r} />
            ))}
          </div>
          <div className="text-muted-foreground text-[10px]">
            checker={latest.checker} · {latest.created_at}
          </div>
        </>
      ) : (
        <div className="text-muted-foreground text-xs">
          No quality check yet. Run one before approving.
        </div>
      )}
    </div>
  );
}
