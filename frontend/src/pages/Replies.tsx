import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { MessageSquare, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { useProject } from "@/state/projectStore";
import {
  REPLY_INTENTS, repliesApi, type ReplyIntent, type ReplyListRow,
} from "@/lib/api";
import { ReplyIntentBadge } from "@/components/replies/ReplyIntentBadge";

export default function RepliesPage() {
  const qc = useQueryClient();
  const { projectId } = useProject();
  const [intentFilter, setIntentFilter] = useState<ReplyIntent | "all">("all");

  const params = useMemo(() => {
    const p: { project_id: number; intent?: ReplyIntent; limit?: number } = {
      project_id: projectId!,
      limit: 500,
    };
    if (intentFilter !== "all") p.intent = intentFilter;
    return p;
  }, [projectId, intentFilter]);

  const list = useQuery({
    queryKey: ["replies-list", params],
    queryFn: () => repliesApi.list(params),
    enabled: projectId != null,
  });

  const pollAll = useMutation({
    mutationFn: () =>
      repliesApi.poll({ project_id: projectId!, limit: 200 }),
    onSuccess: (res) => {
      const intents = Object.entries(res.by_intent ?? {})
        .map(([k, v]) => `${k}=${v}`).join(" ");
      toast.success(
        `scanned=${res.scanned} ingested=${res.ingested} suppressed=${res.suppressed}${intents ? " · " + intents : ""}`,
      );
      qc.invalidateQueries({ queryKey: ["replies-list"] });
      qc.invalidateQueries({ queryKey: ["replies"] });
      qc.invalidateQueries({ queryKey: ["sends-list"] });
      qc.invalidateQueries({ queryKey: ["outreach-list"] });
    },
    onError: (e: unknown) => toast.error((e as Error)?.message ?? "poll failed"),
  });

  const rows = list.data?.data ?? [];

  return (
    <div className="space-y-4 p-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <MessageSquare className="h-5 w-5 text-fuchsia-400" />
          <h1 className="text-xl font-semibold">Replies</h1>
        </div>
        <Button
          onClick={() => pollAll.mutate()}
          disabled={projectId == null || pollAll.isPending}
        >
          <RefreshCw className={`mr-2 h-4 w-4 ${pollAll.isPending ? "animate-spin" : ""}`} />
          Poll inbox
        </Button>
      </div>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center justify-between text-base">
            <span>Filters</span>
            <span className="text-muted-foreground text-xs">{list.data?.count ?? 0} shown</span>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap items-center gap-1">
            <span className="text-muted-foreground text-[10px] uppercase">intent</span>
            {(["all", ...REPLY_INTENTS] as const).map((v) => (
              <button
                key={v}
                onClick={() => setIntentFilter(v as ReplyIntent | "all")}
                className={`rounded border px-2 py-1 text-xs ${
                  intentFilter === v
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
                <TableHead>Received</TableHead>
                <TableHead>Intent</TableHead>
                <TableHead>From</TableHead>
                <TableHead>Subject</TableHead>
                <TableHead>Body</TableHead>
                <TableHead>Company</TableHead>
                <TableHead>Classifier</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((r: ReplyListRow) => (
                <TableRow key={r.id}>
                  <TableCell className="font-mono text-[10px]">
                    {r.received_at ?? "—"}
                  </TableCell>
                  <TableCell>
                    <ReplyIntentBadge intent={r.intent} confidence={r.confidence} />
                  </TableCell>
                  <TableCell className="text-xs">
                    <div>{r.from_name ?? r.from_email ?? "—"}</div>
                    <div className="text-muted-foreground text-[10px]">
                      {r.from_email ?? ""}
                    </div>
                  </TableCell>
                  <TableCell className="max-w-[16rem] truncate text-xs">
                    {r.subject ?? "—"}
                  </TableCell>
                  <TableCell className="max-w-[24rem] truncate text-xs text-muted-foreground">
                    {r.body ?? "—"}
                  </TableCell>
                  <TableCell className="text-xs">
                    <div className="font-medium">{r.company_name ?? "—"}</div>
                    <div className="text-muted-foreground text-[10px]">
                      {r.company_domain ?? ""}
                    </div>
                  </TableCell>
                  <TableCell className="font-mono text-[10px] text-muted-foreground">
                    {r.classifier ?? "—"}
                  </TableCell>
                </TableRow>
              ))}
              {rows.length === 0 && (
                <TableRow>
                  <TableCell colSpan={7} className="text-muted-foreground py-6 text-center text-xs">
                    No replies yet. Click "Poll inbox" to fetch new replies.
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
