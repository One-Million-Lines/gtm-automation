import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Plus, Sparkles, Activity } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Card, CardContent, CardHeader, CardTitle,
} from "@/components/ui/card";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { StatusBadge } from "@/components/StatusBadge";
import { IngestDialog } from "@/components/companies/IngestDialog";
import { CompanyDrawer } from "@/components/companies/CompanyDrawer";
import { useProject } from "@/state/projectStore";
import { companiesApi, enrichmentApi, signalsApi } from "@/lib/api";

const FILTERS = ["all", "new", "enriched", "qualified", "rejected"] as const;
type Filter = typeof FILTERS[number];

export default function CompaniesPage() {
  const { projectId } = useProject();
  const qc = useQueryClient();
  const [filter, setFilter] = useState<Filter>("all");
  const [ingestOpen, setIngestOpen] = useState(false);
  const [drawerId, setDrawerId] = useState<number | null>(null);

  const status = filter === "all" ? undefined : filter;

  const enrichAll = useMutation({
    mutationFn: () =>
      enrichmentApi.runBatch({ project_id: projectId!, only_missing: true, limit: 50 }),
    onSuccess: (res) => {
      toast.success(
        `Enriched ${res.enriched}/${res.scanned} (skipped ${res.skipped}, failed ${res.failed})`,
      );
      qc.invalidateQueries({ queryKey: ["companies"] });
    },
    onError: (e: unknown) => {
      const msg = e instanceof Error ? e.message : String(e);
      toast.error(`Batch enrichment failed: ${msg}`);
    },
  });

  const runSignals = useMutation({
    mutationFn: () =>
      signalsApi.runBatch({ project_id: projectId!, only_missing: true, limit: 100 }),
    onSuccess: (res) => {
      toast.success(
        `Signals: persisted ${res.persisted} across ${res.scanned_companies} co. + ${res.scanned_contacts} ct. (failed ${res.failed})`,
      );
      qc.invalidateQueries({ queryKey: ["signals"] });
    },
    onError: (e: unknown) => {
      const msg = e instanceof Error ? e.message : String(e);
      toast.error(`Signals run failed: ${msg}`);
    },
  });

  const q = useQuery({
    queryKey: ["companies", projectId, status ?? "all"],
    queryFn: () => companiesApi.list(projectId!, status),
    enabled: projectId != null,
  });

  if (projectId == null) {
    return (
      <Card>
        <CardHeader><CardTitle>Companies</CardTitle></CardHeader>
        <CardContent className="text-muted-foreground text-sm">
          Select or create a project from the top bar to manage companies.
        </CardContent>
      </Card>
    );
  }

  const items = q.data ?? [];

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Companies</h1>
          <p className="text-muted-foreground text-sm">
            Discovery output — companies linked to one or more ICPs.
          </p>
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            onClick={() => enrichAll.mutate()}
            disabled={enrichAll.isPending}
          >
            <Sparkles className="mr-1 h-4 w-4" />
            {enrichAll.isPending ? "Enriching\u2026" : "Enrich missing"}
          </Button>          <Button
            variant="outline"
            onClick={() => runSignals.mutate()}
            disabled={runSignals.isPending}
          >
            <Activity className="mr-1 h-4 w-4" />
            {runSignals.isPending ? "Running…" : "Run signals"}
          </Button>          <Button onClick={() => setIngestOpen(true)}>
            <Plus className="mr-1 h-4 w-4" /> Ingest companies
          </Button>
        </div>
      </div>

      <div className="flex flex-wrap gap-2">
        {FILTERS.map((f) => (
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
          </button>
        ))}
      </div>

      {q.isLoading ? (
        <p className="text-muted-foreground text-sm">Loading…</p>
      ) : items.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center gap-3 py-12 text-center">
            <p className="text-muted-foreground text-sm">
              No companies yet for this project.
            </p>
            <Button onClick={() => setIngestOpen(true)}>
              <Plus className="mr-1 h-4 w-4" /> Ingest companies
            </Button>
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Domain</TableHead>
                  <TableHead>Name</TableHead>
                  <TableHead>Industry</TableHead>
                  <TableHead>Size</TableHead>
                  <TableHead>Country</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Created</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map((c) => (
                  <TableRow
                    key={c.id}
                    onClick={() => setDrawerId(c.id)}
                    className="cursor-pointer"
                  >
                    <TableCell className="font-medium">{c.domain ?? "—"}</TableCell>
                    <TableCell>{c.name ?? "—"}</TableCell>
                    <TableCell>{c.industry ?? "—"}</TableCell>
                    <TableCell>{c.employee_count ?? "—"}</TableCell>
                    <TableCell>{c.country ?? "—"}</TableCell>
                    <TableCell><StatusBadge status={c.status} /></TableCell>
                    <TableCell className="text-muted-foreground text-xs">
                      {new Date(c.created_at).toLocaleString()}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      <IngestDialog
        open={ingestOpen}
        onOpenChange={setIngestOpen}
        projectId={projectId}
      />
      <CompanyDrawer
        companyId={drawerId}
        onOpenChange={(v) => !v && setDrawerId(null)}
      />
    </div>
  );
}
