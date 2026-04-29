import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Workflow, Copy, Archive, Plus, Play } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { useProject } from "@/state/projectStore";
import { templatesApi, type PipelineTemplate, type TemplateStep } from "@/lib/api";

function statusBadge(s: string) {
  const cls =
    s === "active"
      ? "bg-emerald-500/15 text-emerald-400"
      : s === "archived"
        ? "bg-zinc-500/15 text-zinc-400"
        : "bg-amber-500/15 text-amber-400";
  return <span className={`rounded px-2 py-0.5 text-xs ${cls}`}>{s}</span>;
}

export default function Templates() {
  const qc = useQueryClient();
  const { projectId } = useProject();
  const [draftName, setDraftName] = useState("");
  const [draftSlug, setDraftSlug] = useState("");
  const [draftSteps, setDraftSteps] = useState<string>(
    JSON.stringify(
      [
        { run_type: "company_discovery", config: {}, on_failure: "continue" },
        { run_type: "lead_scoring", config: {}, on_failure: "continue" },
      ],
      null,
      2,
    ),
  );

  const listQ = useQuery({
    queryKey: ["templates", projectId],
    queryFn: () =>
      templatesApi.list({
        project_id: projectId ?? undefined,
        include_global: true,
      }),
    enabled: projectId != null,
  });

  const invalidate = () => qc.invalidateQueries({ queryKey: ["templates", projectId] });

  const createMut = useMutation({
    mutationFn: () => {
      let steps: TemplateStep[];
      try {
        steps = JSON.parse(draftSteps);
      } catch (e) {
        throw new Error("steps must be valid JSON");
      }
      return templatesApi.create({
        project_id: projectId,
        name: draftName,
        slug: draftSlug,
        steps,
      });
    },
    onSuccess: (t) => {
      toast.success(`Created template #${t.id}`);
      setDraftName("");
      setDraftSlug("");
      invalidate();
    },
    onError: (e: unknown) => toast.error((e as Error).message ?? "create failed"),
  });

  const cloneMut = useMutation({
    mutationFn: (id: number) =>
      templatesApi.clone(id, { project_id: projectId ?? undefined }),
    onSuccess: () => {
      toast.success("Cloned");
      invalidate();
    },
  });

  const archiveMut = useMutation({
    mutationFn: (id: number) => templatesApi.archive(id),
    onSuccess: () => {
      toast.success("Archived");
      invalidate();
    },
  });

  const runMut = useMutation({
    mutationFn: (id: number) =>
      templatesApi.run({ template_id: id, project_id: projectId! }),
    onSuccess: (r) => toast.success(`Started run #${r.parent_run_id}`),
    onError: (e: unknown) => toast.error((e as Error).message ?? "run failed"),
  });

  const rows = listQ.data ?? [];

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2">
        <Workflow className="h-5 w-5" />
        <h1 className="text-2xl font-semibold">Pipeline Templates</h1>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>New template</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <Input
              placeholder="Name"
              value={draftName}
              onChange={(e) => setDraftName(e.target.value)}
            />
            <Input
              placeholder="slug_v1"
              value={draftSlug}
              onChange={(e) => setDraftSlug(e.target.value)}
            />
          </div>
          <Textarea
            rows={10}
            value={draftSteps}
            onChange={(e) => setDraftSteps(e.target.value)}
            className="font-mono text-xs"
          />
          <Button
            onClick={() => createMut.mutate()}
            disabled={!draftName || !draftSlug || createMut.isPending}
          >
            <Plus className="mr-1 h-4 w-4" />
            Create
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Templates ({rows.length})</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>ID</TableHead>
                <TableHead>Name</TableHead>
                <TableHead>Slug</TableHead>
                <TableHead>v</TableHead>
                <TableHead>Scope</TableHead>
                <TableHead>Steps</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((t: PipelineTemplate) => (
                <TableRow key={t.id}>
                  <TableCell>{t.id}</TableCell>
                  <TableCell className="font-medium">{t.name}</TableCell>
                  <TableCell className="font-mono text-xs">{t.slug}</TableCell>
                  <TableCell>{t.version}</TableCell>
                  <TableCell>{t.project_id ?? "global"}</TableCell>
                  <TableCell>{t.steps.length}</TableCell>
                  <TableCell>{statusBadge(t.status)}</TableCell>
                  <TableCell className="text-right space-x-1">
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => runMut.mutate(t.id)}
                      disabled={t.status !== "active"}
                    >
                      <Play className="h-3 w-3" />
                    </Button>
                    <Button size="sm" variant="outline" onClick={() => cloneMut.mutate(t.id)}>
                      <Copy className="h-3 w-3" />
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => archiveMut.mutate(t.id)}
                      disabled={t.status === "archived"}
                    >
                      <Archive className="h-3 w-3" />
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
