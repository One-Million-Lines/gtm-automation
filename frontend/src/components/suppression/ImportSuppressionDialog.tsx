import { useEffect, useMemo, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
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
import { suppressionApi, type SuppressionType } from "@/lib/api";

const SUPPRESSION_TYPES: SuppressionType[] = [
  "domain", "email", "company_name", "linkedin_url",
  "competitor", "customer", "unsubscribed", "bounced",
];

type Props = {
  open: boolean;
  onOpenChange: (v: boolean) => void;
};

type Parsed = {
  records: { suppression_type: SuppressionType; value: string; reason?: string; source?: string }[];
  error?: string;
};

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

function parseBulk(text: string, defaultType: SuppressionType): Parsed {
  const trimmed = text.trim();
  if (!trimmed) return { records: [] };
  // JSON
  if (trimmed.startsWith("[") || trimmed.startsWith("{")) {
    try {
      const parsed = JSON.parse(trimmed);
      const arr = Array.isArray(parsed) ? parsed : [parsed];
      const records = arr
        .filter((x) => x && typeof x === "object")
        .map((x) => ({
          suppression_type: (x.suppression_type ?? defaultType) as SuppressionType,
          value: String(x.value ?? "").trim(),
          reason: x.reason ? String(x.reason) : undefined,
          source: x.source ? String(x.source) : undefined,
        }))
        .filter((r) => r.value);
      return { records };
    } catch (e) {
      return { records: [], error: `JSON parse error: ${(e as Error).message}` };
    }
  }
  // CSV with header OR plain values, one per line
  const lines = trimmed.split(/\r?\n/).filter((l) => l.trim());
  const headerCells = splitCSV(lines[0]).map((h) => h.toLowerCase());
  const hasHeader = headerCells.includes("value") || headerCells.includes("suppression_type");
  const records: Parsed["records"] = [];
  if (hasHeader) {
    for (let i = 1; i < lines.length; i++) {
      const cells = splitCSV(lines[i]);
      const rec: Record<string, string> = {};
      headerCells.forEach((h, idx) => { if (cells[idx]) rec[h] = cells[idx]; });
      const v = rec.value;
      if (!v) continue;
      records.push({
        suppression_type: (rec.suppression_type ?? defaultType) as SuppressionType,
        value: v,
        reason: rec.reason || undefined,
        source: rec.source || undefined,
      });
    }
  } else {
    for (const line of lines) {
      const v = line.trim();
      if (!v) continue;
      records.push({ suppression_type: defaultType, value: v });
    }
  }
  return { records };
}

export function ImportSuppressionDialog({ open, onOpenChange }: Props) {
  const qc = useQueryClient();
  const [defaultType, setDefaultType] = useState<SuppressionType>("domain");
  const [text, setText] = useState("");

  useEffect(() => {
    if (open) { setText(""); setDefaultType("domain"); }
  }, [open]);

  const parsed = useMemo<Parsed>(() => parseBulk(text, defaultType), [text, defaultType]);

  const mutate = useMutation({
    mutationFn: () => suppressionApi.bulkImport(parsed.records),
    onSuccess: (s) => {
      toast.success(
        `Import done — created ${s.created}, existing ${s.existing}, invalid ${s.invalid}`,
      );
      qc.invalidateQueries({ queryKey: ["suppression"] });
      onOpenChange(false);
    },
    onError: (e: { message?: string }) => toast.error(e?.message ?? "Import failed"),
  });

  const canSubmit = parsed.records.length > 0 && !parsed.error && !mutate.isPending;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] max-w-2xl overflow-y-auto">
        <DialogHeader><DialogTitle>Import suppression list</DialogTitle></DialogHeader>

        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label>Default suppression type (used when CSV has no header)</Label>
            <Select value={defaultType} onValueChange={(v) => setDefaultType(v as SuppressionType)}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                {SUPPRESSION_TYPES.map((t) => (
                  <SelectItem key={t} value={t}>{t}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="recs">
              Records — JSON array, CSV with headers (<code>suppression_type,value,reason?,source?</code>),
              or one value per line (uses default type).
            </Label>
            <Textarea
              id="recs"
              rows={10}
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder={'spam.com\nnoreply@evil.com\n— or —\nsuppression_type,value,reason\ndomain,spam.com,manual'}
              className="font-mono text-xs"
            />
            <div className="text-muted-foreground text-xs">
              {parsed.error ? (
                <span className="text-destructive">{parsed.error}</span>
              ) : (
                <>Parsed {parsed.records.length} record(s).</>
              )}
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button disabled={!canSubmit} onClick={() => mutate.mutate()}>
            {mutate.isPending ? "Importing…" : "Import"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
