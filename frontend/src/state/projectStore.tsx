import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

const KEY = "gtm.selectedProjectId";

type Ctx = {
  projectId: number | null;
  setProjectId: (id: number | null) => void;
};

const ProjectCtx = createContext<Ctx | null>(null);

export function ProjectProvider({ children }: { children: ReactNode }) {
  const [projectId, setProjectIdState] = useState<number | null>(() => {
    const v = localStorage.getItem(KEY);
    return v ? Number(v) : null;
  });

  useEffect(() => {
    if (projectId == null) localStorage.removeItem(KEY);
    else localStorage.setItem(KEY, String(projectId));
  }, [projectId]);

  const value = useMemo<Ctx>(
    () => ({ projectId, setProjectId: setProjectIdState }),
    [projectId]
  );
  return <ProjectCtx.Provider value={value}>{children}</ProjectCtx.Provider>;
}

export function useProject() {
  const ctx = useContext(ProjectCtx);
  if (!ctx) throw new Error("useProject must be used within ProjectProvider");
  return ctx;
}
