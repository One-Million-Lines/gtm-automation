import { useEffect } from "react";
import { useForm, Controller } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
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
import { TagInput } from "./TagInput";
import { icpsApi, type ICP, type ICPPayload } from "@/lib/api";

const SENIORITIES = [
  "junior", "mid", "senior", "lead", "manager", "director", "vp", "c_level",
] as const;

const schema = z.object({
  name: z.string().min(1, "name required"),
  description: z.string().optional().default(""),
  target_industries: z.array(z.string()).min(1, "at least one industry"),
  target_roles: z.array(z.string()).min(1, "at least one role"),
  target_geographies: z.array(z.string()).default([]),
  target_company_size_min: z.coerce.number().int().nonnegative().nullable().optional(),
  target_company_size_max: z.coerce.number().int().nonnegative().nullable().optional(),
  target_seniorities: z.array(z.string()).default([]),
  target_buying_signals: z.array(z.string()).default([]),
  exclusion_criteria: z.string().optional().default(""),
  status: z.enum(["draft", "active"]).default("draft"),
});

type FormValues = z.infer<typeof schema>;

type Props = {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  projectId: number;
  initial?: ICP | null;
};

const empty: FormValues = {
  name: "",
  description: "",
  target_industries: [],
  target_roles: [],
  target_geographies: [],
  target_company_size_min: null,
  target_company_size_max: null,
  target_seniorities: [],
  target_buying_signals: [],
  exclusion_criteria: "",
  status: "draft",
};

function fromICP(icp: ICP): FormValues {
  const exc = icp.exclusion_rules as { raw?: string } | null;
  return {
    name: icp.name ?? "",
    description: icp.description ?? "",
    target_industries: icp.target_industries ?? [],
    target_roles: icp.target_roles ?? [],
    target_geographies: icp.target_geographies ?? [],
    target_company_size_min: icp.target_company_size_min ?? null,
    target_company_size_max: icp.target_company_size_max ?? null,
    target_seniorities: icp.target_seniorities ?? [],
    target_buying_signals: icp.buying_signals ?? [],
    exclusion_criteria: exc?.raw ?? (exc ? JSON.stringify(exc) : ""),
    status: (icp.status === "archived" ? "draft" : icp.status) as "draft" | "active",
  };
}

export function ICPFormDialog({ open, onOpenChange, projectId, initial }: Props) {
  const qc = useQueryClient();
  const isEdit = !!initial;

  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: empty,
  });

  useEffect(() => {
    if (open) form.reset(initial ? fromICP(initial) : empty);
  }, [open, initial, form]);

  const mutate = useMutation({
    mutationFn: async (values: FormValues) => {
      const payload: ICPPayload = {
        name: values.name,
        description: values.description || null,
        target_industries: values.target_industries,
        target_roles: values.target_roles,
        target_geographies: values.target_geographies,
        target_seniorities: values.target_seniorities,
        target_buying_signals: values.target_buying_signals,
        target_company_size_min: values.target_company_size_min ?? null,
        target_company_size_max: values.target_company_size_max ?? null,
        exclusion_criteria: values.exclusion_criteria || null,
        status: values.status,
      };
      if (isEdit && initial) return icpsApi.update(initial.id, payload);
      return icpsApi.create({ ...payload, project_id: projectId });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["icps", projectId] });
      toast.success(isEdit ? "ICP updated" : "ICP created");
      onOpenChange(false);
    },
    onError: (e: { message?: string }) => toast.error(e?.message ?? "Failed"),
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] max-w-2xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{isEdit ? "Edit ICP" : "New ICP"}</DialogTitle>
        </DialogHeader>

        <form
          className="space-y-4"
          onSubmit={form.handleSubmit((v) => mutate.mutate(v))}
        >
          <div className="space-y-1.5">
            <Label htmlFor="name">Name *</Label>
            <Input id="name" {...form.register("name")} />
            {form.formState.errors.name && (
              <p className="text-destructive text-xs">{form.formState.errors.name.message}</p>
            )}
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="description">Description</Label>
            <Textarea id="description" rows={2} {...form.register("description")} />
          </div>

          <div className="space-y-1.5">
            <Label>Target industries *</Label>
            <Controller
              name="target_industries"
              control={form.control}
              render={({ field }) => (
                <TagInput value={field.value} onChange={field.onChange} lowercase
                          placeholder="saas, fintech…" />
              )}
            />
            {form.formState.errors.target_industries && (
              <p className="text-destructive text-xs">
                {form.formState.errors.target_industries.message as string}
              </p>
            )}
          </div>

          <div className="space-y-1.5">
            <Label>Target roles *</Label>
            <Controller
              name="target_roles"
              control={form.control}
              render={({ field }) => (
                <TagInput value={field.value} onChange={field.onChange} lowercase
                          placeholder="cto, head of eng…" />
              )}
            />
            {form.formState.errors.target_roles && (
              <p className="text-destructive text-xs">
                {form.formState.errors.target_roles.message as string}
              </p>
            )}
          </div>

          <div className="space-y-1.5">
            <Label>Target geographies</Label>
            <Controller
              name="target_geographies"
              control={form.control}
              render={({ field }) => (
                <TagInput value={field.value} onChange={field.onChange} lowercase
                          placeholder="EU, US, DACH…" />
              )}
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="size_min">Company size min</Label>
              <Input
                id="size_min" type="number" min={0}
                {...form.register("target_company_size_min", {
                  setValueAs: (v) => (v === "" || v == null ? null : Number(v)),
                })}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="size_max">Company size max</Label>
              <Input
                id="size_max" type="number" min={0}
                {...form.register("target_company_size_max", {
                  setValueAs: (v) => (v === "" || v == null ? null : Number(v)),
                })}
              />
            </div>
          </div>

          <div className="space-y-1.5">
            <Label>Target seniorities</Label>
            <Controller
              name="target_seniorities"
              control={form.control}
              render={({ field }) => (
                <div className="flex flex-wrap gap-2">
                  {SENIORITIES.map((s) => {
                    const on = field.value.includes(s);
                    return (
                      <button
                        type="button"
                        key={s}
                        onClick={() =>
                          field.onChange(
                            on ? field.value.filter((x) => x !== s) : [...field.value, s]
                          )
                        }
                        className={
                          "rounded-md border px-2 py-1 text-xs " +
                          (on
                            ? "bg-primary text-primary-foreground border-primary"
                            : "bg-background border-input")
                        }
                      >
                        {s}
                      </button>
                    );
                  })}
                </div>
              )}
            />
          </div>

          <div className="space-y-1.5">
            <Label>Target buying signals</Label>
            <Controller
              name="target_buying_signals"
              control={form.control}
              render={({ field }) => (
                <TagInput value={field.value} onChange={field.onChange}
                          placeholder="hiring, raised funding, new product…" />
              )}
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="exclusion">Exclusion criteria (free text)</Label>
            <Textarea
              id="exclusion" rows={2}
              placeholder="e.g. exclude consulting agencies, exclude US-east customers…"
              {...form.register("exclusion_criteria")}
            />
          </div>

          <div className="space-y-1.5">
            <Label>Status</Label>
            <Controller
              name="status"
              control={form.control}
              render={({ field }) => (
                <Select value={field.value} onValueChange={field.onChange}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="draft">draft</SelectItem>
                    <SelectItem value="active">active</SelectItem>
                  </SelectContent>
                </Select>
              )}
            />
          </div>

          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={mutate.isPending}>
              {mutate.isPending ? "Saving…" : isEdit ? "Save" : "Create"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
