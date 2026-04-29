import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Send, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { OutreachPanel, OutreachStatusBadge } from "@/components/outreach/OutreachPanel";
import { TierBadge } from "@/components/leads/LeadScoringPanel";
import { useProject } from "@/state/projectStore";
import {
  OUTREACH_STATUSES, PRIORITY_TIERS, outreachApi,
  type OutreachListRow, type OutreachStatus, type PriorityTier,
} from "@/lib/api";

type SortKey = "generated_at" | "priority_tier" | "company_name" | "status";
type SortDir = "asc" | "desc";

export default function OutreachPage() {
  const qc = useQueryClient();
  const { projectId } = useProject();
  const [status, setStatus] = useState<OutreachStatus | "all">("all");
  const [minTier, setMinTier] = useState<PriorityTier | "all">("all");
  const [sortKey, setSortKey] = useState<SortKey>("generated_at");
  const [sortDir, setSortDir] = useState<SortDir>("desc");
  const [selectedLeadId, setSelectedLeadId] = useState<number | null>(null);

  const statusParam = status === "all" ? undefined : status;
  const tierParam = minTier === "all" ? undefined : minTier;

  const q = useQuery({
    queryKey: ["outreach-list", projectId, statusParam, tierParam],
    queryFn: () =>
      outreachApi.list({
        project_id: projectId!,
        status: statusParam,
        min_tier: tierParam,
        limit: 500,
      }),
    enabled: projectId != null,
  });

  const generateAll = useMutation({
    mutationFn: () =>
      outreachApi.runBatch({
        project_id: projectId!,
        only_missing: true,
        min_tier: (tierParam ?? "B") as PriorityTier,
        limit: 500,
      }),
    onSuccess: (res) => {
      toast.success(
        `Generated ${res.generated} · scanned ${res.scanned} · skipped(tier)=${res.skipped_below_tier} · skipped(existing)=${res.skipped_existing}`,
      );
      qc.invalidateQueries({ queryKey: ["outreach-list"] });
      qc.invalidateQueries({ queryKey: ["outreach"] });
    },
    onError: (e: unknown) => toast.error((e as Error)?.message ?? "batch failed"),
  });

  const rows = useMemo(() => {
    const data = q.data?.data ?? [];
    const sorted = [...data].sort((a, b) => {
      const av = (a as Record<string, unknown>)[sortKey];
      const bv = (b as Record<string, unknown>)[sortKey];
      if (av == null && bv == null) return 0;
      if (av == null) return 1;
      if (bv == null) return -1;
      const sa = String(av);
      const sb = String(bv);
      return sortDir === "asc" ? sa.localeCompare(sb) : sb.localeCompare(sa);
    });
    return sorted;
  }, [q.data, sortKey, sortDir]);

  function toggleSort(k: SortKey) {
    if (sortKey === k) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else { setSortKey(k); setSortDir(k === "company_name" ? "asc" : "desc"); }
  }

  return (
    <div className="space-y-4 p-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Send className="h-5 w-5 text-sky-400" />
          <h1 className="text-xl font-semibold">Outreach</h1>
        </div>
        <Button
          onClick={() => generateAll.mutate()}
          disabled={projectId == null || generateAll.isPending}
        >
          <Sparkles className={`mr-2 h-4 w-4 ${generateAll.isPending ? "animate-pulse" : ""}`} />
          Generate-all (only missing)
        </Button>
      </div>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center justify-between text-base">
            <span>Filters</span>
            <span className="text-muted-foreground text-xs">{q.data?.count ?? 0} shown</span>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-muted-foreground text-[10px] uppercase">status</span>
            <button
              onClick={() => setStatus("all")}
              className={`rounded border px-2 py-1 text-xs ${
                status === "all" ? "border-foreground/50" : "border-border/40 text-muted-foreground"
              }`}
            >all</button>
            {OUTREACH_STATUSES.map((s) => (
              <button
                key={s}
                onClick={() => setStatus(s)}
                className={`rounded border px-2 py-1 text-xs ${
                  status === s ? "border-foreground/50" : "border-border/40 text-muted-foreground"
                }`}
              >
                <OutreachStatusBadge status={s} />
              </button>
            ))}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-muted-foreground text-[10px] uppercase">min tier</span>
            <button
              onClick={() => setMinTier("all")}
              className={`rounded border px-2 py-1 text-xs ${
                minTier === "all" ? "border-foreground/50" : "border-border/40 text-muted-foreground"
              }`}
            >all</button>
            {PRIORITY_TIERS.filter((t) => t === "A" || t === "B").map((t) => (
              <button
                key={t}
                onClick={() => setMinTier(t)}
                className={`rounded border px-2 py-1 text-xs ${
                  minTier === t ? "border-foreground/50" : "border-border/40 text-muted-foreground"
                }`}
              >
                <TierBadge tier={t} />
              </button>
            ))}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="p-0">
          {q.isLoading ? (
            <div className="text-muted-foreground p-4 text-sm">Loading…</div>
          ) : !rows.length ? (
            <div className="text-muted-foreground p-4 text-sm">No outreach messages.</div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>
                    <button onClick={() => toggleSort("generated_at")} className="text-xs uppercase">
                      Generated {sortKey === "generated_at" ? (sortDir === "asc" ? "↑" : "↓") : ""}
                    </button>
                  </TableHead>
                  <TableHead>
                    <button onClick={() => toggleSort("priority_tier")} className="text-xs uppercase">Tier</button>
                  </TableHead>
                  <TableHead>
                    <button onClick={() => toggleSort("company_name")} className="text-xs uppercase">Company</button>
                  </TableHead>
                  <TableHead>Contact</TableHead>
                  <TableHead>Subject</TableHead>
                  <TableHead>
                    <button onClick={() => toggleSort("status")} className="text-xs uppercase">Status</button>
                  </TableHead>
                  <TableHead>Model</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((r: OutreachListRow) => (
                  <TableRow
                    key={r.id}
                    className="cursor-pointer"
                    onClick={() => setSelectedLeadId(r.lead_id)}
                  >
                    <TableCell className="font-mono text-[11px]">
                      {r.generated_at ?? "—"}
                    </TableCell>
                    <TableCell><TierBadge tier={r.priority_tier} /></TableCell>
                    <TableCell>
                      <div className="flex flex-col">
                        <span>{r.company_name ?? "—"}</span>
                        <span className="text-muted-foreground text-[10px]">{r.company_domain ?? ""}</span>
                      </div>
                    </TableCell>
                    <TableCell>
                      <div className="flex flex-col">
                        <span>{r.contact_name ?? "—"}</span>
                        <span className="text-muted-foreground text-[10px]">{r.contact_title ?? ""}</span>
                      </div>
                    </TableCell>
                    <TableCell className="max-w-[260px] truncate text-xs">
                      {r.subject ?? "—"}
                    </TableCell>
                    <TableCell><OutreachStatusBadge status={r.status} /></TableCell>
                    <TableCell className="font-mono text-[10px]">{r.model ?? "—"}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {selectedLeadId != null && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">
              Outreach for lead #{selectedLeadId}
              <button
                onClick={() => setSelectedLeadId(null)}
                className="text-muted-foreground ml-2 text-[10px] underline"
              >close</button>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <OutreachPanel leadId={selectedLeadId} />
          </CardContent>
        </Card>
      )}
    </div>
  );
}
