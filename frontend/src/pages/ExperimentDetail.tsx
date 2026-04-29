import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import {
  ArrowLeft, Award, BarChart3, Pause, Play, RefreshCw,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { experimentsApi, type ExperimentScore } from "@/lib/api";
import { ExperimentStatusBadge } from "@/components/experiments/ExperimentStatusBadge";
import { VariantStatsTable } from "@/components/experiments/VariantStatsTable";
import { VariantBadge } from "@/components/experiments/VariantBadge";

function isScore(s: unknown): s is ExperimentScore {
  return !!s && typeof s === "object" && "by_variant" in (s as object);
}

export default function ExperimentDetailPage() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const { id } = useParams<{ id: string }>();
  const expId = Number(id);

  const detail = useQuery({
    queryKey: ["experiment", expId],
    queryFn: () => experimentsApi.get(expId),
    enabled: Number.isFinite(expId),
  });

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["experiment", expId] });
    qc.invalidateQueries({ queryKey: ["experiments-list"] });
  };

  const startMut = useMutation({
    mutationFn: () => experimentsApi.start(expId),
    onSuccess: () => { toast.success("Experiment started"); invalidate(); },
    onError: (e: unknown) => toast.error((e as Error)?.message ?? "start failed"),
  });
  const pauseMut = useMutation({
    mutationFn: () => experimentsApi.pause(expId),
    onSuccess: () => { toast.success("Experiment paused"); invalidate(); },
    onError: (e: unknown) => toast.error((e as Error)?.message ?? "pause failed"),
  });
  const scoreMut = useMutation({
    mutationFn: () => experimentsApi.score(expId),
    onSuccess: () => { toast.success("Re-scored"); invalidate(); },
    onError: (e: unknown) => toast.error((e as Error)?.message ?? "score failed"),
  });
  const declareMut = useMutation({
    mutationFn: (variant_id: number) => experimentsApi.declare(expId, variant_id),
    onSuccess: () => { toast.success("Winner declared"); invalidate(); },
    onError: (e: unknown) => toast.error((e as Error)?.message ?? "declare failed"),
  });

  if (detail.isLoading) {
    return <div className="p-6 text-muted-foreground">Loading…</div>;
  }
  if (!detail.data) {
    return <div className="p-6 text-muted-foreground">Not found.</div>;
  }

  const { experiment, variants, assignments_count, score } = detail.data;
  const scoreOk = isScore(score);
  const stats = scoreOk ? score.by_variant : [];
  const ready = scoreOk && score.ready_to_declare && score.leader_variant_id;

  return (
    <div className="space-y-4 p-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="icon" onClick={() => navigate("/experiments")}>
            <ArrowLeft className="h-4 w-4" />
          </Button>
          <h1 className="text-xl font-semibold">{experiment.name}</h1>
          <ExperimentStatusBadge status={experiment.status} />
        </div>
        <div className="flex gap-2">
          {experiment.status === "draft" || experiment.status === "paused" ? (
            <Button
              variant="outline"
              onClick={() => startMut.mutate()}
              disabled={startMut.isPending}
            >
              <Play className="h-4 w-4 mr-1" /> Start
            </Button>
          ) : null}
          {experiment.status === "running" && (
            <Button
              variant="outline"
              onClick={() => pauseMut.mutate()}
              disabled={pauseMut.isPending}
            >
              <Pause className="h-4 w-4 mr-1" /> Pause
            </Button>
          )}
          <Button
            variant="outline"
            onClick={() => scoreMut.mutate()}
            disabled={scoreMut.isPending}
          >
            <RefreshCw className={`h-4 w-4 mr-1 ${scoreMut.isPending ? "animate-spin" : ""}`} /> Re-score
          </Button>
          {ready && (
            <Button
              onClick={() => declareMut.mutate(score.leader_variant_id!)}
              disabled={declareMut.isPending}
              className="bg-emerald-600 hover:bg-emerald-700"
            >
              <Award className="h-4 w-4 mr-1" /> Declare winner
            </Button>
          )}
        </div>
      </div>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Overview</CardTitle>
        </CardHeader>
        <CardContent className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
          <div>
            <div className="text-muted-foreground text-xs">Hypothesis</div>
            <div>{experiment.hypothesis || "—"}</div>
          </div>
          <div>
            <div className="text-muted-foreground text-xs">Allocation</div>
            <div className="font-mono">{experiment.allocation}</div>
          </div>
          <div>
            <div className="text-muted-foreground text-xs">Primary metric</div>
            <div className="font-mono">{experiment.primary_metric}</div>
          </div>
          <div>
            <div className="text-muted-foreground text-xs">Min sample / variant</div>
            <div className="font-mono">{experiment.min_sample_size}</div>
          </div>
          <div>
            <div className="text-muted-foreground text-xs">Confidence level</div>
            <div className="font-mono">{experiment.confidence_level}</div>
          </div>
          <div>
            <div className="text-muted-foreground text-xs">Assignments</div>
            <div className="font-mono">{assignments_count}</div>
          </div>
          <div>
            <div className="text-muted-foreground text-xs">Started</div>
            <div className="font-mono">
              {experiment.started_at ? experiment.started_at.slice(0, 19) : "—"}
            </div>
          </div>
          <div>
            <div className="text-muted-foreground text-xs">Winner</div>
            <div className="font-mono">
              {experiment.winner_variant_id ? `#${experiment.winner_variant_id}` : "—"}
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base flex items-center gap-2">
            <BarChart3 className="h-4 w-4" /> Variants
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          <div className="flex flex-wrap gap-2">
            {variants.map((v) => (
              <VariantBadge key={v.id} name={v.name} isControl={v.is_control} />
            ))}
          </div>
          <VariantStatsTable
            stats={stats}
            winnerVariantId={experiment.winner_variant_id}
            leaderVariantId={scoreOk ? score.leader_variant_id : null}
          />
          {!scoreOk && (
            <div className="text-xs text-rose-300">
              Score unavailable: {(score as { error?: string }).error || "unknown error"}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
