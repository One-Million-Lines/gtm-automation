import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Sliders, Sparkles, Undo2, Check, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { useProject } from "@/state/projectStore";
import { icpsApi, tuningApi, type ScoringRevision } from "@/lib/api";
import { RevisionStatusBadge } from "@/components/tuning/RevisionStatusBadge";
import { RevisionSourceBadge } from "@/components/tuning/RevisionSourceBadge";
import { WeightDiff } from "@/components/tuning/WeightDiff";

function fmtNum(n: number | undefined | null, digits = 4): string {
  if (n == null || !Number.isFinite(n)) return "—";
  return Number(n).toFixed(digits);
}

function fmtDate(s: string | null | undefined): string {
  if (!s) return "—";
  return s.replace("T", " ").slice(0, 19);
}

export default function TuningPage() {
  const qc = useQueryClient();
  const { projectId } = useProject();
  const [icpId, setIcpId] = useState<number | null>(null);

  const icpsQ = useQuery({
    queryKey: ["icps", projectId],
    queryFn: () => icpsApi.list(projectId!),
    enabled: projectId != null,
  });

  // Auto-pick first ICP if none selected.
  const effectiveIcpId = icpId ?? icpsQ.data?.[0]?.id ?? null;

  const summaryQ = useQuery({
    queryKey: ["tuning-summary", effectiveIcpId],
    queryFn: () => tuningApi.getWeights(effectiveIcpId!),
    enabled: effectiveIcpId != null,
  });

  const invalidate = () =>
    qc.invalidateQueries({ queryKey: ["tuning-summary", effectiveIcpId] });

  const proposeMut = useMutation({
    mutationFn: () =>
      tuningApi.propose(effectiveIcpId!, {
        project_id: projectId!,
        created_by: "ui",
      }),
    onSuccess: (res) => {
      toast.success(
        `Proposed revision #${res.revision.id} (${(res.stats as { dataset_size?: number }).dataset_size ?? 0} events)`,
      );
      invalidate();
    },
    onError: (e: unknown) => toast.error((e as Error)?.message ?? "propose failed"),
  });

  const approveMut = useMutation({
    mutationFn: (revId: number) => tuningApi.approve(revId),
    onSuccess: (res) => {
      toast.success(`Activated revision #${res.revision.id}`);
      invalidate();
    },
    onError: (e: unknown) => toast.error((e as Error)?.message ?? "approve failed"),
  });

  const rejectMut = useMutation({
    mutationFn: (revId: number) => tuningApi.reject(revId, { reason: "ui-reject" }),
    onSuccess: (res) => {
      toast.success(`Rejected revision #${res.revision.id}`);
      invalidate();
    },
    onError: (e: unknown) => toast.error((e as Error)?.message ?? "reject failed"),
  });

  const rollbackMut = useMutation({
    mutationFn: (revId: number) =>
      tuningApi.rollback(revId, { created_by: "ui", notes: "ui rollback" }),
    onSuccess: (res) => {
      toast.success(`Rolled back to revision (new id #${res.revision.id})`);
      invalidate();
    },
    onError: (e: unknown) => toast.error((e as Error)?.message ?? "rollback failed"),
  });

  const summary = summaryQ.data;
  const proposed = summary?.proposed ?? [];
  const history = summary?.history ?? [];
  const active = summary?.active ?? null;
  const moduleDefaults = summary?.module_defaults;
  const activeWeights = summary?.active_weights;

  const moduleVsActiveDiff = useMemo(() => {
    if (!moduleDefaults || !activeWeights) return [];
    const rows: Array<{
      namespace: "fit" | "signal"; key: string; baseline: number;
      proposed: number; delta: number;
    }> = [];
    for (const ns of ["fit", "signal"] as const) {
      const a = (activeWeights as Record<string, Record<string, number>>)[ns] ?? {};
      const b = (moduleDefaults as Record<string, Record<string, number>>)[ns] ?? {};
      const keys = new Set([...Object.keys(a), ...Object.keys(b)]);
      for (const k of keys) {
        const baseline = Number(b[k] ?? 0);
        const cur = Number(a[k] ?? 0);
        rows.push({ namespace: ns, key: k, baseline, proposed: cur, delta: cur - baseline });
      }
    }
    return rows;
  }, [moduleDefaults, activeWeights]);

  return (
    <div className="space-y-6 p-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Sliders className="h-6 w-6" /> Scoring Tuning
          </h1>
          <p className="text-sm text-zinc-400">
            Propose, approve, and roll back scoring weight revisions per ICP.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Select
            value={effectiveIcpId ? String(effectiveIcpId) : ""}
            onValueChange={(v) => setIcpId(Number(v))}
          >
            <SelectTrigger className="w-56">
              <SelectValue placeholder="Pick an ICP" />
            </SelectTrigger>
            <SelectContent>
              {(icpsQ.data ?? []).map((icp) => (
                <SelectItem key={icp.id} value={String(icp.id)}>
                  {icp.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button
            onClick={() => proposeMut.mutate()}
            disabled={!effectiveIcpId || !projectId || proposeMut.isPending}
          >
            <Sparkles className="mr-2 h-4 w-4" />
            Propose new
          </Button>
        </div>
      </div>

      {!projectId && (
        <p className="text-sm text-zinc-500">Select a project to begin.</p>
      )}

      {effectiveIcpId && (
        <>
          <Card>
            <CardHeader>
              <CardTitle>Active weights vs module defaults</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex items-center gap-3 text-sm">
                {active ? (
                  <>
                    <RevisionStatusBadge status={active.status} />
                    <RevisionSourceBadge source={active.source} />
                    <span className="text-zinc-400">
                      revision #{active.id} · activated {fmtDate(active.activated_at)}
                    </span>
                  </>
                ) : (
                  <span className="text-zinc-500">No active revision — using module defaults.</span>
                )}
              </div>
              <WeightDiff rows={moduleVsActiveDiff} />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Proposed revisions ({proposed.length})</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {proposed.length === 0 && (
                <p className="text-sm text-zinc-500">No proposed revisions.</p>
              )}
              {proposed.map((rev) => (
                <ProposedCard
                  key={rev.id}
                  revision={rev}
                  onApprove={() => approveMut.mutate(rev.id)}
                  onReject={() => rejectMut.mutate(rev.id)}
                  pending={approveMut.isPending || rejectMut.isPending}
                />
              ))}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>History ({history.length})</CardTitle>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>id</TableHead>
                    <TableHead>status</TableHead>
                    <TableHead>source</TableHead>
                    <TableHead>created</TableHead>
                    <TableHead>activated</TableHead>
                    <TableHead>archived</TableHead>
                    <TableHead>conf</TableHead>
                    <TableHead>events</TableHead>
                    <TableHead>by</TableHead>
                    <TableHead className="text-right">actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {history.map((rev) => {
                    const stats = (rev.stats ?? {}) as Record<string, unknown>;
                    return (
                      <TableRow key={rev.id}>
                        <TableCell className="font-mono text-xs">#{rev.id}</TableCell>
                        <TableCell><RevisionStatusBadge status={rev.status} /></TableCell>
                        <TableCell><RevisionSourceBadge source={rev.source} /></TableCell>
                        <TableCell className="font-mono text-xs">{fmtDate(rev.created_at)}</TableCell>
                        <TableCell className="font-mono text-xs">{fmtDate(rev.activated_at)}</TableCell>
                        <TableCell className="font-mono text-xs">{fmtDate(rev.archived_at)}</TableCell>
                        <TableCell className="font-mono text-xs">
                          {fmtNum(stats.confidence as number | undefined, 3)}
                        </TableCell>
                        <TableCell className="font-mono text-xs">
                          {String(stats.dataset_size ?? "—")}
                        </TableCell>
                        <TableCell className="font-mono text-xs text-zinc-400">
                          {rev.created_by ?? "—"}
                        </TableCell>
                        <TableCell className="text-right">
                          {rev.status !== "active" && (
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => rollbackMut.mutate(rev.id)}
                              disabled={rollbackMut.isPending}
                            >
                              <Undo2 className="mr-1 h-3.5 w-3.5" /> Rollback
                            </Button>
                          )}
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}

function ProposedCard({
  revision, onApprove, onReject, pending,
}: {
  revision: ScoringRevision;
  onApprove: () => void;
  onReject: () => void;
  pending: boolean;
}) {
  const detailQ = useQuery({
    queryKey: ["tuning-revision", revision.id],
    queryFn: () => tuningApi.getRevision(revision.id),
  });
  const stats = (revision.stats ?? {}) as Record<string, unknown>;
  return (
    <div className="rounded border border-zinc-800 p-4 space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <RevisionStatusBadge status={revision.status} />
          <RevisionSourceBadge source={revision.source} />
          <span className="text-sm text-zinc-400">
            revision #{revision.id} · by {revision.created_by ?? "—"} · {fmtDate(revision.created_at)}
          </span>
        </div>
        <div className="flex gap-2">
          <Button size="sm" variant="ghost" onClick={onReject} disabled={pending}>
            <X className="mr-1 h-3.5 w-3.5" /> Reject
          </Button>
          <Button size="sm" onClick={onApprove} disabled={pending}>
            <Check className="mr-1 h-3.5 w-3.5" /> Approve
          </Button>
        </div>
      </div>
      <div className="flex flex-wrap gap-4 text-xs text-zinc-400 font-mono">
        <span>dataset={String(stats.dataset_size ?? "—")}</span>
        <span>+{String(stats.positive_n ?? 0)}</span>
        <span>-{String(stats.negative_n ?? 0)}</span>
        <span>conf={fmtNum(stats.confidence as number | undefined, 3)}</span>
        <span>mean_shift={fmtNum(stats.mean_weight_shift as number | undefined, 4)}</span>
        <span>max_shift={fmtNum(stats.max_shift as number | undefined, 4)}</span>
      </div>
      {detailQ.data && <WeightDiff rows={detailQ.data.diff} />}
    </div>
  );
}
