import { useQuery } from "@tanstack/react-query";
import { MessageSquare } from "lucide-react";
import { repliesApi, type Reply } from "@/lib/api";
import { ReplyIntentBadge } from "./ReplyIntentBadge";

export function ReplyPanel({
  messageId,
}: {
  messageId: number | null | undefined;
}) {
  const enabled = !!messageId;

  const history = useQuery({
    queryKey: ["replies", messageId],
    queryFn: () => repliesApi.getForMessage(messageId!),
    enabled,
    staleTime: 5_000,
  });

  if (!enabled) return null;

  const latest = history.data?.latest ?? null;
  const items: Reply[] = history.data?.history ?? [];

  return (
    <div className="border-border/40 space-y-2 rounded border p-3">
      <div className="flex items-center gap-2 text-sm font-medium">
        <MessageSquare className="h-4 w-4 text-fuchsia-400" />
        Replies
        <ReplyIntentBadge intent={latest?.intent ?? null} confidence={latest?.confidence} />
        {history.data && history.data.count > 0 && (
          <span className="text-muted-foreground text-[10px]">
            · {history.data.count} reply{history.data.count === 1 ? "" : "ies"}
          </span>
        )}
      </div>

      {items.length > 0 ? (
        <ul className="space-y-2 text-xs">
          {items.map((r) => (
            <li
              key={r.id}
              className="border-border/30 space-y-1 rounded border p-2"
            >
              <div className="flex items-center gap-2">
                <ReplyIntentBadge intent={r.intent} confidence={r.confidence} />
                <span className="text-muted-foreground font-mono text-[10px]">
                  {r.received_at ?? "—"}
                </span>
                <span className="text-muted-foreground font-mono text-[10px]">
                  {r.classifier ?? ""}
                </span>
              </div>
              <div className="text-[11px]">
                <span className="text-muted-foreground">from </span>
                <span className="font-medium">{r.from_name ?? r.from_email ?? "—"}</span>
                {r.from_email && r.from_name ? (
                  <span className="text-muted-foreground"> &lt;{r.from_email}&gt;</span>
                ) : null}
              </div>
              {r.subject ? (
                <div className="text-[11px] font-medium">{r.subject}</div>
              ) : null}
              {r.body ? (
                <div className="text-muted-foreground line-clamp-3 whitespace-pre-wrap text-[11px]">
                  {r.body}
                </div>
              ) : null}
            </li>
          ))}
        </ul>
      ) : (
        <div className="text-muted-foreground text-xs">No replies yet.</div>
      )}
    </div>
  );
}
