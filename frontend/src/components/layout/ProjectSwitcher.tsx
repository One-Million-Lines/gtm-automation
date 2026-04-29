import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronDown, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { projectsApi } from "@/lib/api";
import { useProject } from "@/state/projectStore";
import { toast } from "sonner";

export function ProjectSwitcher() {
  const { projectId, setProjectId } = useProject();
  const qc = useQueryClient();
  const { data: projects } = useQuery({
    queryKey: ["projects"],
    queryFn: projectsApi.list,
  });

  const [openDialog, setOpenDialog] = useState(false);
  const [name, setName] = useState("");
  const create = useMutation({
    mutationFn: (n: string) => projectsApi.create(n),
    onSuccess: (p) => {
      toast.success(`Project "${p.name}" created`);
      setOpenDialog(false);
      setName("");
      qc.invalidateQueries({ queryKey: ["projects"] });
      setProjectId(p.id);
    },
    onError: (e: { message: string }) => toast.error(e.message),
  });

  // Auto-select first project
  useEffect(() => {
    if (projectId == null && projects && projects.length > 0) {
      setProjectId(projects[0].id);
    }
  }, [projects, projectId, setProjectId]);

  const current = projects?.find((p) => p.id === projectId);

  return (
    <div className="flex items-center gap-2">
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="outline" size="sm" className="gap-2">
            {current ? current.name : "Select project"}
            <ChevronDown className="h-4 w-4" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" className="w-56">
          <DropdownMenuLabel>Projects</DropdownMenuLabel>
          <DropdownMenuSeparator />
          {projects?.length ? (
            projects.map((p) => (
              <DropdownMenuItem key={p.id} onClick={() => setProjectId(p.id)}>
                {p.name}
              </DropdownMenuItem>
            ))
          ) : (
            <DropdownMenuItem disabled>No projects yet</DropdownMenuItem>
          )}
          <DropdownMenuSeparator />
          <DropdownMenuItem onClick={() => setOpenDialog(true)}>
            <Plus className="h-4 w-4 mr-2" /> New project
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      <Dialog open={openDialog} onOpenChange={setOpenDialog}>
        <DialogTrigger asChild>
          <span />
        </DialogTrigger>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>New project</DialogTitle>
          </DialogHeader>
          <div className="space-y-2">
            <Label htmlFor="proj-name">Name</Label>
            <Input
              id="proj-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Acme outbound"
            />
          </div>
          <DialogFooter>
            <Button
              onClick={() => name.trim() && create.mutate(name.trim())}
              disabled={!name.trim() || create.isPending}
            >
              Create
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
