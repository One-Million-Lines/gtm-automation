import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Brain, ChevronDown, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";
import { useProject } from "@/state/projectStore";
import { decisionTracesApi, type DecisionTrace } from "@/lib/api";

// ── Helpers ───────────────────────────────────────────────────────────────────

const TYPE_COLORS: Record<string, string> = {
  score: "bg-blue-100 text-blue-800",
  draft: "bg-purple-100 text-purple-800",
  quality: "bg-green-100 text-green-800",
  send: "bg-yellow-100 text-yellow-800",
  reply: "bg-orange-100 text-orange-800",
  tuning: "bg-pink-100 text-pink-800",
  thread: "bg-gray-100 text-gray-700",
};

const DECISION_TYPES = ["score", "draft", "quality", "send", "reply", "tuning", "thread"] as const;
type FilterType = typeof DECISION_TYPES[number] | "all";

function TypeBadge({ type }: { type: string }) {
  return (
    <span className={cn("text-xs px-2 py-0.5 rounded-full font-medium", TYPE_COLORS[type] ?? "bg-gray-100")}>
      {type}
    </span>
  );
}

// ── JSON Inspector ────────────────────────────────────────────────────────────

function JsonInspector({ data }: { data: unknown }) {
  const [open, setOpen] = useState(false);
  return (
    <div>
      <button
        className="text-xs flex items-center gap-1 text-muted-foreground hover:text-foreground"
        onClick={() => setOpen((v) => !v)}
      >
        {open ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
        {open ? "hide" : "inspect"}
      </button>
      {open && (
        <pre className="mt-2 text-xs bg-muted rounded-md p-3 max-h-64 overflow-auto whitespace-pre-wrap">
          {JSON.stringify(data, null, 2)}
        </pre>
      )}
    </div>
  );
}

// ── Row detail ────────────────────────────────────────────────────────────────

function TraceRow({ trace }: { trace: DecisionTrace }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <>
      <TableRow
        className="cursor-pointer hover:bg-muted/50"
        onClick={() => setExpanded((v) => !v)}
      >
        <TableCell className="text-xs font-mono">{trace.id}</TableCell>
        <TableCell>
          <TypeBadge type={trace.decision_type} />
        </TableCell>
        <TableCell className="text-xs">{trace.module_name}</TableCell>
        <TableCell className="text-xs">{trace.model_name ?? "—"}</TableCell>
        <TableCell className="text-xs">
          {trace.confidence != null ? (trace.confidence * 100).toFixed(0) + "%" : "—"}
        </TableCell>
        <TableCell className="text-xs">
          {trace.lead_id ?? "—"}
        </TableCell>
        <TableCell className="text-xs">
          {trace.pipeline_run_id ?? "—"}
        </TableCell>
        <TableCell className="text-xs text-muted-foreground">
          {new Date(trace.created_at).toLocaleString()}
        </TableCell>
        <TableCell>
          {expanded ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
        </TableCell>
      </TableRow>
      {expanded && (
        <TableRow>
          <TableCell colSpan={9} className="bg-muted/30 px-6 py-3">
            {trace.rationale && (
              <div className="mb-2">
                <div className="text-xs font-medium mb-1">Rationale</div>
                <div className="text-xs text-foreground whitespace-pre-wrap">{trace.rationale}</div>
              </div>
            )}
            {trace.input_snapshot && (
              <div>
                <div className="text-xs font-medium mb-1">Input Snapshot</div>
                <JsonInspector data={trace.input_snapshot} />
              </div>
            )}
            {trace.tokens_in != null && (
              <div className="text-xs text-muted-foreground mt-2">
                tokens_in={trace.tokens_in} tokens_out={trace.tokens_out}
              </div>
            )}
          </TableCell>
        </TableRow>
      )}
    </>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function DecisionTracesPage() {
  const { projectId } = useProject();
  const [typeFilter, setTypeFilter] = useState<FilterType>("all");
  const [runIdInput, setRunIdInput] = useState("");
  const [leadIdInput, setLeadIdInput] = useState("");

  const params: Record<string, unknown> = { limit: 200 };
  if (typeFilter !== "all") params.decision_type = typeFilter;
  if (runIdInput.trim()) params.run_id = parseInt(runIdInput, 10);
  if (leadIdInput.trim()) params.lead_id = parseInt(leadIdInput, 10);

  const traces = useQuery({
    queryKey: ["decision-traces", params],
    queryFn: () => decisionTracesApi.list(params as Parameters<typeof decisionTracesApi.list>[0]),
    enabled: true,
  });

  const rows = traces.data?.data ?? [];

  return (
    <div className="space-y-4 p-4">
      <div className="flex items-center gap-2">
        <Brain className="h-5 w-5 text-primary" />
        <h1 className="text-xl font-semibold">Decision Traces (Reasoning)</h1>
      </div>

      {/* Filters */}
      <Card>
        <CardContent className="pt-4 flex flex-wrap gap-3 items-end">
          <div>
            <div className="text-xs font-medium mb-1">Decision Type</div>
            <div className="flex flex-wrap gap-1">
              {(["all", ...DECISION_TYPES] as FilterType[]).map((t) => (
                <button
                  key={t}
                  onClick={() => setTypeFilter(t)}
                  className={cn(
                    "text-xs px-2 py-1 rounded-full border",
                    typeFilter === t
                      ? "bg-primary text-primary-foreground border-primary"
                      : "border-border text-muted-foreground hover:border-foreground",
                  )}
                >
                  {t}
                </button>
              ))}
            </div>
          </div>
          <div>
            <div className="text-xs font-medium mb-1">Run ID</div>
            <input
              className="h-8 rounded border px-2 text-xs w-20"
              placeholder="any"
              value={runIdInput}
              onChange={(e) => setRunIdInput(e.target.value)}
            />
          </div>
          <div>
            <div className="text-xs font-medium mb-1">Lead ID</div>
            <input
              className="h-8 rounded border px-2 text-xs w-20"
              placeholder="any"
              value={leadIdInput}
              onChange={(e) => setLeadIdInput(e.target.value)}
            />
          </div>
        </CardContent>
      </Card>

      {/* Table */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm">
            {traces.isLoading ? "Loading…" : `${rows.length} traces`}
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-16">ID</TableHead>
                <TableHead>Type</TableHead>
                <TableHead>Module</TableHead>
                <TableHead>Model</TableHead>
                <TableHead>Conf</TableHead>
                <TableHead>Lead</TableHead>
                <TableHead>Run</TableHead>
                <TableHead>At</TableHead>
                <TableHead className="w-8" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((t) => (
                <TraceRow key={t.id} trace={t} />
              ))}
              {rows.length === 0 && !traces.isLoading && (
                <TableRow>
                  <TableCell colSpan={9} className="text-center text-muted-foreground py-8 text-sm">
                    No decision traces found.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
