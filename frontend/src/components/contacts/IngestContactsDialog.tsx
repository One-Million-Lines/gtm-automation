import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { contactsApi, icpsApi } from "@/lib/api";

type Props = {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  projectId: number;
};

type ParsedRecords = {
  records: Record<string, unknown>[];
  error?: string;
};

function parseInput(text: string): ParsedRecords {
  const trimmed = text.trim();
  if (!trimmed) return { records: [] };
  if (trimmed.startsWith("[") || trimmed.startsWith("{")) {
    try {
      const parsed = JSON.parse(trimmed);
      const arr = Array.isArray(parsed) ? parsed : [parsed];
      return { records: arr.filter((x) => x && typeof x === "object") };
    } catch (e) {
      return { records: [], error: `JSON parse error: ${(e as Error).message}` };
    }
  }
  const lines = trimmed.split(/\r?\n/).filter((l) => l.trim());
  if (lines.length < 2) return { records: [], error: "CSV needs header + at least one row" };
  const headers = splitCSV(lines[0]);
  const records: Record<string, unknown>[] = [];
  for (let i = 1; i < lines.length; i++) {
    const cells = splitCSV(lines[i]);
    const rec: Record<string, unknown> = {};
    headers.forEach((h, idx) => {
      const v = cells[idx];
      if (v !== undefined && v !== "") rec[h.trim()] = v;
    });
    if (Object.keys(rec).length) records.push(rec);
  }
  return { records };
}

function splitCSV(line: string): string[] {
  const out: string[] = [];
  let cur = "";
  let inQ = false;
  for (let i = 0; i < line.length; i++) {
    const c = line[i];
    if (inQ) {
      if (c === '"' && line[i + 1] === '"') { cur += '"'; i++; }
      else if (c === '"') inQ = false;
      else cur += c;
    } else {
      if (c === ",") { out.push(cur); cur = ""; }
      else if (c === '"' && !cur) inQ = true;
      else cur += c;
    }
  }
  out.push(cur);
  return out.map((s) => s.trim());
}

function validateRecords(records: Record<string, unknown>[]): string | undefined {
  if (records.length === 0) return undefined;
  const missing = records.filter(
    (r) => !r.company_id && !r.company_domain && !r.domain,
  );
  if (missing.length === records.length) {
    return "Every record must have company_id or company_domain.";
  }
  if (missing.length > 0) {
    return `${missing.length} record(s) missing company_id/company_domain — they will be skipped.`;
  }
  return undefined;
}

export function IngestContactsDialog({ open, onOpenChange, projectId }: Props) {
  const qc = useQueryClient();
  const [sourceName, setSourceName] = useState("manual");
  const [icpId, setIcpId] = useState<string>("");
  const [text, setText] = useState("");

  useEffect(() => {
    if (open) { setText(""); setSourceName("manual"); }
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

  const parsed = useMemo<ParsedRecords>(() => parseInput(text), [text]);
  const warning = useMemo(() => validateRecords(parsed.records), [parsed.records]);
  const blockingError =
    parsed.error ?? (warning && warning.startsWith("Every record") ? warning : undefined);

  const mutate = useMutation({
    mutationFn: () =>
      contactsApi.ingest({
        projectId,
        icpId: Number(icpId),
        sourceName: sourceName.trim() || "manual",
        records: parsed.records,
      }),
    onSuccess: (s) => {
      toast.success(
        `Ingest done — created ${s.created}, updated ${s.updated}, skipped ${s.skipped}` +
        ` (leads: +${s.leads_created} new, ${s.leads_attached} attached)`,
      );
      qc.invalidateQueries({ queryKey: ["contacts", projectId] });
      qc.invalidateQueries({ queryKey: ["companies", projectId] });
      onOpenChange(false);
    },
    onError: (e: { message?: string }) => toast.error(e?.message ?? "Ingest failed"),
  });

  const canSubmit =
    parsed.records.length > 0 && !blockingError && icpId !== "" && !mutate.isPending;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] max-w-2xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Ingest contacts</DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label>Active ICP (required)</Label>
            <Select value={icpId} onValueChange={setIcpId}>
              <SelectTrigger>
                <SelectValue placeholder={
                  icps.isLoading ? "Loading…" :
                  (icps.data?.length ? "Pick an ICP" : "No active ICPs — create one first")
                } />
              </SelectTrigger>
              <SelectContent>
                {(icps.data ?? []).map((i) => (
                  <SelectItem key={i.id} value={String(i.id)}>{i.name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="src">Source name</Label>
            <Input id="src" value={sourceName} onChange={(e) => setSourceName(e.target.value)} />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="recs">
              Records — paste JSON array or CSV (with headers). Each row needs
              <code className="mx-1">company_id</code> or
              <code className="mx-1">company_domain</code>.
            </Label>
            <Textarea
              id="recs"
              rows={10}
              placeholder={
                '[{"first_name":"Jane","last_name":"Doe","email":"jane@acme.com",' +
                '"job_title":"CMO","company_domain":"acme.com"}, …]'
              }
              value={text}
              onChange={(e) => setText(e.target.value)}
              className="font-mono text-xs"
            />
            <div className="text-muted-foreground text-xs">
              {parsed.error ? (
                <span className="text-destructive">{parsed.error}</span>
              ) : (
                <>
                  Parsed {parsed.records.length} record(s).
                  {warning && (
                    <span className={
                      warning.startsWith("Every record") ? "text-destructive ml-2" : "ml-2 text-amber-500"
                    }>{warning}</span>
                  )}
                </>
              )}
            </div>
          </div>

          {parsed.records.length > 0 && (
            <div className="bg-muted/40 rounded-md p-2 text-xs">
              <div className="text-muted-foreground mb-1">Preview (first 3):</div>
              <pre className="overflow-x-auto whitespace-pre-wrap break-all">
                {JSON.stringify(parsed.records.slice(0, 3), null, 2)}
              </pre>
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button disabled={!canSubmit} onClick={() => mutate.mutate()}>
            {mutate.isPending ? "Ingesting…" : `Ingest ${parsed.records.length}`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
