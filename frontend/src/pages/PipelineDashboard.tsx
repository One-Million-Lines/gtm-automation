import { useQuery } from "@tanstack/react-query";
import { LineChart, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useProject } from "@/state/projectStore";
import { pipelineHealthApi, type StageHealth } from "@/lib/api";

function fmtMs(n: number) {
  if (!n) return "—";
  if (n < 1000) return `${Math.round(n)}ms`;
  return `${(n / 1000).toFixed(1)}s`;
}
function fmtPct(n: number) {
  return `${(n * 100).toFixed(0)}%`;
}
function color(rate: number, total: number) {
  if (!total) return "bg-zinc-500/10 text-zinc-400";
  if (rate >= 0.9) return "bg-emerald-500/15 text-emerald-400";
  if (rate >= 0.5) return "bg-amber-500/15 text-amber-400";
  return "bg-rose-500/15 text-rose-400";
}

function StageCard({ s }: { s: StageHealth }) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-mono">{s.run_type}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2 text-sm">
        <div className={`inline-block rounded px-2 py-0.5 text-xs ${color(s.success_rate, s.count_total)}`}>
          {s.count_total ? `${fmtPct(s.success_rate)} success` : "no runs"}
        </div>
        <div className="grid grid-cols-3 gap-2 text-xs text-muted-foreground">
          <div>total {s.count_total}</div>
          <div>ok {s.count_success}</div>
          <div>fail {s.count_failed}</div>
        </div>
        <div className="grid grid-cols-2 gap-2 text-xs text-muted-foreground">
          <div>p50 {fmtMs(s.p50_ms)}</div>
          <div>p95 {fmtMs(s.p95_ms)}</div>
        </div>
        <div className="text-xs text-muted-foreground">
          last: {s.last_status ?? "—"} {s.last_run_at ? "@ " + s.last_run_at.slice(0, 19).replace("T", " ") : ""}
        </div>
        {s.last_error ? (
          <div className="text-xs text-rose-400 truncate" title={s.last_error}>
            {s.last_error}
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

export default function PipelineDashboard() {
  const { projectId } = useProject();
  const q = useQuery({
    queryKey: ["health-overview", projectId],
    queryFn: () =>
      pipelineHealthApi.overview({ project_id: projectId ?? undefined, limit: 50 }),
    enabled: projectId != null,
    refetchInterval: 30_000,
  });

  const stages = q.data?.stages ?? [];
  const fullPipeline = stages.find((s) => s.run_type === "full_pipeline");
  const others = stages.filter((s) => s.run_type !== "full_pipeline");

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2">
        <LineChart className="h-5 w-5" />
        <h1 className="text-2xl font-semibold">Pipeline Dashboard</h1>
        <div className="ml-auto">
          <Button variant="outline" size="sm" onClick={() => q.refetch()}>
            <RefreshCw className="mr-1 h-4 w-4" />
            Refresh
          </Button>
        </div>
      </div>

      {fullPipeline && (
        <Card>
          <CardHeader>
            <CardTitle>full_pipeline</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
              <div>
                <div className="text-muted-foreground text-xs">success rate</div>
                <div className="text-xl font-semibold">
                  {fullPipeline.count_total ? fmtPct(fullPipeline.success_rate) : "—"}
                </div>
              </div>
              <div>
                <div className="text-muted-foreground text-xs">runs</div>
                <div className="text-xl font-semibold">{fullPipeline.count_total}</div>
              </div>
              <div>
                <div className="text-muted-foreground text-xs">p50 / p95</div>
                <div className="text-xl font-semibold">
                  {fmtMs(fullPipeline.p50_ms)} / {fmtMs(fullPipeline.p95_ms)}
                </div>
              </div>
              <div>
                <div className="text-muted-foreground text-xs">last status</div>
                <div className="text-xl font-semibold">{fullPipeline.last_status ?? "—"}</div>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
        {others.map((s) => (
          <StageCard key={s.run_type} s={s} />
        ))}
      </div>
    </div>
  );
}
