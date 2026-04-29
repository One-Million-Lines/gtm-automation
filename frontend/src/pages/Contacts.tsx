import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Plus, Sparkles, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Card, CardContent, CardHeader, CardTitle,
} from "@/components/ui/card";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { IngestContactsDialog } from "@/components/contacts/IngestContactsDialog";
import { ImportEnrichedDialog } from "@/components/contacts/ImportEnrichedDialog";
import { ContactDrawer } from "@/components/contacts/ContactDrawer";
import {
  ConfidenceBar, StatusPill,
} from "@/components/contacts/ContactEnrichmentSection";
import { TierBadge } from "@/components/leads/LeadScoringPanel";
import { useProject } from "@/state/projectStore";
import { contactEnrichmentApi, contactsApi, leadsApi } from "@/lib/api";

const ROLE_FILTERS = [
  "all", "founder", "marketing_lead", "growth_lead", "crm_lead",
  "lifecycle_marketing", "email_marketing", "ecommerce_lead",
  "revops", "ops_lead", "sales_lead",
] as const;
type RoleFilter = typeof ROLE_FILTERS[number];

export default function ContactsPage() {
  const qc = useQueryClient();
  const { projectId } = useProject();
  const [filter, setFilter] = useState<RoleFilter>("all");
  const [ingestOpen, setIngestOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [drawerId, setDrawerId] = useState<number | null>(null);

  const role = filter === "all" ? undefined : filter;

  const q = useQuery({
    queryKey: ["contacts", projectId, role ?? "all"],
    queryFn: () => contactsApi.list(projectId!, { role }),
    enabled: projectId != null,
  });

  const leadsQ = useQuery({
    queryKey: ["leads-for-contacts", projectId],
    queryFn: () => leadsApi.list({ project_id: projectId!, limit: 1000 }),
    enabled: projectId != null,
  });
  const tierByContact = (() => {
    const m = new Map<number, "A" | "B" | "C" | "D" | null>();
    for (const r of leadsQ.data?.data ?? []) {
      if (r.contact_id != null) m.set(r.contact_id, r.priority_tier);
    }
    return m;
  })();

  const enrichAll = useMutation({
    mutationFn: () =>
      contactEnrichmentApi.runBatch({
        project_id: projectId!,
        only_missing: true,
        limit: 200,
      }),
    onSuccess: (res) => {
      toast.success(
        `Enriched ${res.enriched}/${res.scanned} (skipped ${res.skipped}, failed ${res.failed})`,
      );
      qc.invalidateQueries({ queryKey: ["contacts"] });
    },
    onError: (err: unknown) => {
      const e = err as { response?: { data?: { detail?: string } }; message?: string };
      toast.error(e.response?.data?.detail ?? e.message ?? "Enrichment failed");
    },
  });

  if (projectId == null) {
    return (
      <Card>
        <CardHeader><CardTitle>Contacts</CardTitle></CardHeader>
        <CardContent className="text-muted-foreground text-sm">
          Select or create a project from the top bar to manage contacts.
        </CardContent>
      </Card>
    );
  }

  const items = q.data ?? [];

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Contacts</h1>
          <p className="text-muted-foreground text-sm">
            Discovery output — contacts attached to companies and ICPs.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            onClick={() => enrichAll.mutate()}
            disabled={enrichAll.isPending || projectId == null}
          >
            <Sparkles className="mr-1 h-4 w-4" /> Enrich missing
          </Button>
          <Button variant="outline" onClick={() => setImportOpen(true)}>
            <Upload className="mr-1 h-4 w-4" /> Import enriched CSV
          </Button>
          <Button onClick={() => setIngestOpen(true)}>
            <Plus className="mr-1 h-4 w-4" /> Ingest contacts
          </Button>
        </div>
      </div>

      <div className="flex flex-wrap gap-2">
        {ROLE_FILTERS.map((f) => (
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
              No contacts yet for this project. Run company discovery first, then
              ingest contacts referencing those companies.
            </p>
            <Button onClick={() => setIngestOpen(true)}>
              <Plus className="mr-1 h-4 w-4" /> Ingest contacts
            </Button>
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead>Tier</TableHead>
                  <TableHead>Title</TableHead>
                  <TableHead>Role</TableHead>
                  <TableHead>Email</TableHead>
                  <TableHead>Email status</TableHead>
                  <TableHead>LinkedIn</TableHead>
                  <TableHead>Company</TableHead>
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
                    <TableCell className="font-medium">
                      {c.full_name ||
                        [c.first_name, c.last_name].filter(Boolean).join(" ") ||
                        "—"}
                    </TableCell>
                    <TableCell>
                      <TierBadge tier={tierByContact.get(c.id) ?? null} />
                    </TableCell>
                    <TableCell>{c.job_title ?? "—"}</TableCell>
                    <TableCell>
                      {c.normalized_role ? (
                        <Badge variant="secondary">{c.normalized_role}</Badge>
                      ) : "—"}
                    </TableCell>
                    <TableCell>{c.email ?? "—"}</TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <StatusPill status={c.email_status} />
                        {c.email_confidence != null && (
                          <ConfidenceBar value={c.email_confidence} />
                        )}
                      </div>
                    </TableCell>
                    <TableCell>
                      {c.linkedin_url ? (
                        <a
                          href={c.linkedin_url}
                          target="_blank"
                          rel="noreferrer"
                          onClick={(e) => e.stopPropagation()}
                          className="text-blue-400 underline"
                        >
                          link
                        </a>
                      ) : "—"}
                    </TableCell>
                    <TableCell className="text-muted-foreground text-xs">
                      #{c.company_id}
                    </TableCell>
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

      <IngestContactsDialog
        open={ingestOpen}
        onOpenChange={setIngestOpen}
        projectId={projectId}
      />
      <ImportEnrichedDialog
        open={importOpen}
        onOpenChange={setImportOpen}
        projectId={projectId}
      />
      <ContactDrawer
        contactId={drawerId}
        onOpenChange={(v) => !v && setDrawerId(null)}
      />
    </div>
  );
}
