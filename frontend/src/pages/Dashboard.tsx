import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { useProject } from "@/state/projectStore";
import { metricsApi } from "@/lib/api";
import { MetricCard } from "@/components/metrics/MetricCard";
import { SparklineChart } from "@/components/metrics/SparklineChart";
import { FunnelChart } from "@/components/metrics/FunnelChart";
import { IntentBreakdown } from "@/components/metrics/IntentBreakdown";

const WINDOWS = [7, 30, 90] as const;
type WindowDays = typeof WINDOWS[number];

function pct(v: number | null | undefined): string {
  if (v == null) return "—";
  return `${(v * 100).toFixed(1)}%`;
}

export default function Dashboard() {
  const { projectId } = useProject();
  const qc = useQueryClient();
  const [windowDays, setWindowDays] = useState<WindowDays>(30);

  const current = useQuery({
    queryKey: ["metrics-campaign", projectId, windowDays],
    queryFn: () =>
      metricsApi.campaign({ project_id: projectId!, window_days: windowDays }),
    enabled: projectId != null,
  });

  const prior = useQuery({
    queryKey: ["metrics-campaign-prior", projectId, windowDays],
    queryFn: () =>
      metricsApi.campaign({
        project_id: projectId!,
        window_days: windowDays * 2,
      }),
    enabled: projectId != null,
  });

  const recompute = useMutation({
    mutationFn: () =>
      metricsApi.recompute({ project_id: projectId!, window_days: windowDays }),
    onSuccess: () => {
      toast.success("Metrics recomputed");
      qc.invalidateQueries({ queryKey: ["metrics-campaign"] });
      qc.invalidateQueries({ queryKey: ["metrics-campaign-prior"] });
    },
    onError: (e: { message: string }) => toast.error(e.message),
  });

  const m = current.data;
  const p = prior.data;

  const deltaRate = (
    cur: number | undefined,
    pre: number | undefined,
  ): number | null => {
    if (cur == null || pre == null) return null;
    return cur - pre;
  };

  if (projectId == null) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>No project selected</CardTitle>
        </CardHeader>
        <CardContent className="text-muted-foreground text-sm">
          Pick or create a project from the topbar.
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">Campaign metrics</h2>
        <div className="flex items-center gap-2">
          <div className="flex gap-1">
            {WINDOWS.map((w) => (
              <Button
                key={w}
                size="sm"
                variant={windowDays === w ? "default" : "outline"}
                onClick={() => setWindowDays(w)}
              >
                {w}d
              </Button>
            ))}
          </div>
          <Button
            size="sm"
            variant="outline"
            onClick={() => recompute.mutate()}
            disabled={recompute.isPending}
          >
            <RefreshCw className="w-3.5 h-3.5 mr-1" />
            Recompute
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
        <MetricCard
          label={`Sent ${windowDays}d`}
          value={m?.sent_window ?? "—"}
          hint={`today ${m?.sent_today ?? 0}`}
        />
        <MetricCard
          label="Reply rate"
          value={pct(m?.reply_rate)}
          delta={deltaRate(m?.reply_rate, p?.reply_rate)}
        />
        <MetricCard
          label="Positive reply rate"
          value={pct(m?.positive_reply_rate)}
          delta={deltaRate(m?.positive_reply_rate, p?.positive_reply_rate)}
        />
        <MetricCard
          label="Open rate"
          value={pct(m?.opened_rate)}
          delta={deltaRate(m?.opened_rate, p?.opened_rate)}
        />
        <MetricCard
          label="Bounce rate"
          value={pct(m?.bounce_rate)}
          delta={deltaRate(m?.bounce_rate, p?.bounce_rate)}
        />
        <MetricCard
          label="Unsubscribe rate"
          value={pct(m?.unsubscribe_rate)}
          delta={deltaRate(m?.unsubscribe_rate, p?.unsubscribe_rate)}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle className="text-sm">Activity (last {windowDays} days)</CardTitle>
          </CardHeader>
          <CardContent>
            <SparklineChart series={m?.daily_series ?? []} />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Funnel</CardTitle>
          </CardHeader>
          <CardContent>
            <FunnelChart funnel={m?.funnel ?? {
              discovered: 0, scored: 0, approved: 0,
              sent: 0, opened: 0, replied: 0, positive: 0,
            }} />
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Reply intents</CardTitle>
          </CardHeader>
          <CardContent>
            <IntentBreakdown byIntent={m?.by_intent ?? {}} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Top replied companies</CardTitle>
          </CardHeader>
          <CardContent>
            {m?.top_replied_companies && m.top_replied_companies.length > 0 ? (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Company</TableHead>
                    <TableHead className="text-right">Replies</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {m.top_replied_companies.map((c) => (
                    <TableRow key={c.company_id}>
                      <TableCell>{c.company_name ?? `#${c.company_id}`}</TableCell>
                      <TableCell className="text-right font-mono">{c.replies}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            ) : (
              <div className="text-xs text-muted-foreground">no replies yet</div>
            )}
          </CardContent>
        </Card>
      </div>

      <div className="text-[10px] text-muted-foreground text-right">
        {m?.from_cache ? "cached" : "fresh"} · computed_at {m?.computed_at ?? "—"}
      </div>
    </div>
  );
}
