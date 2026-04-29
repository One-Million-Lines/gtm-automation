import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { FlaskConical, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { useProject } from "@/state/projectStore";
import { experimentsApi, type CreateExperimentInput } from "@/lib/api";
import { ExperimentStatusBadge } from "@/components/experiments/ExperimentStatusBadge";
import { ExperimentForm } from "@/components/experiments/ExperimentForm";

const STATUSES = ["all", "draft", "running", "paused", "completed", "archived"] as const;

export default function ExperimentsPage() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const { projectId } = useProject();
  const [statusFilter, setStatusFilter] = useState<(typeof STATUSES)[number]>("all");
  const [createOpen, setCreateOpen] = useState(false);

  const params = useMemo(
    () => ({
      project_id: projectId!,
      status: statusFilter === "all" ? undefined : statusFilter,
    }),
    [projectId, statusFilter],
  );

  const list = useQuery({
    queryKey: ["experiments-list", params],
    queryFn: () => experimentsApi.list(params.project_id, params.status),
    enabled: projectId != null,
  });

  const createMut = useMutation({
    mutationFn: (input: CreateExperimentInput) => experimentsApi.create(input),
    onSuccess: (exp) => {
      toast.success(`Experiment "${exp.name}" created`);
      qc.invalidateQueries({ queryKey: ["experiments-list"] });
      setCreateOpen(false);
      navigate(`/experiments/${exp.id}`);
    },
    onError: (e: unknown) => toast.error((e as Error)?.message ?? "create failed"),
  });

  const rows = list.data?.data ?? [];

  return (
    <div className="space-y-4 p-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <FlaskConical className="h-5 w-5 text-violet-400" />
          <h1 className="text-xl font-semibold">Experiments</h1>
        </div>
        <Dialog open={createOpen} onOpenChange={setCreateOpen}>
          <DialogTrigger asChild>
            <Button disabled={projectId == null}>
              <Plus className="h-4 w-4 mr-2" /> New experiment
            </Button>
          </DialogTrigger>
          <DialogContent className="max-w-3xl">
            <DialogHeader>
              <DialogTitle>Create experiment</DialogTitle>
            </DialogHeader>
            {projectId != null && (
              <ExperimentForm
                projectId={projectId}
                onSubmit={(input) => createMut.mutateAsync(input)}
                onCancel={() => setCreateOpen(false)}
                submitting={createMut.isPending}
              />
            )}
          </DialogContent>
        </Dialog>
      </div>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center justify-between text-base">
            <span>Filters</span>
            <span className="text-muted-foreground text-xs">
              {list.data?.count ?? 0} shown
            </span>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap items-center gap-1">
            <span className="text-muted-foreground text-[10px] uppercase">status</span>
            {STATUSES.map((s) => (
              <button
                key={s}
                onClick={() => setStatusFilter(s)}
                className={`rounded border px-2 py-1 text-xs ${
                  statusFilter === s
                    ? "border-foreground/50"
                    : "border-border/40 text-muted-foreground"
                }`}
              >
                {s}
              </button>
            ))}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Variants</TableHead>
                <TableHead>Allocation</TableHead>
                <TableHead>Min sample</TableHead>
                <TableHead>Started</TableHead>
                <TableHead>Winner</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.length === 0 && (
                <TableRow>
                  <TableCell colSpan={7} className="text-center text-sm text-muted-foreground py-8">
                    {list.isLoading ? "Loading…" : "No experiments yet."}
                  </TableCell>
                </TableRow>
              )}
              {rows.map((e) => (
                <TableRow
                  key={e.id}
                  className="cursor-pointer hover:bg-secondary/30"
                  onClick={() => navigate(`/experiments/${e.id}`)}
                >
                  <TableCell className="font-medium">{e.name}</TableCell>
                  <TableCell><ExperimentStatusBadge status={e.status} /></TableCell>
                  <TableCell className="font-mono text-xs">{e.variant_count ?? "—"}</TableCell>
                  <TableCell className="font-mono text-xs">{e.allocation}</TableCell>
                  <TableCell className="font-mono text-xs">{e.min_sample_size}</TableCell>
                  <TableCell className="font-mono text-xs">
                    {e.started_at ? e.started_at.slice(0, 10) : "—"}
                  </TableCell>
                  <TableCell className="font-mono text-xs">
                    {e.winner_variant_id ? `#${e.winner_variant_id}` : "—"}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
