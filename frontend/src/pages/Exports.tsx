import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Download, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger,
} from "@/components/ui/dialog";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { useProject } from "@/state/projectStore";
import {
  EXPORT_STATUSES, exportsApi,
  type CreateExportInput, type ExportStatus,
} from "@/lib/api";
import { ExportStatusBadge } from "@/components/exports/ExportStatusBadge";
import { ExportDestinationBadge } from "@/components/exports/ExportDestinationBadge";
import { ExportForm } from "@/components/exports/ExportForm";

const STATUSES = ["all", ...EXPORT_STATUSES] as const;

export default function ExportsPage() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const { projectId } = useProject();
  const [statusFilter, setStatusFilter] = useState<(typeof STATUSES)[number]>("all");
  const [createOpen, setCreateOpen] = useState(false);

  const params = useMemo(
    () => ({
      project_id: projectId!,
      status: (statusFilter === "all" ? undefined : (statusFilter as ExportStatus)),
    }),
    [projectId, statusFilter],
  );

  const list = useQuery({
    queryKey: ["exports-list", params],
    queryFn: () => exportsApi.list(params.project_id, params.status),
    enabled: projectId != null,
  });

  const createMut = useMutation({
    mutationFn: (input: CreateExportInput) => exportsApi.create(input),
    onSuccess: (res) => {
      toast.success(`Export "${res.export.name}" — ${res.row_count} rows`);
      qc.invalidateQueries({ queryKey: ["exports-list"] });
      setCreateOpen(false);
      navigate(`/exports/${res.export.id}`);
    },
    onError: (e: unknown) => toast.error((e as Error)?.message ?? "create failed"),
  });

  const rows = list.data?.data ?? [];

  const triggerDownload = (id: number) => {
    window.open(exportsApi.downloadUrl(id), "_blank");
  };

  return (
    <div className="space-y-4 p-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Download className="h-5 w-5 text-emerald-400" />
          <h1 className="text-xl font-semibold">Exports</h1>
        </div>
        <Dialog open={createOpen} onOpenChange={setCreateOpen}>
          <DialogTrigger asChild>
            <Button disabled={projectId == null}>
              <Plus className="h-4 w-4 mr-2" /> New export
            </Button>
          </DialogTrigger>
          <DialogContent className="max-w-2xl">
            <DialogHeader>
              <DialogTitle>Create export</DialogTitle>
            </DialogHeader>
            {projectId != null && (
              <ExportForm
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
                <TableHead>Destination</TableHead>
                <TableHead>Format</TableHead>
                <TableHead>Rows</TableHead>
                <TableHead>Size</TableHead>
                <TableHead>Created</TableHead>
                <TableHead>Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.length === 0 && (
                <TableRow>
                  <TableCell colSpan={8} className="text-center text-sm text-muted-foreground py-8">
                    {list.isLoading ? "Loading…" : "No exports yet."}
                  </TableCell>
                </TableRow>
              )}
              {rows.map((e) => (
                <TableRow
                  key={e.id}
                  className="cursor-pointer hover:bg-secondary/30"
                  onClick={() => navigate(`/exports/${e.id}`)}
                >
                  <TableCell className="font-medium">{e.name}</TableCell>
                  <TableCell><ExportStatusBadge status={e.status} /></TableCell>
                  <TableCell><ExportDestinationBadge destination={e.destination} /></TableCell>
                  <TableCell className="font-mono text-xs uppercase">{e.format}</TableCell>
                  <TableCell className="font-mono text-xs">{e.row_count}</TableCell>
                  <TableCell className="font-mono text-xs">
                    {e.artifact_size_bytes != null ? `${e.artifact_size_bytes} B` : "—"}
                  </TableCell>
                  <TableCell className="font-mono text-xs">
                    {e.created_at ? e.created_at.slice(0, 19).replace("T", " ") : "—"}
                  </TableCell>
                  <TableCell onClick={(ev) => ev.stopPropagation()}>
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={!e.artifact_path}
                      onClick={() => triggerDownload(e.id)}
                    >
                      <Download className="h-3 w-3 mr-1" /> Download
                    </Button>
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
