import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { CalendarClock, Trash2, Zap, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { useProject } from "@/state/projectStore";
import {
  schedulesApi, schedulerApi, templatesApi, type PipelineSchedule,
} from "@/lib/api";

function fmtDate(s: string | null) {
  if (!s) return "—";
  return s.replace("T", " ").slice(0, 19);
}

export default function Schedules() {
  const qc = useQueryClient();
  const { projectId } = useProject();
  const [name, setName] = useState("");
  const [cron, setCron] = useState("*/30 * * * *");
  const [tplId, setTplId] = useState<string>("");

  const tplsQ = useQuery({
    queryKey: ["templates", projectId, "for-schedules"],
    queryFn: () =>
      templatesApi.list({
        project_id: projectId ?? undefined,
        include_global: true,
        status: "active",
      }),
    enabled: projectId != null,
  });

  const listQ = useQuery({
    queryKey: ["schedules", projectId],
    queryFn: () => schedulesApi.list(projectId!),
    enabled: projectId != null,
  });

  const invalidate = () =>
    qc.invalidateQueries({ queryKey: ["schedules", projectId] });

  const createMut = useMutation({
    mutationFn: () =>
      schedulesApi.create({
        project_id: projectId!,
        template_id: Number(tplId),
        name,
        cron_expr: cron,
      }),
    onSuccess: () => {
      toast.success("Schedule created");
      setName("");
      invalidate();
    },
    onError: (e: unknown) => toast.error((e as Error).message ?? "create failed"),
  });

  const toggleMut = useMutation({
    mutationFn: ({ id, enabled }: { id: number; enabled: boolean }) =>
      schedulesApi.update(id, { enabled }),
    onSuccess: invalidate,
  });

  const deleteMut = useMutation({
    mutationFn: (id: number) => schedulesApi.remove(id),
    onSuccess: () => {
      toast.success("Deleted");
      invalidate();
    },
  });

  const fireMut = useMutation({
    mutationFn: (id: number) => schedulesApi.fireNow(id),
    onSuccess: (r) => {
      toast.success(`Fired run #${r.run_id}`);
      invalidate();
    },
    onError: (e: unknown) => toast.error((e as Error).message ?? "fire failed"),
  });

  const tickMut = useMutation({
    mutationFn: () => schedulerApi.tick(50),
    onSuccess: (r) => {
      toast.success(`Tick: fired=${r.fired_count} skipped=${r.skipped_count}`);
      invalidate();
    },
  });

  const rows = listQ.data ?? [];

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2">
        <CalendarClock className="h-5 w-5" />
        <h1 className="text-2xl font-semibold">Schedules</h1>
        <div className="ml-auto">
          <Button variant="outline" onClick={() => tickMut.mutate()}>
            <Zap className="mr-1 h-4 w-4" />
            Run scheduler tick
          </Button>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>New schedule</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid grid-cols-3 gap-3">
            <Input
              placeholder="Name"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
            <select
              value={tplId}
              onChange={(e) => setTplId(e.target.value)}
              className="h-9 rounded-md border bg-background px-2 text-sm"
            >
              <option value="">Pick template…</option>
              {(tplsQ.data ?? []).map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name} ({t.slug} v{t.version})
                </option>
              ))}
            </select>
            <Input
              placeholder="*/30 * * * *"
              value={cron}
              onChange={(e) => setCron(e.target.value)}
              className="font-mono"
            />
          </div>
          <Button
            onClick={() => createMut.mutate()}
            disabled={!name || !tplId || !cron || createMut.isPending}
          >
            <Plus className="mr-1 h-4 w-4" />
            Create
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Schedules ({rows.length})</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>ID</TableHead>
                <TableHead>Name</TableHead>
                <TableHead>Template</TableHead>
                <TableHead>Cron</TableHead>
                <TableHead>Next fire</TableHead>
                <TableHead>Last fire</TableHead>
                <TableHead>Last run</TableHead>
                <TableHead>Enabled</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((s: PipelineSchedule) => (
                <TableRow key={s.id}>
                  <TableCell>{s.id}</TableCell>
                  <TableCell className="font-medium">{s.name}</TableCell>
                  <TableCell>#{s.template_id}</TableCell>
                  <TableCell className="font-mono text-xs">{s.cron_expr}</TableCell>
                  <TableCell>{fmtDate(s.next_fire_at)}</TableCell>
                  <TableCell>{fmtDate(s.last_fired_at)}</TableCell>
                  <TableCell>{s.last_run_id ?? "—"}</TableCell>
                  <TableCell>
                    <Switch
                      checked={!!s.enabled}
                      onCheckedChange={(v) =>
                        toggleMut.mutate({ id: s.id, enabled: v })
                      }
                    />
                  </TableCell>
                  <TableCell className="text-right space-x-1">
                    <Button size="sm" variant="outline" onClick={() => fireMut.mutate(s.id)}>
                      <Zap className="h-3 w-3" />
                    </Button>
                    <Button size="sm" variant="outline" onClick={() => deleteMut.mutate(s.id)}>
                      <Trash2 className="h-3 w-3" />
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
