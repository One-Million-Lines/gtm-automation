import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { ShieldCheck, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { useProject } from "@/state/projectStore";
import { qualityApi, type QualityListRow, type QualityRuleResult } from "@/lib/api";

function ScoreBar({ score }: { score: number }) {
  const pct = Math.max(0, Math.min(1, score)) * 100;
  const color =
    score >= 0.8 ? "bg-emerald-500" : score >= 0.6 ? "bg-amber-500" : "bg-rose-500";
  return (
    <div className="bg-muted/30 border-border/40 h-1.5 w-24 overflow-hidden rounded border">
      <div className={`h-full ${color}`} style={{ width: `${pct.toFixed(1)}%` }} />
    </div>
  );
}

function PassedChip({ passed }: { passed: number }) {
  const ok = !!passed;
  return (
    <Badge
      variant="outline"
      className={`border font-mono text-[10px] ${
        ok
          ? "border-emerald-600 bg-emerald-500/15 text-emerald-300"
          : "border-rose-700 bg-rose-500/20 text-rose-200"
      }`}
    >
      {ok ? "passed" : "failed"}
    </Badge>
  );
}

export default function QualityPage() {
  const qc = useQueryClient();
  const { projectId } = useProject();
  const [minScore, setMinScore] = useState<string>("");
  const [passedFilter, setPassedFilter] = useState<"all" | "true" | "false">("all");
  const [highlightId, setHighlightId] = useState<number | null>(null);

  const params = useMemo(() => {
    const p: { project_id: number; min_score?: number; passed?: boolean; limit?: number } = {
      project_id: projectId!,
      limit: 500,
    };
    const ms = parseFloat(minScore);
    if (!Number.isNaN(ms)) p.min_score = ms;
    if (passedFilter !== "all") p.passed = passedFilter === "true";
    return p;
  }, [projectId, minScore, passedFilter]);

  const q = useQuery({
    queryKey: ["quality-list", params],
    queryFn: () => qualityApi.list(params),
    enabled: projectId != null,
  });

  const runAll = useMutation({
    mutationFn: () =>
      qualityApi.runBatch({
        project_id: projectId!,
        only_missing: true,
        only_status: ["draft"],
        limit: 500,
      }),
    onSuccess: (res) => {
      toast.success(
        `Checked ${res.checked} · passed ${res.passed_count} · failed ${res.failed_count}`,
      );
      qc.invalidateQueries({ queryKey: ["quality-list"] });
      qc.invalidateQueries({ queryKey: ["quality"] });
    },
    onError: (e: unknown) => toast.error((e as Error)?.message ?? "batch failed"),
  });

  const rows = q.data?.data ?? [];

  return (
    <div className="space-y-4 p-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <ShieldCheck className="h-5 w-5 text-emerald-400" />
          <h1 className="text-xl font-semibold">Quality</h1>
        </div>
        <Button
          onClick={() => runAll.mutate()}
          disabled={projectId == null || runAll.isPending}
        >
          <RefreshCw className={`mr-2 h-4 w-4 ${runAll.isPending ? "animate-spin" : ""}`} />
          Run-all (drafts, only missing)
        </Button>
      </div>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center justify-between text-base">
            <span>Filters</span>
            <span className="text-muted-foreground text-xs">{q.data?.count ?? 0} shown</span>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          <div className="flex flex-wrap items-center gap-3">
            <label className="flex items-center gap-1 text-xs">
              <span className="text-muted-foreground">min_score</span>
              <input
                type="number"
                step="0.1"
                min={0}
                max={1}
                value={minScore}
                onChange={(e) => setMinScore(e.target.value)}
                placeholder="0.0–1.0"
                className="bg-muted/30 border-border/40 w-20 rounded border px-2 py-1 text-xs"
              />
            </label>
            <div className="flex items-center gap-1">
              <span className="text-muted-foreground text-[10px] uppercase">passed</span>
              {(["all", "true", "false"] as const).map((v) => (
                <button
                  key={v}
                  onClick={() => setPassedFilter(v)}
                  className={`rounded border px-2 py-1 text-xs ${
                    passedFilter === v
                      ? "border-foreground/50"
                      : "border-border/40 text-muted-foreground"
                  }`}
                >
                  {v}
                </button>
              ))}
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Created</TableHead>
                <TableHead>Company</TableHead>
                <TableHead>Subject</TableHead>
                <TableHead>Score</TableHead>
                <TableHead>Passed</TableHead>
                <TableHead>Rules</TableHead>
                <TableHead>Checker</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((r: QualityListRow) => {
                const failedRules = (r.rule_results ?? []).filter(
                  (x: QualityRuleResult) => !x.passed,
                );
                const isHi = highlightId === r.outreach_message_id;
                return (
                  <TableRow
                    key={r.id}
                    onClick={() => setHighlightId(r.outreach_message_id)}
                    className={`cursor-pointer ${isHi ? "bg-primary/10" : ""}`}
                  >
                    <TableCell className="font-mono text-[10px]">
                      {r.created_at}
                    </TableCell>
                    <TableCell className="text-xs">
                      <div className="font-medium">{r.company_name ?? "—"}</div>
                      <div className="text-muted-foreground text-[10px]">
                        {r.contact_email ?? r.company_domain ?? ""}
                      </div>
                    </TableCell>
                    <TableCell className="max-w-xs truncate text-xs">
                      {r.subject ?? "—"}
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <ScoreBar score={r.score} />
                        <span className="font-mono text-[10px]">{r.score.toFixed(2)}</span>
                      </div>
                    </TableCell>
                    <TableCell>
                      <PassedChip passed={r.passed} />
                    </TableCell>
                    <TableCell className="text-[10px] font-mono text-muted-foreground">
                      {failedRules.length === 0 ? "—" : failedRules.map((x) => x.rule).join(", ")}
                    </TableCell>
                    <TableCell className="text-[10px] font-mono">{r.checker}</TableCell>
                  </TableRow>
                );
              })}
              {rows.length === 0 && (
                <TableRow>
                  <TableCell colSpan={7} className="text-muted-foreground py-6 text-center text-xs">
                    No quality checks yet. Click Run-all to start.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {highlightId != null && (
        <div className="text-muted-foreground text-xs">
          Highlighted message id = <span className="font-mono">{highlightId}</span>
        </div>
      )}
    </div>
  );
}
