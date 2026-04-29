import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { useProject } from "@/state/projectStore";
import {
  FEEDBACK_KINDS, FEEDBACK_SOURCES, feedbackApi,
  type FeedbackKind, type FeedbackSource,
} from "@/lib/api";
import { FeedbackKindBadge } from "@/components/feedback/FeedbackKindBadge";
import { LifecycleStageBadge } from "@/components/feedback/LifecycleStageBadge";

const KIND_FILTERS = ["all", ...FEEDBACK_KINDS] as const;
const SOURCE_FILTERS = ["all", ...FEEDBACK_SOURCES] as const;
const APPLIED_FILTERS = [
  { label: "all", value: undefined },
  { label: "applied", value: 1 },
  { label: "pending", value: 0 },
] as const;

export default function FeedbackPage() {
  const qc = useQueryClient();
  const { projectId } = useProject();
  const [kindFilter, setKindFilter] = useState<(typeof KIND_FILTERS)[number]>("all");
  const [sourceFilter, setSourceFilter] = useState<(typeof SOURCE_FILTERS)[number]>("all");
  const [appliedFilter, setAppliedFilter] = useState<number | undefined>(undefined);

  const params = useMemo(
    () => ({
      project_id: projectId!,
      kind: kindFilter === "all" ? undefined : (kindFilter as FeedbackKind),
      source: sourceFilter === "all" ? undefined : (sourceFilter as FeedbackSource),
      applied: appliedFilter,
      limit: 200,
    }),
    [projectId, kindFilter, sourceFilter, appliedFilter],
  );

  const list = useQuery({
    queryKey: ["feedback-list", params],
    queryFn: () => feedbackApi.list(params),
    enabled: projectId != null,
  });

  const summary = useQuery({
    queryKey: ["feedback-summary", projectId],
    queryFn: () => feedbackApi.summary(projectId!),
    enabled: projectId != null,
  });

  const applyMut = useMutation({
    mutationFn: () => feedbackApi.apply(projectId!),
    onSuccess: (res) => {
      toast.success(`Applied ${res.applied} of ${res.scanned} pending events`);
      qc.invalidateQueries({ queryKey: ["feedback-list"] });
      qc.invalidateQueries({ queryKey: ["feedback-summary"] });
    },
    onError: (e: unknown) => toast.error((e as Error)?.message ?? "apply failed"),
  });

  const rows = list.data?.data ?? [];
  const byKind = summary.data?.by_kind ?? {};
  const byStage = summary.data?.by_stage ?? {};

  return (
    <div className="space-y-6 p-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Feedback</h1>
          <p className="text-sm text-zinc-400">
            Engagement signals + lifecycle transitions feeding the learning loop.
          </p>
        </div>
        <Button onClick={() => applyMut.mutate()} disabled={applyMut.isPending}>
          <Sparkles className="mr-2 h-4 w-4" />
          Apply pending
        </Button>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>By kind</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-wrap gap-2">
            {Object.entries(byKind).length === 0 && (
              <p className="text-sm text-zinc-500">no events yet</p>
            )}
            {Object.entries(byKind).map(([k, n]) => (
              <div key={k} className="flex items-center gap-2 rounded border border-zinc-800 px-2 py-1">
                <FeedbackKindBadge kind={k} />
                <span className="font-mono text-xs text-zinc-300">{n}</span>
              </div>
            ))}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>By lifecycle stage</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-wrap gap-2">
            {Object.entries(byStage).length === 0 && (
              <p className="text-sm text-zinc-500">no leads yet</p>
            )}
            {Object.entries(byStage).map(([s, n]) => (
              <div key={s} className="flex items-center gap-2 rounded border border-zinc-800 px-2 py-1">
                <LifecycleStageBadge stage={s} />
                <span className="font-mono text-xs text-zinc-300">{n}</span>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Filters</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex flex-wrap gap-2">
            {KIND_FILTERS.map((k) => (
              <Button
                key={k}
                size="sm"
                variant={kindFilter === k ? "default" : "outline"}
                onClick={() => setKindFilter(k)}
              >
                {k}
              </Button>
            ))}
          </div>
          <div className="flex flex-wrap gap-2">
            {SOURCE_FILTERS.map((s) => (
              <Button
                key={s}
                size="sm"
                variant={sourceFilter === s ? "default" : "outline"}
                onClick={() => setSourceFilter(s)}
              >
                {s}
              </Button>
            ))}
          </div>
          <div className="flex flex-wrap gap-2">
            {APPLIED_FILTERS.map((f) => (
              <Button
                key={String(f.value)}
                size="sm"
                variant={appliedFilter === f.value ? "default" : "outline"}
                onClick={() => setAppliedFilter(f.value)}
              >
                {f.label}
              </Button>
            ))}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Events ({rows.length})</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>ID</TableHead>
                <TableHead>Kind</TableHead>
                <TableHead>Source</TableHead>
                <TableHead>Lead</TableHead>
                <TableHead>Weight</TableHead>
                <TableHead>Applied</TableHead>
                <TableHead>Created</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((ev) => (
                <TableRow key={ev.id}>
                  <TableCell className="font-mono text-xs">{ev.id}</TableCell>
                  <TableCell><FeedbackKindBadge kind={ev.kind} /></TableCell>
                  <TableCell className="font-mono text-xs">{ev.source}</TableCell>
                  <TableCell className="font-mono text-xs">{ev.lead_id ?? "—"}</TableCell>
                  <TableCell className="font-mono text-xs">{ev.weight ?? 1.0}</TableCell>
                  <TableCell className="font-mono text-xs">
                    {ev.applied ? "yes" : "no"}
                  </TableCell>
                  <TableCell className="font-mono text-[10px] text-zinc-500">
                    {(ev.created_at || "").slice(0, 19).replace("T", " ")}
                  </TableCell>
                </TableRow>
              ))}
              {rows.length === 0 && (
                <TableRow>
                  <TableCell colSpan={7} className="text-center text-sm text-zinc-500">
                    No feedback events match these filters.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
