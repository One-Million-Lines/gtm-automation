import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Inbox, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { useProject } from "@/state/projectStore";
import {
  SEND_STATUSES, sendsApi, type SendListRow, type SendStatus,
} from "@/lib/api";
import { SendStatusBadge } from "@/components/sends/SendPanel";

function QuotaBar({
  sent_today, max_per_day,
}: { sent_today: number; max_per_day: number }) {
  const pct = max_per_day > 0 ? Math.min(100, (sent_today / max_per_day) * 100) : 0;
  const color = pct >= 100 ? "bg-rose-500" : pct >= 80 ? "bg-amber-500" : "bg-emerald-500";
  return (
    <div className="bg-muted/30 border-border/40 h-2 w-full overflow-hidden rounded border">
      <div className={`h-full ${color} transition-all`} style={{ width: `${pct.toFixed(1)}%` }} />
    </div>
  );
}

export default function SendsPage() {
  const qc = useQueryClient();
  const { projectId } = useProject();
  const [statusFilter, setStatusFilter] = useState<SendStatus | "all">("all");
  const [highlightId, setHighlightId] = useState<number | null>(null);

  const params = useMemo(() => {
    const p: { project_id: number; status?: SendStatus; limit?: number } = {
      project_id: projectId!,
      limit: 500,
    };
    if (statusFilter !== "all") p.status = statusFilter;
    return p;
  }, [projectId, statusFilter]);

  const list = useQuery({
    queryKey: ["sends-list", params],
    queryFn: () => sendsApi.list(params),
    enabled: projectId != null,
  });

  const quota = useQuery({
    queryKey: ["sends-quota", projectId],
    queryFn: () => sendsApi.quota(projectId!),
    enabled: projectId != null,
    staleTime: 5_000,
  });

  const sendAll = useMutation({
    mutationFn: () =>
      sendsApi.runBatch({ project_id: projectId!, max_per_day: 50, limit: 500 }),
    onSuccess: (res) => {
      toast.success(
        `Sent ${res.sent} · failed ${res.failed} · skipped ${res.skipped_quota + res.skipped_status}`,
      );
      qc.invalidateQueries({ queryKey: ["sends-list"] });
      qc.invalidateQueries({ queryKey: ["sends-quota"] });
      qc.invalidateQueries({ queryKey: ["sends"] });
      qc.invalidateQueries({ queryKey: ["outreach-list"] });
    },
    onError: (e: unknown) => toast.error((e as Error)?.message ?? "batch failed"),
  });

  const rows = list.data?.data ?? [];

  return (
    <div className="space-y-4 p-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Inbox className="h-5 w-5 text-violet-400" />
          <h1 className="text-xl font-semibold">Sends</h1>
        </div>
        <Button
          onClick={() => sendAll.mutate()}
          disabled={projectId == null || sendAll.isPending}
        >
          <RefreshCw className={`mr-2 h-4 w-4 ${sendAll.isPending ? "animate-spin" : ""}`} />
          Send-all (approved, quota=50)
        </Button>
      </div>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center justify-between text-base">
            <span>Daily quota</span>
            <span className="text-muted-foreground font-mono text-xs">
              {quota.data
                ? `${quota.data.sent_today} / ${quota.data.max_per_day} · ${quota.data.remaining} left`
                : "—"}
            </span>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <QuotaBar
            sent_today={quota.data?.sent_today ?? 0}
            max_per_day={quota.data?.max_per_day ?? 50}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center justify-between text-base">
            <span>Filters</span>
            <span className="text-muted-foreground text-xs">{list.data?.count ?? 0} shown</span>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap items-center gap-1">
            <span className="text-muted-foreground text-[10px] uppercase">status</span>
            {(["all", ...SEND_STATUSES] as const).map((v) => (
              <button
                key={v}
                onClick={() => setStatusFilter(v as SendStatus | "all")}
                className={`rounded border px-2 py-1 text-xs ${
                  statusFilter === v
                    ? "border-foreground/50"
                    : "border-border/40 text-muted-foreground"
                }`}
              >
                {v}
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
                <TableHead>Attempted</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Provider</TableHead>
                <TableHead>External ID</TableHead>
                <TableHead>Company</TableHead>
                <TableHead>Contact</TableHead>
                <TableHead>Subject</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((r: SendListRow) => {
                const isHi = highlightId === r.outreach_message_id;
                return (
                  <TableRow
                    key={r.id}
                    onClick={() => setHighlightId(r.outreach_message_id)}
                    className={`cursor-pointer ${isHi ? "bg-primary/10" : ""}`}
                  >
                    <TableCell className="font-mono text-[10px]">
                      {r.attempted_at}
                    </TableCell>
                    <TableCell>
                      <SendStatusBadge status={r.status} />
                      {r.error_message ? (
                        <div className="text-rose-300 text-[10px]">{r.error_message}</div>
                      ) : null}
                    </TableCell>
                    <TableCell className="font-mono text-[10px]">{r.provider}</TableCell>
                    <TableCell className="font-mono text-[10px] text-muted-foreground">
                      {r.message_id_external ?? "—"}
                    </TableCell>
                    <TableCell className="text-xs">
                      <div className="font-medium">{r.company_name ?? "—"}</div>
                      <div className="text-muted-foreground text-[10px]">
                        {r.company_domain ?? ""}
                      </div>
                    </TableCell>
                    <TableCell className="text-xs">
                      <div>{r.contact_name ?? "—"}</div>
                      <div className="text-muted-foreground text-[10px]">
                        {r.contact_email ?? ""}
                      </div>
                    </TableCell>
                    <TableCell className="max-w-xs truncate text-xs">
                      {r.subject ?? "—"}
                    </TableCell>
                  </TableRow>
                );
              })}
              {rows.length === 0 && (
                <TableRow>
                  <TableCell colSpan={7} className="text-muted-foreground py-6 text-center text-xs">
                    No sends yet. Approve a draft and click "Send now" or run "Send-all".
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
