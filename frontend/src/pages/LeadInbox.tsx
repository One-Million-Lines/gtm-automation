import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  Inbox, RefreshCw, Send, ChevronDown, ChevronRight, Bot, Pencil,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { useProject } from "@/state/projectStore";
import {
  threadsApi,
  type LeadThread,
  type LeadThreadDetail,
  type ThreadMessage,
} from "@/lib/api";

// ── helpers ──────────────────────────────────────────────────────────────────

const STATUS_COLORS: Record<string, string> = {
  open: "bg-blue-100 text-blue-800",
  awaiting_reply: "bg-yellow-100 text-yellow-800",
  replied: "bg-green-100 text-green-800",
  closed: "bg-gray-100 text-gray-700",
  bounced: "bg-red-100 text-red-700",
};

function StatusBadge({ status }: { status: string }) {
  return (
    <span className={cn("text-xs px-2 py-0.5 rounded-full font-medium", STATUS_COLORS[status] ?? "bg-gray-100 text-gray-700")}>
      {status.replace("_", " ")}
    </span>
  );
}

function DirectionBubble({ msg }: { msg: ThreadMessage }) {
  const isOut = msg.direction === "out";
  const [expanded, setExpanded] = useState(false);
  const hasRationale = Boolean(msg.decision_trace?.rationale);
  const ts = msg.sent_at ?? msg.received_at ?? msg.created_at;

  return (
    <div className={cn("flex flex-col gap-1 max-w-[80%]", isOut ? "self-end items-end" : "self-start items-start")}>
      <div className="flex items-center gap-1 text-xs text-muted-foreground">
        {isOut ? <Send className="h-3 w-3" /> : <Inbox className="h-3 w-3" />}
        <span>{msg.source}</span>
        {ts && <span>· {new Date(ts).toLocaleString()}</span>}
      </div>
      <div
        className={cn(
          "rounded-xl px-4 py-2 text-sm shadow-sm whitespace-pre-wrap",
          isOut
            ? "bg-primary text-primary-foreground"
            : "bg-secondary text-foreground",
        )}
      >
        {msg.subject && <div className="font-semibold mb-1">{msg.subject}</div>}
        {msg.body_text || <span className="italic text-xs opacity-60">[no body]</span>}
      </div>
      {hasRationale && (
        <button
          className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
          onClick={() => setExpanded((v) => !v)}
        >
          <Bot className="h-3 w-3" />
          {expanded ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
          Reasoning
        </button>
      )}
      {expanded && hasRationale && (
        <div className="text-xs bg-muted rounded-md px-3 py-2 max-w-sm whitespace-pre-wrap">
          <div className="font-medium mb-1">
            {msg.decision_trace?.model_name} · conf={msg.decision_trace?.confidence?.toFixed(2)}
          </div>
          {msg.decision_trace?.rationale}
        </div>
      )}
    </div>
  );
}

// ── Thread Detail panel ───────────────────────────────────────────────────────

function ThreadDetail({
  thread,
  onStatusChange,
}: {
  thread: LeadThread;
  onStatusChange: (status: string) => void;
}) {
  const qc = useQueryClient();
  const detail = useQuery({
    queryKey: ["thread-detail", thread.id],
    queryFn: () => threadsApi.get(thread.id),
  });

  const draftReply = useMutation({
    mutationFn: () => threadsApi.draftReply(thread.id),
    onSuccess: () => {
      toast.success("Reply draft generated");
      qc.invalidateQueries({ queryKey: ["thread-detail", thread.id] });
      qc.invalidateQueries({ queryKey: ["threads-list"] });
    },
    onError: (e: unknown) => toast.error((e as Error)?.message ?? "draft failed"),
  });

  const patchStatus = useMutation({
    mutationFn: (status: string) => threadsApi.patch(thread.id, { status }),
    onSuccess: (updated) => {
      onStatusChange(updated.status);
      qc.invalidateQueries({ queryKey: ["threads-list"] });
      qc.invalidateQueries({ queryKey: ["thread-detail", thread.id] });
    },
    onError: (e: unknown) => toast.error((e as Error)?.message ?? "update failed"),
  });

  const messages: ThreadMessage[] = detail.data?.messages ?? [];

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b">
        <div>
          <div className="font-semibold text-sm">{thread.subject ?? "(no subject)"}</div>
          <div className="flex items-center gap-2 mt-1">
            <StatusBadge status={thread.status} />
            <span className="text-xs text-muted-foreground">{thread.message_count} messages</span>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button
            size="sm"
            variant="outline"
            disabled={draftReply.isPending}
            onClick={() => draftReply.mutate()}
          >
            <Pencil className="h-3 w-3 mr-1" />
            Generate reply
          </Button>
          {thread.status !== "closed" && (
            <Button
              size="sm"
              variant="ghost"
              disabled={patchStatus.isPending}
              onClick={() => patchStatus.mutate("closed")}
            >
              Close
            </Button>
          )}
        </div>
      </div>
      {/* Timeline */}
      <div className="flex-1 overflow-auto p-4 flex flex-col gap-3">
        {detail.isLoading && (
          <div className="text-sm text-muted-foreground">Loading…</div>
        )}
        {messages.map((msg) => (
          <DirectionBubble key={msg.id} msg={msg} />
        ))}
        {messages.length === 0 && !detail.isLoading && (
          <div className="text-sm text-muted-foreground text-center mt-8">No messages yet</div>
        )}
      </div>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

const STATUS_FILTERS = ["all", "open", "awaiting_reply", "replied", "closed", "bounced"] as const;
type StatusFilter = typeof STATUS_FILTERS[number];

export default function LeadInboxPage() {
  const qc = useQueryClient();
  const { projectId } = useProject();
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [selectedId, setSelectedId] = useState<number | null>(null);

  const list = useQuery({
    queryKey: ["threads-list", projectId, statusFilter],
    queryFn: () =>
      threadsApi.list({
        project_id: projectId!,
        status: statusFilter === "all" ? undefined : statusFilter,
        limit: 200,
      }),
    enabled: projectId != null,
  });

  const reconcile = useMutation({
    mutationFn: () => threadsApi.reconcile(projectId!),
    onSuccess: (res) => {
      toast.success(`Reconcile: created=${res.created} updated=${res.updated} skipped=${res.skipped}`);
      qc.invalidateQueries({ queryKey: ["threads-list"] });
    },
    onError: (e: unknown) => toast.error((e as Error)?.message ?? "reconcile failed"),
  });

  const threads = list.data?.data ?? [];
  const selected = threads.find((t) => t.id === selectedId) ?? null;

  return (
    <div className="flex h-[calc(100vh-3.5rem)] overflow-hidden">
      {/* Sidebar */}
      <div className="w-80 shrink-0 border-r flex flex-col">
        <div className="p-4 border-b flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Inbox className="h-5 w-5 text-primary" />
            <h1 className="text-base font-semibold">Lead Inbox</h1>
          </div>
          <Button
            size="icon"
            variant="ghost"
            onClick={() => reconcile.mutate()}
            disabled={reconcile.isPending || projectId == null}
            title="Reconcile threads"
          >
            <RefreshCw className={cn("h-4 w-4", reconcile.isPending && "animate-spin")} />
          </Button>
        </div>
        {/* Status filters */}
        <div className="flex flex-wrap gap-1 p-2 border-b">
          {STATUS_FILTERS.map((s) => (
            <button
              key={s}
              onClick={() => setStatusFilter(s)}
              className={cn(
                "text-xs px-2 py-1 rounded-full border",
                statusFilter === s
                  ? "bg-primary text-primary-foreground border-primary"
                  : "border-border text-muted-foreground hover:border-foreground",
              )}
            >
              {s.replace("_", " ")}
            </button>
          ))}
        </div>
        {/* Thread list */}
        <div className="flex-1 overflow-auto">
          {list.isLoading && (
            <div className="p-4 text-sm text-muted-foreground">Loading…</div>
          )}
          {threads.map((t) => (
            <button
              key={t.id}
              className={cn(
                "w-full text-left px-4 py-3 border-b hover:bg-muted/50 transition-colors",
                selectedId === t.id && "bg-muted",
              )}
              onClick={() => setSelectedId(t.id)}
            >
              <div className="flex items-center justify-between mb-1">
                <span className="text-sm font-medium truncate">
                  {t.subject ?? "(no subject)"}
                </span>
                <StatusBadge status={t.status} />
              </div>
              <div className="text-xs text-muted-foreground flex items-center gap-2">
                <span>{t.message_count} msgs</span>
                {t.last_message_at && (
                  <span>· {new Date(t.last_message_at).toLocaleDateString()}</span>
                )}
              </div>
            </button>
          ))}
          {threads.length === 0 && !list.isLoading && (
            <div className="p-4 text-sm text-muted-foreground text-center">
              No threads. Click reconcile to import from sends.
            </div>
          )}
        </div>
      </div>

      {/* Detail panel */}
      <div className="flex-1 overflow-hidden">
        {selected ? (
          <ThreadDetail
            key={selected.id}
            thread={selected}
            onStatusChange={() => qc.invalidateQueries({ queryKey: ["threads-list"] })}
          />
        ) : (
          <div className="flex items-center justify-center h-full text-muted-foreground text-sm">
            Select a thread to view
          </div>
        )}
      </div>
    </div>
  );
}
