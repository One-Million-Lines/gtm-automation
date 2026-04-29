import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { contactEnrichmentApi, icpsApi } from "@/lib/api";

type Props = {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  projectId: number;
};

const PLACEHOLDER = `email,first_name,last_name,job_title,email_status,email_confidence,linkedin_url,company_domain
alex@acme.com,Alex,Doe,Head of Marketing,valid,0.9,https://linkedin.com/in/alex,acme.com
info@beta.io,,,Sales,role,0.4,,beta.io`;

export function ImportEnrichedDialog({ open, onOpenChange, projectId }: Props) {
  const qc = useQueryClient();
  const [icpId, setIcpId] = useState<string>("");
  const [csv, setCsv] = useState("");

  useEffect(() => {
    if (open) setCsv("");
  }, [open]);

  const icps = useQuery({
    queryKey: ["icps", projectId, "active"],
    queryFn: () => icpsApi.list(projectId, "active"),
    enabled: open,
  });

  useEffect(() => {
    if (!icpId && icps.data && icps.data.length) {
      setIcpId(String(icps.data[0].id));
    }
  }, [icps.data, icpId]);

  const lineCount = useMemo(() => {
    const lines = csv.split(/\r?\n/).filter((l) => l.trim());
    return Math.max(0, lines.length - 1);
  }, [csv]);

  const m = useMutation({
    mutationFn: () =>
      contactEnrichmentApi.importCsv({
        project_id: projectId,
        icp_id: Number(icpId),
        csv,
        source_name: "csv_enriched_import",
      }),
    onSuccess: (res) => {
      toast.success(
        `Imported: created=${res.created}, updated=${res.updated}, enriched=${res.enriched}, skipped=${res.skipped}`,
      );
      qc.invalidateQueries({ queryKey: ["contacts"] });
      onOpenChange(false);
    },
    onError: (err: unknown) => {
      const e = err as { response?: { data?: { detail?: string } }; message?: string };
      toast.error(e.response?.data?.detail ?? e.message ?? "Import failed");
    },
  });

  const canSubmit = !!icpId && lineCount > 0 && !m.isPending;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Import enriched contacts (CSV)</DialogTitle>
        </DialogHeader>

        <div className="space-y-3">
          <div>
            <Label className="mb-1 block text-xs">ICP</Label>
            <Select value={icpId} onValueChange={setIcpId}>
              <SelectTrigger>
                <SelectValue placeholder="Select ICP" />
              </SelectTrigger>
              <SelectContent>
                {(icps.data ?? []).map((i) => (
                  <SelectItem key={i.id} value={String(i.id)}>
                    {i.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div>
            <div className="mb-1 flex items-center justify-between">
              <Label className="text-xs">CSV (header + rows)</Label>
              <span className="text-muted-foreground text-[10px]">
                {lineCount} row(s) detected
              </span>
            </div>
            <Textarea
              value={csv}
              onChange={(e) => setCsv(e.target.value)}
              placeholder={PLACEHOLDER}
              className="h-64 font-mono text-xs"
            />
            <p className="text-muted-foreground mt-1 text-[10px]">
              Header columns recognized: <code>email, first_name, last_name, full_name,
              job_title, email_status, email_confidence, linkedin_url, company_id,
              company_domain, country, city</code>. Each record needs at least an email
              or linkedin_url plus a way to resolve the company (<code>company_id</code>,
              <code>company_domain</code>, or matching email domain).
            </p>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={m.isPending}>
            Cancel
          </Button>
          <Button onClick={() => m.mutate()} disabled={!canSubmit}>
            {m.isPending ? "Importing…" : "Import + enrich"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
