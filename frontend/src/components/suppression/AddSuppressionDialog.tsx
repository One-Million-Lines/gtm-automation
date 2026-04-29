import { useEffect, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { suppressionApi, type SuppressionType } from "@/lib/api";

const SUPPRESSION_TYPES: SuppressionType[] = [
  "domain", "email", "company_name", "linkedin_url",
  "competitor", "customer", "unsubscribed", "bounced",
];

export function AddSuppressionDialog({
  open, onOpenChange,
}: { open: boolean; onOpenChange: (v: boolean) => void }) {
  const qc = useQueryClient();
  const [type, setType] = useState<SuppressionType>("domain");
  const [value, setValue] = useState("");
  const [reason, setReason] = useState("");

  useEffect(() => {
    if (open) { setType("domain"); setValue(""); setReason(""); }
  }, [open]);

  const mutate = useMutation({
    mutationFn: () =>
      suppressionApi.add({
        suppression_type: type, value: value.trim(),
        reason: reason.trim() || undefined,
        source: "manual",
      }),
    onSuccess: (r) => {
      toast.success(r.action === "created" ? "Added" : "Already in list");
      qc.invalidateQueries({ queryKey: ["suppression"] });
      onOpenChange(false);
    },
    onError: (e: { message?: string }) => toast.error(e?.message ?? "Add failed"),
  });

  const canSubmit = value.trim().length > 0 && !mutate.isPending;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader><DialogTitle>Add suppression entry</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label>Type</Label>
            <Select value={type} onValueChange={(v) => setType(v as SuppressionType)}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                {SUPPRESSION_TYPES.map((t) => (
                  <SelectItem key={t} value={t}>{t}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="val">Value</Label>
            <Input id="val" value={value} onChange={(e) => setValue(e.target.value)}
                   placeholder={type === "email" ? "noreply@x.com" : type.includes("domain") ? "spam.com" : "value"} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="rsn">Reason (optional)</Label>
            <Input id="rsn" value={reason} onChange={(e) => setReason(e.target.value)} />
          </div>
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button disabled={!canSubmit} onClick={() => mutate.mutate()}>
            {mutate.isPending ? "Saving…" : "Add"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
