import { useMemo, useState, Fragment } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { ArrowDown, ArrowUp, Award, ChevronDown, ChevronRight, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Card, CardContent, CardHeader, CardTitle,
} from "@/components/ui/card";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { ContactDrawer } from "@/components/contacts/ContactDrawer";
import { OutreachPanel } from "@/components/outreach/OutreachPanel";
import { TierBadge } from "@/components/leads/LeadScoringPanel";
import { useProject } from "@/state/projectStore";
import {
  PRIORITY_TIERS, leadsApi, type LeadRow, type PriorityTier,
} from "@/lib/api";

type SortKey =
  | "final_score" | "icp_fit_score" | "signal_score"
  | "priority_tier" | "company_name" | "contact_name" | "lead_status";
type SortDir = "asc" | "desc";

function fmtPct(v: number | null | undefined) {
  if (v == null) return "—";
  return `${(v * 100).toFixed(0)}%`;
}

export default function LeadsPage() {
  const qc = useQueryClient();
  const { projectId } = useProject();
  const [tier, setTier] = useState<PriorityTier | "all">("all");
  const [drawerContactId, setDrawerContactId] = useState<number | null>(null);
  const [expandedLeadId, setExpandedLeadId] = useState<number | null>(null);
  const [sortKey, setSortKey] = useState<SortKey>("final_score");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  const tierParam = tier === "all" ? undefined : tier;

  const q = useQuery({
    queryKey: ["leads", projectId, tierParam],
    queryFn: () => leadsApi.list({ project_id: projectId!, tier: tierParam, limit: 500 }),
    enabled: projectId != null,
  });

  const rescoreAll = useMutation({
    mutationFn: () =>
      leadsApi.runBatch({ project_id: projectId!, only_missing: false, limit: 500 }),
    onSuccess: (res) => {
      toast.success(
        `Scored ${res.scored} leads · A:${res.tier_counts.A} B:${res.tier_counts.B} C:${res.tier_counts.C} D:${res.tier_counts.D}`,
      );
      qc.invalidateQueries({ queryKey: ["leads"] });
      qc.invalidateQueries({ queryKey: ["lead-scoring"] });
    },
    onError: (e: unknown) => toast.error((e as Error)?.message ?? "scoring failed"),
  });

  const rows = useMemo(() => {
    const data = q.data?.data ?? [];
    const sorted = [...data].sort((a, b) => {
      const av = (a as Record<string, unknown>)[sortKey];
      const bv = (b as Record<string, unknown>)[sortKey];
      if (av == null && bv == null) return 0;
      if (av == null) return 1;
      if (bv == null) return -1;
      if (typeof av === "number" && typeof bv === "number") {
        return sortDir === "asc" ? av - bv : bv - av;
      }
      const sa = String(av);
      const sb = String(bv);
      return sortDir === "asc" ? sa.localeCompare(sb) : sb.localeCompare(sa);
    });
    return sorted;
  }, [q.data, sortKey, sortDir]);

  function toggleSort(key: SortKey) {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir(key === "company_name" || key === "contact_name" ? "asc" : "desc");
    }
  }

  function SortHead({ k, label }: { k: SortKey; label: string }) {
    const active = sortKey === k;
    const Icon = active && sortDir === "asc" ? ArrowUp : ArrowDown;
    return (
      <button
        onClick={() => toggleSort(k)}
        className={`flex items-center gap-1 text-left text-xs uppercase ${
          active ? "text-foreground" : "text-muted-foreground hover:text-foreground"
        }`}
      >
        {label}
        {active && <Icon className="h-3 w-3" />}
      </button>
    );
  }

  const counts = useMemo(() => {
    const c: Record<string, number> = { all: 0, A: 0, B: 0, C: 0, D: 0, unscored: 0 };
    for (const r of q.data?.data ?? []) {
      c.all += 1;
      const t = r.priority_tier ?? "unscored";
      c[t] = (c[t] ?? 0) + 1;
    }
    return c;
  }, [q.data]);

  return (
    <div className="space-y-4 p-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Award className="h-5 w-5 text-emerald-400" />
          <h1 className="text-xl font-semibold">Leads</h1>
        </div>
        <Button
          onClick={() => rescoreAll.mutate()}
          disabled={projectId == null || rescoreAll.isPending}
        >
          <RefreshCw className={`mr-2 h-4 w-4 ${rescoreAll.isPending ? "animate-spin" : ""}`} />
          Re-score all
        </Button>
      </div>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center justify-between text-base">
            <span>Filter by tier</span>
            <span className="text-muted-foreground text-xs">
              {q.data?.count ?? 0} shown
            </span>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap gap-2">
            <button
              onClick={() => setTier("all")}
              className={`rounded border px-2 py-1 text-xs ${
                tier === "all"
                  ? "border-foreground/50"
                  : "border-border/40 text-muted-foreground hover:text-foreground"
              }`}
            >
              all ({counts.all ?? 0})
            </button>
            {PRIORITY_TIERS.map((t) => (
              <button
                key={t}
                onClick={() => setTier(t)}
                className={`flex items-center gap-1 rounded border px-2 py-1 text-xs ${
                  tier === t
                    ? "border-foreground/50"
                    : "border-border/40 text-muted-foreground hover:text-foreground"
                }`}
              >
                <TierBadge tier={t} />
                ({counts[t] ?? 0})
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
            <div className="text-muted-foreground p-4 text-sm">No leads.</div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-8"></TableHead>
                  <TableHead><SortHead k="priority_tier" label="Tier" /></TableHead>
                  <TableHead><SortHead k="company_name" label="Company" /></TableHead>
                  <TableHead><SortHead k="contact_name" label="Contact" /></TableHead>
                  <TableHead><SortHead k="lead_status" label="Status" /></TableHead>
                  <TableHead><SortHead k="icp_fit_score" label="Fit" /></TableHead>
                  <TableHead><SortHead k="signal_score" label="Intent" /></TableHead>
                  <TableHead><SortHead k="final_score" label="Combined" /></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((r: LeadRow) => (
                  <Fragment key={r.id}>
                  <TableRow
                    key={r.id}
                    className="cursor-pointer"
                    onClick={() => r.contact_id && setDrawerContactId(r.contact_id)}
                  >
                    <TableCell
                      className="w-8"
                      onClick={(e) => {
                        e.stopPropagation();
                        setExpandedLeadId((cur) => (cur === r.id ? null : r.id));
                      }}
                    >
                      {expandedLeadId === r.id ? (
                        <ChevronDown className="h-3 w-3" />
                      ) : (
                        <ChevronRight className="h-3 w-3" />
                      )}
                    </TableCell>
                    <TableCell><TierBadge tier={r.priority_tier} /></TableCell>
                    <TableCell>
                      <div className="flex flex-col">
                        <span>{r.company_name ?? "—"}</span>
                        <span className="text-muted-foreground text-[10px]">
                          {r.company_industry ?? "—"} · {r.company_domain ?? ""}
                        </span>
                      </div>
                    </TableCell>
                    <TableCell>
                      <div className="flex flex-col">
                        <span>{r.contact_name ?? "—"}</span>
                        <span className="text-muted-foreground text-[10px]">
                          {r.contact_title ?? "—"}
                        </span>
                      </div>
                    </TableCell>
                    <TableCell className="text-xs">{r.lead_status}</TableCell>
                    <TableCell className="font-mono text-xs">
                      {fmtPct(r.icp_fit_score)}
                    </TableCell>
                    <TableCell className="font-mono text-xs">
                      {fmtPct(r.signal_score)}
                    </TableCell>
                    <TableCell className="font-mono text-xs font-semibold">
                      {fmtPct(r.final_score)}
                    </TableCell>
                  </TableRow>
                  {expandedLeadId === r.id && (
                    <TableRow key={`${r.id}-expand`}>
                      <TableCell colSpan={8} className="bg-muted/10 p-3">
                        <OutreachPanel leadId={r.id} />
                      </TableCell>
                    </TableRow>
                  )}
                  </Fragment>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <ContactDrawer
        contactId={drawerContactId}
        onOpenChange={(v) => !v && setDrawerContactId(null)}
      />
    </div>
  );
}
