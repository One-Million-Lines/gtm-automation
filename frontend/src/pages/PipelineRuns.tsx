import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { pipelineApi } from "@/lib/api";
import { useProject } from "@/state/projectStore";
import { StatusBadge } from "@/components/StatusBadge";

export default function PipelineRuns() {
  const { projectId } = useProject();
  const [openRunId, setOpenRunId] = useState<number | null>(null);

  const runs = useQuery({
    queryKey: ["pipeline-runs", projectId],
    queryFn: () => pipelineApi.listRuns(projectId!, 50),
    enabled: projectId != null,
  });

  const detail = useQuery({
    queryKey: ["pipeline-run", openRunId],
    queryFn: () => pipelineApi.getRun(openRunId!),
    enabled: openRunId != null,
  });

  if (projectId == null) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>No project selected</CardTitle>
        </CardHeader>
      </Card>
    );
  }

  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle>Pipeline runs</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>#</TableHead>
                <TableHead>Type</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Started</TableHead>
                <TableHead className="text-right">Processed</TableHead>
                <TableHead className="text-right">Created</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {runs.data?.map((r) => (
                <TableRow
                  key={r.id}
                  className="cursor-pointer"
                  onClick={() => setOpenRunId(r.id)}
                >
                  <TableCell className="font-mono">{r.id}</TableCell>
                  <TableCell>{r.run_type}</TableCell>
                  <TableCell>
                    <StatusBadge status={r.status} />
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {r.started_at}
                  </TableCell>
                  <TableCell className="text-right">{r.total_processed}</TableCell>
                  <TableCell className="text-right">{r.total_created}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          {!runs.data?.length && (
            <p className="text-sm text-muted-foreground py-6 text-center">
              No runs yet.
            </p>
          )}
        </CardContent>
      </Card>

      <Sheet open={openRunId != null} onOpenChange={(o) => !o && setOpenRunId(null)}>
        <SheetContent className="w-[640px] sm:max-w-[640px] overflow-y-auto">
          <SheetHeader>
            <SheetTitle>
              Run #{openRunId} {detail.data && <StatusBadge status={detail.data.run.status} />}
            </SheetTitle>
          </SheetHeader>

          {detail.data && (
            <div className="mt-4 space-y-6">
              <section>
                <h3 className="text-sm font-semibold mb-2">Steps</h3>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Module</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead className="text-right">In</TableHead>
                      <TableHead className="text-right">Out</TableHead>
                      <TableHead className="text-right">Failed</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {detail.data.steps.map((s) => (
                      <TableRow key={s.id}>
                        <TableCell>{s.module_name}</TableCell>
                        <TableCell>
                          <StatusBadge status={s.status} />
                        </TableCell>
                        <TableCell className="text-right">{s.input_count}</TableCell>
                        <TableCell className="text-right">{s.output_count}</TableCell>
                        <TableCell className="text-right">{s.failed_count}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </section>

              <section>
                <h3 className="text-sm font-semibold mb-2">Logs</h3>
                <div className="space-y-1 font-mono text-xs">
                  {detail.data.logs.map((l) => (
                    <div
                      key={l.id}
                      className="border border-border rounded-md p-2 bg-card/40"
                    >
                      <div className="flex justify-between text-muted-foreground">
                        <span>
                          [{l.level}] {l.module_name}
                        </span>
                        <span>{l.created_at}</span>
                      </div>
                      <div>{l.message}</div>
                      {Object.keys(l.context || {}).length > 0 && (
                        <pre className="mt-1 text-[10px] text-muted-foreground whitespace-pre-wrap">
                          {JSON.stringify(l.context, null, 2)}
                        </pre>
                      )}
                    </div>
                  ))}
                </div>
              </section>
            </div>
          )}
        </SheetContent>
      </Sheet>
    </>
  );
}
