import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { enrichmentApi } from "@/lib/api";

type Props = { companyId: number };

export function EnrichmentSection({ companyId }: Props) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);

  const q = useQuery({
    queryKey: ["enrichment", companyId],
    queryFn: () => enrichmentApi.getEnrichment(companyId),
    enabled: companyId != null,
  });

  const m = useMutation({
    mutationFn: () => enrichmentApi.enrichCompany(companyId),
    onSuccess: (res) => {
      if (res.ok) {
        toast.success(`Enriched (${res.snapshot?.ecommerce_platform ?? "no platform"})`);
      } else {
        toast.error(`Enrichment failed: ${res.error ?? "unknown"}`);
      }
      qc.invalidateQueries({ queryKey: ["enrichment", companyId] });
      qc.invalidateQueries({ queryKey: ["company", companyId] });
      qc.invalidateQueries({ queryKey: ["companies"] });
    },
    onError: (e: unknown) => {
      const msg = e instanceof Error ? e.message : String(e);
      toast.error(`Enrichment error: ${msg}`);
    },
  });

  const latest = q.data?.latest ?? null;
  const snap = latest?.raw_data ?? null;

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <div className="font-semibold">Enrichment</div>
        <Button size="sm" onClick={() => m.mutate()} disabled={m.isPending}>
          <Sparkles className="mr-1 h-4 w-4" />
          {m.isPending ? "Enriching…" : latest ? "Re-enrich" : "Enrich"}
        </Button>
      </div>

      {q.isLoading ? (
        <p className="text-muted-foreground text-xs">Loading…</p>
      ) : !latest ? (
        <p className="text-muted-foreground text-xs">No enrichment yet.</p>
      ) : (
        <div className="bg-muted/40 space-y-2 rounded-md p-2 text-xs">
          <div className="flex flex-wrap gap-2">
            <span className={
              "rounded px-1.5 py-0.5 text-[10px] " +
              ((snap?.ok ?? false)
                ? "bg-emerald-500/20 text-emerald-300"
                : "bg-red-500/20 text-red-300")
            }>
              {snap?.ok ? "ok" : "failed"} · {snap?.status_code ?? "—"}
            </span>
            {latest.ecommerce_platform && (
              <span className="rounded bg-blue-500/20 px-1.5 py-0.5 text-[10px] text-blue-200">
                {latest.ecommerce_platform}
              </span>
            )}
            {(latest.tech_stack ?? []).map((t) => (
              <span key={t} className="rounded bg-zinc-700/60 px-1.5 py-0.5 text-[10px]">{t}</span>
            ))}
          </div>

          {snap?.title && (
            <div>
              <div className="text-muted-foreground text-[10px] uppercase">Title</div>
              <div>{snap.title}</div>
            </div>
          )}
          {snap?.description && (
            <div>
              <div className="text-muted-foreground text-[10px] uppercase">Description</div>
              <div>{snap.description}</div>
            </div>
          )}
          {snap?.social_links && snap.social_links.length > 0 && (
            <div>
              <div className="text-muted-foreground text-[10px] uppercase">Social</div>
              <div className="flex flex-wrap gap-1">
                {snap.social_links.map((u) => (
                  <a key={u} href={u} target="_blank" rel="noreferrer"
                     className="text-blue-400 underline">{u}</a>
                ))}
              </div>
            </div>
          )}
          <div className="text-muted-foreground text-[10px]">
            Provider: {latest.provider} · {new Date(latest.created_at).toLocaleString()}
            {q.data && q.data.count > 1 && (
              <> · history: {q.data.count}</>
            )}
          </div>

          <button
            onClick={() => setOpen((v) => !v)}
            className="text-[10px] text-blue-400 underline"
          >
            {open ? "Hide raw" : "Show raw snapshot"}
          </button>
          {open && (
            <pre className="max-h-60 overflow-auto whitespace-pre-wrap break-all text-[10px]">
              {JSON.stringify(snap, null, 2)}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}
