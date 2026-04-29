import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Upload, Play, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  Card, CardContent, CardHeader, CardTitle,
} from "@/components/ui/card";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { useProject } from "@/state/projectStore";
import { suppressionApi, type SuppressionType } from "@/lib/api";
import { AddSuppressionDialog } from "@/components/suppression/AddSuppressionDialog";
import { ImportSuppressionDialog } from "@/components/suppression/ImportSuppressionDialog";

const TYPE_FILTERS: ("all" | SuppressionType)[] = [
  "all", "domain", "email", "company_name", "linkedin_url",
  "competitor", "customer", "unsubscribed", "bounced",
];

export default function SuppressionPage() {
  const qc = useQueryClient();
  const { projectId } = useProject();
  const [filter, setFilter] = useState<(typeof TYPE_FILTERS)[number]>("all");
  const [q, setQ] = useState("");
  const [addOpen, setAddOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);

  const type = filter === "all" ? undefined : filter;

  const list = useQuery({
    queryKey: ["suppression", type ?? "all", q],
    queryFn: () => suppressionApi.list({ type, q: q || undefined, limit: 500 }),
  });

  const del = useMutation({
    mutationFn: (id: number) => suppressionApi.delete(id),
    onSuccess: () => {
      toast.success("Removed");
      qc.invalidateQueries({ queryKey: ["suppression"] });
    },
    onError: (e: { message?: string }) => toast.error(e?.message ?? "Delete failed"),
  });

  const apply = useMutation({
    mutationFn: (dryRun: boolean) =>
      suppressionApi.apply({ project_id: projectId ?? undefined, dry_run: dryRun }),
    onSuccess: (r) => {
      const reason = Object.entries(r.by_reason)
        .map(([k, v]) => `${k}:${v}`).join(", ") || "—";
      toast.success(
        `${r.dry_run ? "Dry-run" : "Applied"} — scanned ${r.scanned}, ` +
        `suppressed ${r.suppressed} (${reason})`,
      );
      qc.invalidateQueries({ queryKey: ["leads"] });
      qc.invalidateQueries({ queryKey: ["contacts"] });
    },
    onError: (e: { message?: string }) => toast.error(e?.message ?? "Apply failed"),
  });

  const items = list.data?.data ?? [];
  const stats = list.data?.stats ?? {};

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Suppression</h1>
          <p className="text-muted-foreground text-sm">
            Block domains, emails, companies, and contacts from outreach. Apply
            before scoring/export.
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => setImportOpen(true)}>
            <Upload className="mr-1 h-4 w-4" /> Import
          </Button>
          <Button onClick={() => setAddOpen(true)}>
            <Plus className="mr-1 h-4 w-4" /> Add entry
          </Button>
          <Button
            variant="secondary"
            disabled={projectId == null || apply.isPending}
            onClick={() => apply.mutate(true)}
            title={projectId == null ? "Select a project first" : "Dry run on selected project"}
          >
            Dry run
          </Button>
          <Button
            disabled={projectId == null || apply.isPending}
            onClick={() => apply.mutate(false)}
            title={projectId == null ? "Select a project first" : "Apply to leads in selected project"}
          >
            <Play className="mr-1 h-4 w-4" />
            {apply.isPending ? "Applying…" : "Apply to leads"}
          </Button>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {TYPE_FILTERS.map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={
              "rounded-md border px-2 py-1 text-xs " +
              (filter === f
                ? "bg-primary text-primary-foreground border-primary"
                : "bg-background border-input")
            }
          >
            {f}
            {f !== "all" && stats[f] != null && (
              <span className="ml-1 opacity-60">({stats[f]})</span>
            )}
          </button>
        ))}
        <div className="ml-auto w-64">
          <Input
            placeholder="Search value…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        </div>
      </div>

      {list.isLoading ? (
        <p className="text-muted-foreground text-sm">Loading…</p>
      ) : items.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center gap-3 py-12 text-center">
            <p className="text-muted-foreground text-sm">
              No suppression entries{type ? ` of type ${type}` : ""}.
            </p>
            <div className="flex gap-2">
              <Button onClick={() => setAddOpen(true)}>
                <Plus className="mr-1 h-4 w-4" /> Add entry
              </Button>
              <Button variant="outline" onClick={() => setImportOpen(true)}>
                <Upload className="mr-1 h-4 w-4" /> Import CSV
              </Button>
            </div>
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Type</TableHead>
                  <TableHead>Value</TableHead>
                  <TableHead>Reason</TableHead>
                  <TableHead>Source</TableHead>
                  <TableHead>Created</TableHead>
                  <TableHead className="w-12" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map((e) => (
                  <TableRow key={e.id}>
                    <TableCell><Badge variant="secondary">{e.suppression_type}</Badge></TableCell>
                    <TableCell className="font-mono text-xs">{e.value}</TableCell>
                    <TableCell className="text-muted-foreground text-xs">
                      {e.reason || "—"}
                    </TableCell>
                    <TableCell className="text-muted-foreground text-xs">
                      {e.source || "—"}
                    </TableCell>
                    <TableCell className="text-muted-foreground text-xs">
                      {e.created_at?.slice(0, 16).replace("T", " ")}
                    </TableCell>
                    <TableCell>
                      <Button
                        size="icon"
                        variant="ghost"
                        onClick={() => del.mutate(e.id)}
                        disabled={del.isPending}
                        title="Remove"
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      <AddSuppressionDialog open={addOpen} onOpenChange={setAddOpen} />
      <ImportSuppressionDialog open={importOpen} onOpenChange={setImportOpen} />
    </div>
  );
}
