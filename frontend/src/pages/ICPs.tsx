import { useState } from "react";
import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { MoreHorizontal, Plus } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  Card, CardContent, CardHeader, CardTitle,
} from "@/components/ui/card";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { StatusBadge } from "@/components/StatusBadge";
import { ICPFormDialog } from "@/components/icps/ICPFormDialog";
import { useProject } from "@/state/projectStore";
import {
  icpsApi, type ICP, type ICPStatus,
} from "@/lib/api";

type TabKey = "all" | "active" | "draft" | "archived";

export default function ICPsPage() {
  const { projectId } = useProject();
  const qc = useQueryClient();
  const [tab, setTab] = useState<TabKey>("all");
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<ICP | null>(null);

  const status: ICPStatus | undefined = tab === "all" ? undefined : tab;

  const list = useQuery({
    queryKey: ["icps", projectId, status ?? "all"],
    queryFn: () => icpsApi.list(projectId!, status),
    enabled: projectId != null,
  });

  const summaries = useQueries({
    queries: (list.data ?? []).map((i) => ({
      queryKey: ["icp-summary", i.id],
      queryFn: () => icpsApi.summary(i.id),
      staleTime: 30_000,
    })),
  });

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["icps", projectId] });
  };

  const activate = useMutation({
    mutationFn: (id: number) => icpsApi.activate(id),
    onSuccess: () => { invalidate(); toast.success("Activated"); },
    onError: (e: { message?: string }) => toast.error(e?.message ?? "Failed"),
  });
  const archive = useMutation({
    mutationFn: (id: number) => icpsApi.archive(id),
    onSuccess: () => { invalidate(); toast.success("Archived"); },
    onError: (e: { message?: string }) => toast.error(e?.message ?? "Failed"),
  });
  const clone = useMutation({
    mutationFn: (id: number) => icpsApi.clone(id),
    onSuccess: () => { invalidate(); toast.success("Cloned as draft"); },
    onError: (e: { message?: string }) => toast.error(e?.message ?? "Failed"),
  });

  if (projectId == null) {
    return (
      <Card>
        <CardHeader><CardTitle>ICPs</CardTitle></CardHeader>
        <CardContent className="text-muted-foreground text-sm">
          Select or create a project from the top bar to manage ICPs.
        </CardContent>
      </Card>
    );
  }

  const items = list.data ?? [];

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">ICPs</h1>
          <p className="text-muted-foreground text-sm">
            Ideal Customer Profiles drive discovery, scoring, and outreach.
          </p>
        </div>
        <Button onClick={() => { setEditing(null); setOpen(true); }}>
          <Plus className="mr-1 h-4 w-4" /> New ICP
        </Button>
      </div>

      <Tabs value={tab} onValueChange={(v) => setTab(v as TabKey)}>
        <TabsList>
          <TabsTrigger value="all">All</TabsTrigger>
          <TabsTrigger value="active">Active</TabsTrigger>
          <TabsTrigger value="draft">Draft</TabsTrigger>
          <TabsTrigger value="archived">Archived</TabsTrigger>
        </TabsList>
      </Tabs>

      {list.isLoading ? (
        <p className="text-muted-foreground text-sm">Loading…</p>
      ) : items.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center gap-3 py-12 text-center">
            <p className="text-muted-foreground text-sm">
              No ICPs yet for this project.
            </p>
            <Button onClick={() => { setEditing(null); setOpen(true); }}>
              <Plus className="mr-1 h-4 w-4" /> Create your first ICP
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {items.map((icp, idx) => {
            const summary = summaries[idx]?.data;
            return (
              <Card key={icp.id}>
                <CardHeader className="flex flex-row items-start justify-between gap-2 pb-2">
                  <div className="space-y-1">
                    <CardTitle className="text-base">{icp.name}</CardTitle>
                    <StatusBadge status={icp.status} />
                  </div>
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button variant="ghost" size="icon">
                        <MoreHorizontal className="h-4 w-4" />
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end">
                      <DropdownMenuItem onClick={() => { setEditing(icp); setOpen(true); }}>
                        Edit
                      </DropdownMenuItem>
                      {icp.status !== "active" && (
                        <DropdownMenuItem onClick={() => activate.mutate(icp.id)}>
                          Activate
                        </DropdownMenuItem>
                      )}
                      {icp.status !== "archived" && (
                        <DropdownMenuItem onClick={() => archive.mutate(icp.id)}>
                          Archive
                        </DropdownMenuItem>
                      )}
                      <DropdownMenuItem onClick={() => clone.mutate(icp.id)}>
                        Clone
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                </CardHeader>
                <CardContent className="space-y-3 text-sm">
                  {icp.description && (
                    <p className="text-muted-foreground line-clamp-2">{icp.description}</p>
                  )}
                  <Facet label="Industries" items={icp.target_industries} />
                  <Facet label="Roles" items={icp.target_roles} />
                  <Facet label="Geos" items={icp.target_geographies} />

                  <div className="grid grid-cols-4 gap-2 pt-2">
                    <Stat label="Companies" value={summary?.companies_targeted} />
                    <Stat label="Contacts" value={summary?.contacts_targeted} />
                    <Stat label="Leads ready" value={summary?.leads_ready} />
                    <Stat label="Drafts pending" value={summary?.drafts_pending} />
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}

      <ICPFormDialog
        open={open}
        onOpenChange={setOpen}
        projectId={projectId}
        initial={editing}
      />
    </div>
  );
}

function Facet({ label, items }: { label: string; items: string[] | null }) {
  const top = (items ?? []).slice(0, 3);
  const more = (items?.length ?? 0) - top.length;
  if (!top.length) return null;
  return (
    <div className="text-xs">
      <span className="text-muted-foreground mr-1">{label}:</span>
      <span>{top.join(", ")}{more > 0 ? ` +${more}` : ""}</span>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number | undefined }) {
  return (
    <div className="bg-muted/40 rounded-md px-2 py-1.5">
      <div className="text-muted-foreground text-[10px] uppercase">{label}</div>
      <div className="text-base font-semibold tabular-nums">
        {value ?? "—"}
      </div>
    </div>
  );
}
