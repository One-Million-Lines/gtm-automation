import { useState } from "react";
import { Plus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import type { CreateExperimentInput, ExperimentVariantInput } from "@/lib/api";

type Props = {
  projectId: number;
  icpId?: number | null;
  onSubmit: (input: CreateExperimentInput) => void | Promise<void>;
  onCancel?: () => void;
  submitting?: boolean;
};

const blankVariant = (n: number, control = false): ExperimentVariantInput => ({
  name: control ? "control" : `variant_${n}`,
  weight: 1.0,
  subject_template: "",
  body_template: "",
  cta_template: "",
  is_control: control,
});

export function ExperimentForm({
  projectId, icpId, onSubmit, onCancel, submitting,
}: Props) {
  const [name, setName] = useState("");
  const [hypothesis, setHypothesis] = useState("");
  const [minSample, setMinSample] = useState("30");
  const [variants, setVariants] = useState<ExperimentVariantInput[]>([
    blankVariant(1, true),
    blankVariant(2, false),
  ]);

  const updateVariant = (idx: number, patch: Partial<ExperimentVariantInput>) => {
    setVariants((prev) => prev.map((v, i) => (i === idx ? { ...v, ...patch } : v)));
  };

  const addVariant = () => {
    setVariants((prev) => [...prev, blankVariant(prev.length + 1)]);
  };

  const removeVariant = (idx: number) => {
    setVariants((prev) => prev.filter((_, i) => i !== idx));
  };

  const setControl = (idx: number) => {
    setVariants((prev) => prev.map((v, i) => ({ ...v, is_control: i === idx })));
  };

  const canSubmit = !!name.trim() && variants.length >= 2;

  const handle = async () => {
    if (!canSubmit || submitting) return;
    await onSubmit({
      project_id: projectId,
      icp_id: icpId ?? null,
      name: name.trim(),
      hypothesis: hypothesis.trim() || undefined,
      min_sample_size: Number(minSample) || 30,
      variants,
    });
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-2 gap-4">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="exp-name">Name</Label>
          <Input
            id="exp-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. subject_test_v1"
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="min-sample">Min sample size per variant</Label>
          <Input
            id="min-sample"
            type="number"
            min={1}
            value={minSample}
            onChange={(e) => setMinSample(e.target.value)}
          />
        </div>
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="hypothesis">Hypothesis</Label>
        <Textarea
          id="hypothesis"
          rows={2}
          value={hypothesis}
          onChange={(e) => setHypothesis(e.target.value)}
          placeholder="Short subject lines drive higher positive reply rate."
        />
      </div>

      <div className="flex flex-col gap-3">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-medium">Variants</h3>
          <Button type="button" variant="outline" size="sm" onClick={addVariant}>
            <Plus className="h-3 w-3 mr-1" /> Add variant
          </Button>
        </div>
        {variants.map((v, idx) => (
          <div
            key={idx}
            className="rounded-md border border-border/40 p-3 flex flex-col gap-2 bg-card/30"
          >
            <div className="flex items-center gap-3">
              <Input
                className="max-w-45"
                value={v.name}
                onChange={(e) => updateVariant(idx, { name: e.target.value })}
                placeholder="variant name"
              />
              <Input
                type="number"
                step="0.1"
                min={0}
                className="max-w-25"
                value={v.weight ?? 1}
                onChange={(e) =>
                  updateVariant(idx, { weight: Number(e.target.value) || 0 })
                }
                placeholder="weight"
              />
              <div className="flex items-center gap-2 ml-2">
                <Switch
                  checked={!!v.is_control}
                  onCheckedChange={(c) => c && setControl(idx)}
                />
                <span className="text-xs text-muted-foreground">control</span>
              </div>
              <div className="flex-1" />
              {variants.length > 2 && (
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  onClick={() => removeVariant(idx)}
                >
                  <Trash2 className="h-4 w-4 text-rose-300" />
                </Button>
              )}
            </div>
            <Input
              value={v.subject_template ?? ""}
              onChange={(e) => updateVariant(idx, { subject_template: e.target.value })}
              placeholder="subject template — supports {first_name}, {company_name}, ..."
            />
            <Textarea
              rows={3}
              value={v.body_template ?? ""}
              onChange={(e) => updateVariant(idx, { body_template: e.target.value })}
              placeholder="body template — supports {first_name}, {company_name}, ..."
            />
          </div>
        ))}
      </div>

      <div className="flex justify-end gap-2 pt-2">
        {onCancel && (
          <Button type="button" variant="outline" onClick={onCancel}>
            Cancel
          </Button>
        )}
        <Button type="button" onClick={handle} disabled={!canSubmit || submitting}>
          {submitting ? "Creating…" : "Create experiment"}
        </Button>
      </div>
    </div>
  );
}
