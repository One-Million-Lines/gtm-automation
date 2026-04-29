import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Send as SendIcon, Inbox, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useProject } from "@/state/projectStore";
import { sendsApi, type Send, type SendStatus } from "@/lib/api";

const STATUS_COLORS: Record<SendStatus, string> = {
  queued:  "border-zinc-600  bg-zinc-500/15  text-zinc-300",
  sending: "border-amber-600 bg-amber-500/15 text-amber-200",
  sent:    "border-emerald-600 bg-emerald-500/15 text-emerald-300",
  bounced: "border-rose-700  bg-rose-500/20  text-rose-200",
  failed:  "border-rose-700  bg-rose-500/20  text-rose-200",
  opened:  "border-sky-600   bg-sky-500/15   text-sky-300",
  replied: "border-violet-600 bg-violet-500/15 text-violet-300",
};

export function SendStatusBadge({ status }: { status: SendStatus | null | undefined }) {
  if (!status) {
    return (
      <Badge variant="outline" className="border-border/40 text-muted-foreground">
        none
      </Badge>
    );
  }
  return (
    <Badge variant="outline" className={`border ${STATUS_COLORS[status]} font-mono text-[10px]`}>
      {status}
    </Badge>
  );
}

function QuotaBar({
  sent_today, max_per_day,
}: { sent_today: number; max_per_day: number }) {
  const pct = max_per_day > 0 ? Math.min(100, (sent_today / max_per_day) * 100) : 0;
  const color = pct >= 100 ? "bg-rose-500" : pct >= 80 ? "bg-amber-500" : "bg-emerald-500";
  return (
    <div className="bg-muted/30 border-border/40 h-1.5 w-full overflow-hidden rounded border">
      <div className={`h-full ${color} transition-all`} style={{ width: `${pct.toFixed(1)}%` }} />
    </div>
  );
}

export function SendPanel({
  messageId,
  messageStatus,
}: {
  messageId: number | null | undefined;
  messageStatus: string | null | undefined;
}) {
  const qc = useQueryClient();
  const { projectId } = useProject();
  const enabled = !!messageId;

  const history = useQuery({
    queryKey: ["sends", messageId],
    queryFn: () => sendsApi.getForMessage(messageId!),
    enabled,
    staleTime: 5_000,
  });

  const quota = useQuery({
    queryKey: ["sends-quota", projectId],
    queryFn: () => sendsApi.quota(projectId!),
    enabled: projectId != null,
    staleTime: 5_000,
  });

  const send = useMutation({
    mutationFn: () => sendsApi.send(messageId!),
    onSuccess: (res) => {
      if (res.ok) {
        toast.success(`Sent · ${res.message_id_external ?? "—"}`);
      } else {
        toast.error(res.error || res.status || "send failed");
      }
      qc.invalidateQueries({ queryKey: ["sends", messageId] });
      qc.invalidateQueries({ queryKey: ["sends-quota", projectId] });
      qc.invalidateQueries({ queryKey: ["sends-list"] });
      qc.invalidateQueries({ queryKey: ["outreach"] });
      qc.invalidateQueries({ queryKey: ["outreach-list"] });
    },
    onError: (e: unknown) => toast.error((e as Error)?.message ?? "send failed"),
  });

  if (!enabled) return null;

  const latest = history.data?.latest ?? null;
  const items: Send[] = history.data?.history ?? [];
  const remaining = quota.data?.remaining ?? 0;
  const canSend = (messageStatus ?? "").toLowerCase() === "approved" && remaining > 0;

  return (
    <div className="border-border/40 space-y-2 rounded border p-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-sm font-medium">
          <Inbox className="h-4 w-4 text-violet-400" />
          Sends
          <SendStatusBadge status={latest?.status ?? null} />
          {latest?.message_id_external && (
            <span className="text-muted-foreground font-mono text-[10px]">
              {latest.provider}:{latest.message_id_external}
            </span>
          )}
          {history.data && history.data.count > 0 && (
            <span className="text-muted-foreground text-[10px]">
              · {history.data.count} attempt{history.data.count === 1 ? "" : "s"}
            </span>
          )}
        </div>
        <Button
          size="sm"
          variant="outline"
          onClick={() => send.mutate()}
          disabled={!canSend || send.isPending}
          title={
            (messageStatus ?? "").toLowerCase() !== "approved"
              ? "approve message first"
              : remaining <= 0
                ? "daily quota exceeded"
                : "send now"
          }
        >
          {send.isPending ? (
            <RefreshCw className="mr-1 h-3 w-3 animate-spin" />
          ) : (
            <SendIcon className="mr-1 h-3 w-3" />
          )}
          Send now
        </Button>
      </div>

      {quota.data && (
        <div className="space-y-1">
          <div className="text-muted-foreground flex items-center justify-between text-[10px]">
            <span>Daily quota</span>
            <span className="font-mono">
              {quota.data.sent_today} / {quota.data.max_per_day} · {quota.data.remaining} left
            </span>
          </div>
          <QuotaBar
            sent_today={quota.data.sent_today}
            max_per_day={quota.data.max_per_day}
          />
        </div>
      )}

      {items.length > 0 ? (
        <details className="text-[10px]">
          <summary className="text-muted-foreground cursor-pointer uppercase">
            History ({items.length})
          </summary>
          <ul className="mt-1 space-y-0.5">
            {items.map((s) => (
              <li key={s.id} className="font-mono">
                <SendStatusBadge status={s.status} />{" "}
                {s.attempted_at} · {s.provider} · {s.message_id_external ?? "—"}
                {s.error_message ? (
                  <span className="text-rose-300"> · {s.error_message}</span>
                ) : null}
              </li>
            ))}
          </ul>
        </details>
      ) : (
        <div className="text-muted-foreground text-xs">No send attempts yet.</div>
      )}
    </div>
  );
}
