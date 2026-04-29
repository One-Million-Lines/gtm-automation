import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Mail, RefreshCw, Send, Copy, Check, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { outreachApi, qualityApi, type OutreachStatus } from "@/lib/api";
import { QualityPanel } from "@/components/quality/QualityPanel";
import { SendPanel } from "@/components/sends/SendPanel";
import { ReplyPanel } from "@/components/replies/ReplyPanel";

const STATUS_COLORS: Record<OutreachStatus, string> = {
  draft: "bg-zinc-500/20 text-zinc-300 border-zinc-600",
  approved: "bg-emerald-500/20 text-emerald-300 border-emerald-600",
  sent: "bg-sky-500/20 text-sky-300 border-sky-600",
};

export function OutreachStatusBadge({ status }: { status: OutreachStatus | null | undefined }) {
  if (!status) {
    return (
      <Badge variant="outline" className="border-border/40 text-muted-foreground">
        none
      </Badge>
    );
  }
  return (
    <Badge variant="outline" className={`border ${STATUS_COLORS[status]} font-mono`}>
      {status}
    </Badge>
  );
}

export function OutreachPanel({ leadId }: { leadId: number | null | undefined }) {
  const qc = useQueryClient();
  const enabled = !!leadId;
  const [dryRun, setDryRun] = useState(false);
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [dirty, setDirty] = useState(false);
  const [forceApprove, setForceApprove] = useState(false);

  const q = useQuery({
    queryKey: ["outreach", leadId],
    queryFn: () => outreachApi.getForLead(leadId!),
    enabled,
    staleTime: 5_000,
  });

  const latest = q.data?.latest ?? null;

  useEffect(() => {
    if (latest && !dirty) {
      setSubject(latest.subject ?? "");
      setBody(latest.body ?? "");
    }
    if (!latest) {
      setSubject("");
      setBody("");
    }
  }, [latest, dirty]);

  const generate = useMutation({
    mutationFn: () => outreachApi.generate(leadId!, { dry_run: dryRun }),
    onSuccess: (res) => {
      if (res.ok) {
        toast.success(
          dryRun ? "Dry-run draft generated (not saved)" : `Draft generated · ${res.model ?? "—"}`,
        );
        setDirty(false);
      } else {
        toast.error(res.error || "generate failed");
      }
      qc.invalidateQueries({ queryKey: ["outreach", leadId] });
      qc.invalidateQueries({ queryKey: ["outreach-list"] });
    },
    onError: (e: unknown) => toast.error((e as Error)?.message ?? "generate failed"),
  });

  const qualityQ = useQuery({
    queryKey: ["quality", latest?.id ?? null],
    queryFn: () => qualityApi.getForMessage(latest!.id),
    enabled: !!latest?.id,
    staleTime: 5_000,
  });
  const latestQuality = qualityQ.data?.latest ?? null;
  const qualityPassed = !!latestQuality && !!latestQuality.passed;

  const approve = useMutation({
    mutationFn: () => outreachApi.approve(latest!.id, forceApprove ? { force: true } : undefined),
    onSuccess: (res) => {
      toast.success(res.forced ? "Force-approved (gate bypassed)" : "Approved");
      setForceApprove(false);
      qc.invalidateQueries({ queryKey: ["outreach", leadId] });
      qc.invalidateQueries({ queryKey: ["outreach-list"] });
    },
    onError: (e: unknown) => toast.error((e as Error)?.message ?? "approve failed"),
  });

  const save = useMutation({
    mutationFn: () => outreachApi.edit(latest!.id, { subject, body }),
    onSuccess: () => {
      toast.success("Saved");
      setDirty(false);
      qc.invalidateQueries({ queryKey: ["outreach", leadId] });
      qc.invalidateQueries({ queryKey: ["outreach-list"] });
    },
    onError: (e: unknown) => toast.error((e as Error)?.message ?? "save failed"),
  });

  const copy = async () => {
    const text = `Subject: ${subject}\n\n${body}`;
    try {
      await navigator.clipboard.writeText(text);
      toast.success("Copied");
    } catch {
      toast.error("Copy failed");
    }
  };

  if (!enabled) return null;

  const signals = latest?.context?.signals_top ?? [];

  return (
    <div className="border-border/40 space-y-3 rounded border p-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-sm font-medium">
          <Mail className="h-4 w-4 text-sky-400" />
          Outreach
          <OutreachStatusBadge status={latest?.status ?? null} />
          {q.data && q.data.count > 0 && (
            <span className="text-muted-foreground text-[10px]">
              · {q.data.count} version{q.data.count === 1 ? "" : "s"}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <label className="text-muted-foreground flex items-center gap-1 text-[10px]">
            <input
              type="checkbox"
              checked={dryRun}
              onChange={(e) => setDryRun(e.target.checked)}
              className="h-3 w-3"
            />
            dry-run
          </label>
          <Button
            size="sm"
            variant="outline"
            onClick={() => generate.mutate()}
            disabled={generate.isPending}
          >
            {latest ? (
              <RefreshCw className={`mr-1 h-3 w-3 ${generate.isPending ? "animate-spin" : ""}`} />
            ) : (
              <Sparkles className={`mr-1 h-3 w-3 ${generate.isPending ? "animate-pulse" : ""}`} />
            )}
            {latest ? "Re-generate" : "Generate"}
          </Button>
        </div>
      </div>

      {q.isLoading ? (
        <div className="text-muted-foreground text-xs">Loading…</div>
      ) : !latest ? (
        <div className="text-muted-foreground text-xs">
          No draft yet. Click Generate to compose one.
        </div>
      ) : (
        <>
          <div className="space-y-1">
            <div className="text-muted-foreground text-[10px] uppercase">Subject</div>
            <input
              value={subject}
              onChange={(e) => { setSubject(e.target.value); setDirty(true); }}
              className="bg-muted/30 border-border/40 w-full rounded border px-2 py-1 text-sm"
            />
          </div>
          <div className="space-y-1">
            <div className="text-muted-foreground text-[10px] uppercase">Body</div>
            <textarea
              value={body}
              onChange={(e) => { setBody(e.target.value); setDirty(true); }}
              rows={8}
              className="bg-muted/30 border-border/40 w-full rounded border px-2 py-1 font-mono text-xs"
            />
          </div>

          {signals.length > 0 && (
            <div className="text-[10px]">
              <div className="text-muted-foreground uppercase">Grounded signals</div>
              <ul className="mt-1 space-y-0.5">
                {signals.map((s, i) => (
                  <li key={i} className="font-mono">
                    · {s.signal_type ?? "?"} (s={(s.strength ?? 0).toFixed(2)} r=
                    {(s.recency ?? 0).toFixed(2)})
                  </li>
                ))}
              </ul>
            </div>
          )}

          <QualityPanel messageId={latest.id} />

          <SendPanel messageId={latest.id} messageStatus={latest.status} />

          <ReplyPanel messageId={latest.id} />

          <div className="text-muted-foreground text-[10px]">
            model={latest.model ?? "—"} · prompt_tokens={latest.prompt_tokens ?? 0} ·
            completion_tokens={latest.completion_tokens ?? 0} ·{" "}
            {latest.generated_at ? `generated ${latest.generated_at}` : ""}
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <Button
              size="sm"
              variant="default"
              onClick={() => save.mutate()}
              disabled={!dirty || save.isPending}
            >
              <Check className="mr-1 h-3 w-3" />
              Save edits
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => approve.mutate()}
              disabled={
                approve.isPending ||
                latest.status === "approved" ||
                latest.status === "sent" ||
                (!qualityPassed && !forceApprove)
              }
              title={
                latest.status === "approved" || latest.status === "sent"
                  ? `already ${latest.status}`
                  : qualityPassed
                    ? "quality check passed"
                    : forceApprove
                      ? "will bypass quality gate"
                      : "quality check required (or use Force approve)"
              }
            >
              <Send className="mr-1 h-3 w-3" />
              {forceApprove ? "Force approve" : "Approve"}
            </Button>
            <label className="text-muted-foreground flex items-center gap-1 text-[10px]">
              <input
                type="checkbox"
                checked={forceApprove}
                onChange={(e) => setForceApprove(e.target.checked)}
                className="h-3 w-3"
              />
              Force approve
            </label>
            <Button size="sm" variant="ghost" onClick={copy}>
              <Copy className="mr-1 h-3 w-3" />
              Copy
            </Button>
          </div>
        </>
      )}
    </div>
  );
}
