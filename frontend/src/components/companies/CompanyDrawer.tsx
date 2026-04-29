import { useQuery } from "@tanstack/react-query";
import {
  Sheet, SheetContent, SheetHeader, SheetTitle,
} from "@/components/ui/sheet";
import { StatusBadge } from "@/components/StatusBadge";
import { EnrichmentSection } from "@/components/companies/EnrichmentSection";
import { SignalsTimeline } from "@/components/signals/SignalsTimeline";
import { companiesApi } from "@/lib/api";

type Props = {
  companyId: number | null;
  onOpenChange: (v: boolean) => void;
};

export function CompanyDrawer({ companyId, onOpenChange }: Props) {
  const open = companyId != null;
  const q = useQuery({
    queryKey: ["company", companyId],
    queryFn: () => companiesApi.get(companyId as number),
    enabled: open,
  });

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="w-full overflow-y-auto sm:max-w-xl">
        <SheetHeader>
          <SheetTitle>{q.data?.company.name ?? q.data?.company.domain ?? "Company"}</SheetTitle>
        </SheetHeader>

        {q.isLoading ? (
          <p className="text-muted-foreground p-4 text-sm">Loading…</p>
        ) : !q.data ? null : (
          <div className="space-y-4 p-4 text-sm">
            <div className="flex items-center gap-2">
              <StatusBadge status={q.data.company.status} />
              <a
                href={q.data.company.website_url ?? `https://${q.data.company.domain}`}
                target="_blank" rel="noreferrer"
                className="text-blue-400 underline"
              >
                {q.data.company.domain}
              </a>
            </div>

            <DetailGrid c={q.data.company} />

            <EnrichmentSection companyId={q.data.company.id} />

            <SignalsTimeline scope={{ kind: "company", id: q.data.company.id }} />

            <div>
              <div className="mb-2 font-semibold">Sources ({q.data.sources.length})</div>
              <div className="space-y-2">
                {q.data.sources.map((s) => (
                  <div key={s.id} className="bg-muted/40 rounded-md p-2">
                    <div className="text-xs">
                      <span className="font-medium">{s.source_name ?? s.source_type}</span>
                      <span className="text-muted-foreground ml-2">
                        {new Date(s.discovered_at).toLocaleString()}
                      </span>
                    </div>
                    {s.source_url && (
                      <a href={s.source_url} target="_blank" rel="noreferrer"
                         className="text-xs text-blue-400 underline">{s.source_url}</a>
                    )}
                    <pre className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap break-all text-[10px]">
                      {JSON.stringify(s.raw_data, null, 2)}
                    </pre>
                  </div>
                ))}
                {q.data.sources.length === 0 && (
                  <p className="text-muted-foreground text-xs">No source rows yet.</p>
                )}
              </div>
            </div>
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
}

function DetailGrid({ c }: { c: import("@/lib/api").Company }) {
  const rows: [string, unknown][] = [
    ["Name", c.name],
    ["Industry", c.industry],
    ["Country", c.country],
    ["City", c.city],
    ["Employees", c.employee_count],
    ["Revenue", c.revenue_estimate],
    ["Platform", c.ecommerce_platform],
    ["LinkedIn", c.linkedin_url],
  ];
  return (
    <div className="grid grid-cols-2 gap-2 text-xs">
      {rows.map(([k, v]) => (
        <div key={k} className="bg-muted/30 rounded px-2 py-1">
          <div className="text-muted-foreground text-[10px] uppercase">{k}</div>
          <div className="truncate">{v == null || v === "" ? "—" : String(v)}</div>
        </div>
      ))}
      {c.tech_stack && c.tech_stack.length > 0 && (
        <div className="bg-muted/30 col-span-2 rounded px-2 py-1">
          <div className="text-muted-foreground text-[10px] uppercase">Tech stack</div>
          <div>{c.tech_stack.join(", ")}</div>
        </div>
      )}
      {c.description && (
        <div className="bg-muted/30 col-span-2 rounded px-2 py-1">
          <div className="text-muted-foreground text-[10px] uppercase">Description</div>
          <div className="text-xs">{c.description}</div>
        </div>
      )}
    </div>
  );
}
