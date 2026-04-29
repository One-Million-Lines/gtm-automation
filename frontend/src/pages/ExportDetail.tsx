import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import { ArrowLeft, Download, RefreshCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { exportsApi } from "@/lib/api";
import { ExportStatusBadge } from "@/components/exports/ExportStatusBadge";
import { ExportDestinationBadge } from "@/components/exports/ExportDestinationBadge";
import { ExportItemsTable } from "@/components/exports/ExportItemsTable";

export default function ExportDetailPage() {
  const { id: idParam } = useParams<{ id: string }>();
  const id = Number(idParam);
  const qc = useQueryClient();
  const navigate = useNavigate();

  const detail = useQuery({
    queryKey: ["export-detail", id],
    queryFn: () => exportsApi.get(id),
    enabled: !Number.isNaN(id),
  });

  const items = useQuery({
    queryKey: ["export-items", id],
    queryFn: () => exportsApi.items(id, 1000),
    enabled: !Number.isNaN(id),
  });

  const redeliverMut = useMutation({
    mutationFn: () => exportsApi.redeliver(id),
    onSuccess: (res) => {
      const delivered = (res.delivery as { delivered?: boolean })?.delivered;
      toast.success(delivered ? "Redelivered" : "Redeliver attempted");
      qc.invalidateQueries({ queryKey: ["export-detail", id] });
      qc.invalidateQueries({ queryKey: ["exports-list"] });
    },
    onError: (e: unknown) => toast.error((e as Error)?.message ?? "redeliver failed"),
  });

  const exp = detail.data?.export;

  return (
    <div className="space-y-4 p-4">
      <div className="flex items-center justify-between">
        <Button variant="ghost" size="sm" onClick={() => navigate("/exports")}>
          <ArrowLeft className="h-4 w-4 mr-1" /> Back to Exports
        </Button>
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            disabled={!exp?.artifact_path}
            onClick={() => window.open(exportsApi.downloadUrl(id), "_blank")}
          >
            <Download className="h-4 w-4 mr-1" /> Download
          </Button>
          <Button
            size="sm"
            onClick={() => redeliverMut.mutate()}
            disabled={redeliverMut.isPending}
          >
            <RefreshCcw className="h-4 w-4 mr-1" />
            {redeliverMut.isPending ? "Redelivering…" : "Redeliver"}
          </Button>
        </div>
      </div>

      {exp && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2 text-lg">
              {exp.name}
              <ExportStatusBadge status={exp.status} />
              <ExportDestinationBadge destination={exp.destination} />
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 gap-3 text-sm md:grid-cols-4">
              <Stat label="Format" value={exp.format.toUpperCase()} />
              <Stat label="Rows" value={String(exp.row_count)} />
              <Stat
                label="Size"
                value={exp.artifact_size_bytes != null ? `${exp.artifact_size_bytes} B` : "—"}
              />
              <Stat label="Items" value={String(detail.data?.item_count ?? 0)} />
              <Stat label="Created" value={(exp.created_at || "").slice(0, 19).replace("T", " ")} />
              <Stat
                label="Delivered"
                value={(exp.delivered_at || "").slice(0, 19).replace("T", " ") || "—"}
              />
              <Stat label="ICP" value={exp.icp_id != null ? `#${exp.icp_id}` : "—"} />
              <Stat label="ID" value={`#${exp.id}`} />
            </div>
            {exp.error_message && (
              <p className="mt-3 rounded border border-rose-700 bg-rose-500/10 p-2 text-xs text-rose-300">
                {exp.error_message}
              </p>
            )}
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Items</CardTitle>
        </CardHeader>
        <CardContent>
          {items.isLoading ? (
            <p className="text-sm text-zinc-400">Loading…</p>
          ) : (
            <ExportItemsTable items={items.data?.data ?? []} />
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col">
      <span className="text-muted-foreground text-[10px] uppercase">{label}</span>
      <span className="font-mono text-sm">{value}</span>
    </div>
  );
}
