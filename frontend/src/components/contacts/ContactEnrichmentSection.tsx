import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { contactEnrichmentApi, type ContactEnrichmentSnapshot } from "@/lib/api";
import { toast } from "sonner";

const STATUS_VARIANT: Record<string, string> = {
  valid: "bg-emerald-500/15 text-emerald-300 border-emerald-700",
  risky: "bg-amber-500/15 text-amber-300 border-amber-700",
  role: "bg-sky-500/15 text-sky-300 border-sky-700",
  disposable: "bg-fuchsia-500/15 text-fuchsia-300 border-fuchsia-700",
  invalid: "bg-rose-500/15 text-rose-300 border-rose-700",
  unverified: "bg-zinc-500/15 text-zinc-300 border-zinc-700",
};

export function StatusPill({ status }: { status: string | null | undefined }) {
  if (!status) return <span className="text-muted-foreground text-xs">—</span>;
  const cls = STATUS_VARIANT[status] ?? STATUS_VARIANT.unverified;
  return (
    <span className={`rounded border px-1.5 py-0.5 text-[10px] font-medium uppercase ${cls}`}>
      {status}
    </span>
  );
}

export function ConfidenceBar({ value }: { value: number | null | undefined }) {
  const v = Math.max(0, Math.min(1, value ?? 0));
  const pct = Math.round(v * 100);
  return (
    <div className="bg-muted h-1.5 w-16 overflow-hidden rounded">
      <div
        className="h-full bg-emerald-500"
        style={{ width: `${pct}%` }}
        title={`confidence ${pct}%`}
      />
    </div>
  );
}

export function ContactEnrichmentSection({ contactId }: { contactId: number }) {
  const qc = useQueryClient();
  const [showRaw, setShowRaw] = useState(false);

  const q = useQuery({
    queryKey: ["contact-enrichment", contactId],
    queryFn: () => contactEnrichmentApi.getEnrichment(contactId),
  });

  const m = useMutation({
    mutationFn: () => contactEnrichmentApi.enrichOne(contactId),
    onSuccess: (res) => {
      toast.success(
        res.skipped
          ? `Skipped: ${res.error}`
          : `Enriched · ${res.status} · conf ${Math.round((res.confidence ?? 0) * 100)}%`,
      );
      qc.invalidateQueries({ queryKey: ["contact-enrichment", contactId] });
      qc.invalidateQueries({ queryKey: ["contact", contactId] });
      qc.invalidateQueries({ queryKey: ["contacts"] });
    },
    onError: (err: unknown) => {
      const e = err as { response?: { data?: { detail?: string } }; message?: string };
      toast.error(e.response?.data?.detail ?? e.message ?? "Enrichment failed");
    },
  });

  const latest = q.data?.latest;
  const snap: ContactEnrichmentSnapshot | null = latest?.raw_data ?? null;
  const hasAny = q.data && q.data.count > 0;

  return (
    <div className="border-border/40 rounded-md border p-3">
      <div className="mb-2 flex items-center justify-between">
        <div className="font-semibold">Email enrichment</div>
        <Button
          size="sm"
          variant="outline"
          onClick={() => m.mutate()}
          disabled={m.isPending}
        >
          <Sparkles className="mr-1 h-3.5 w-3.5" />
          {hasAny ? "Re-enrich" : "Enrich"}
        </Button>
      </div>

      {q.isLoading ? (
        <p className="text-muted-foreground text-xs">Loading…</p>
      ) : !hasAny ? (
        <p className="text-muted-foreground text-xs">No enrichment yet.</p>
      ) : snap ? (
        <div className="space-y-2 text-xs">
          <div className="flex flex-wrap items-center gap-2">
            <StatusPill status={latest?.email_status ?? snap.email_status} />
            <ConfidenceBar value={latest?.email_confidence ?? snap.email_confidence} />
            <span className="text-muted-foreground">
              conf {Math.round(((latest?.email_confidence ?? snap.email_confidence) ?? 0) * 100)}%
            </span>
            {snap.is_free && <Badge variant="secondary">free</Badge>}
            {snap.is_role && <Badge variant="secondary">role</Badge>}
            {snap.is_disposable && <Badge variant="destructive">disposable</Badge>}
            {snap.is_catch_all && <Badge variant="secondary">catch-all</Badge>}
            {snap.has_mx === false && <Badge variant="destructive">no MX</Badge>}
            {snap.has_mx === true && <Badge variant="outline">MX ok</Badge>}
            {snap.typo_corrected_from && (
              <Badge variant="outline">
                typo: {snap.typo_corrected_from} → {snap.domain}
              </Badge>
            )}
          </div>
          <div className="bg-muted/30 grid grid-cols-2 gap-2 rounded p-2">
            <div>
              <div className="text-muted-foreground text-[10px] uppercase">Email</div>
              <div className="truncate">{snap.email ?? "—"}</div>
            </div>
            <div>
              <div className="text-muted-foreground text-[10px] uppercase">Domain</div>
              <div className="truncate">{snap.domain ?? "—"}</div>
            </div>
            <div>
              <div className="text-muted-foreground text-[10px] uppercase">Reason</div>
              <div className="truncate">{snap.reason}</div>
            </div>
            <div>
              <div className="text-muted-foreground text-[10px] uppercase">History</div>
              <div>{q.data?.count ?? 0} snapshot(s)</div>
            </div>
          </div>
          <button
            onClick={() => setShowRaw((v) => !v)}
            className="text-muted-foreground hover:text-foreground text-[10px] underline"
          >
            {showRaw ? "Hide" : "Show"} raw snapshot
          </button>
          {showRaw && (
            <pre className="bg-muted/40 max-h-60 overflow-auto whitespace-pre-wrap break-all rounded p-2 text-[10px]">
              {JSON.stringify(snap, null, 2)}
            </pre>
          )}
        </div>
      ) : null}
    </div>
  );
}
