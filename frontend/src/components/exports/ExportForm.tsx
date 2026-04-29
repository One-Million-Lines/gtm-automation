import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  EXPORT_DESTINATIONS, EXPORT_FORMATS,
  type CreateExportInput, type ExportDestination, type ExportFormat,
} from "@/lib/api";

type Props = {
  projectId: number;
  icpId?: number | null;
  onSubmit: (input: CreateExportInput) => void | Promise<void>;
  onCancel?: () => void;
  submitting?: boolean;
};

const TIERS = ["A", "B", "C", "D"] as const;

export function ExportForm({ projectId, icpId, onSubmit, onCancel, submitting }: Props) {
  const [name, setName] = useState("");
  const [destination, setDestination] = useState<ExportDestination>("filesystem");
  const [format, setFormat] = useState<ExportFormat>("csv");
  const [minScore, setMinScore] = useState("");
  const [tiers, setTiers] = useState<string[]>([]);

  const toggleTier = (t: string) =>
    setTiers((prev) => (prev.includes(t) ? prev.filter((x) => x !== t) : [...prev, t]));

  const handleSubmit = () => {
    const filters: Record<string, unknown> = {};
    if (tiers.length > 0) filters.priority_tier = tiers;
    if (minScore.trim()) {
      const v = Number(minScore);
      if (!Number.isNaN(v)) filters.min_score = v;
    }
    void onSubmit({
      project_id: projectId,
      icp_id: icpId ?? null,
      name: name.trim() || `export-${new Date().toISOString()}`,
      destination,
      format,
      filters: Object.keys(filters).length ? filters : null,
    });
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-2">
        <Label htmlFor="exp-name">Name</Label>
        <Input
          id="exp-name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Q2 EU SaaS leads"
        />
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div className="flex flex-col gap-2">
          <Label>Destination</Label>
          <Select value={destination} onValueChange={(v) => setDestination(v as ExportDestination)}>
            <SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent>
              {EXPORT_DESTINATIONS.map((d) => (
                <SelectItem key={d} value={d}>{d}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="flex flex-col gap-2">
          <Label>Format</Label>
          <div className="flex gap-2">
            {EXPORT_FORMATS.map((f) => (
              <Button
                key={f}
                type="button"
                size="sm"
                variant={format === f ? "default" : "outline"}
                onClick={() => setFormat(f)}
                className="uppercase font-mono text-xs"
              >
                {f}
              </Button>
            ))}
          </div>
        </div>
      </div>

      <div className="flex flex-col gap-2">
        <Label>Priority tier filter</Label>
        <div className="flex gap-2">
          {TIERS.map((t) => (
            <Button
              key={t}
              type="button"
              size="sm"
              variant={tiers.includes(t) ? "default" : "outline"}
              onClick={() => toggleTier(t)}
              className="font-mono"
            >
              {t}
            </Button>
          ))}
        </div>
      </div>

      <div className="flex flex-col gap-2 max-w-45">
        <Label htmlFor="min-score">Min score</Label>
        <Input
          id="min-score"
          type="number"
          step="0.01"
          min="0"
          max="1"
          value={minScore}
          onChange={(e) => setMinScore(e.target.value)}
          placeholder="0.70"
        />
      </div>

      <div className="flex justify-end gap-2 pt-2">
        {onCancel && (
          <Button type="button" variant="outline" onClick={onCancel} disabled={submitting}>
            Cancel
          </Button>
        )}
        <Button type="button" onClick={handleSubmit} disabled={submitting}>
          {submitting ? "Creating…" : "Create export"}
        </Button>
      </div>
    </div>
  );
}
