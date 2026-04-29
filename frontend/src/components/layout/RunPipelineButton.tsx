import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Play } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Label } from "@/components/ui/label";
import { pipelineApi } from "@/lib/api";
import { useProject } from "@/state/projectStore";
import { toast } from "sonner";

export function RunPipelineButton() {
  const { projectId } = useProject();
  const [open, setOpen] = useState(false);
  const [runType, setRunType] = useState("full_pipeline");
  const [dryRun, setDryRun] = useState("false");
  const qc = useQueryClient();

  const { data: runTypes } = useQuery({
    queryKey: ["run-types"],
    queryFn: pipelineApi.runTypes,
  });

  const m = useMutation({
    mutationFn: () =>
      pipelineApi.createRun({
        project_id: projectId!,
        run_type: runType,
        dry_run: dryRun === "true",
      }),
    onSuccess: (r) => {
      toast.success(`Run #${r.pipeline_run_id} started`);
      setOpen(false);
      qc.invalidateQueries({ queryKey: ["pipeline-runs"] });
    },
    onError: (e: { message: string }) => toast.error(e.message),
  });

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm" disabled={!projectId} className="gap-2">
          <Play className="h-4 w-4" /> Run pipeline
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Run pipeline</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-2">
            <Label>Run type</Label>
            <Select value={runType} onValueChange={setRunType}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {(runTypes || ["full_pipeline"]).map((rt) => (
                  <SelectItem key={rt} value={rt}>
                    {rt}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label>Dry run</Label>
            <Select value={dryRun} onValueChange={setDryRun}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="false">No</SelectItem>
                <SelectItem value="true">Yes</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>
        <DialogFooter>
          <Button onClick={() => m.mutate()} disabled={m.isPending}>
            Run now
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
