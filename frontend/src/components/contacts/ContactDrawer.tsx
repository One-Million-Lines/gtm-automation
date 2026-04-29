import { useQuery } from "@tanstack/react-query";
import {
  Sheet, SheetContent, SheetHeader, SheetTitle,
} from "@/components/ui/sheet";
import { Badge } from "@/components/ui/badge";
import { StatusBadge } from "@/components/StatusBadge";
import { ContactEnrichmentSection, StatusPill } from "@/components/contacts/ContactEnrichmentSection";
import { LeadScoringPanel } from "@/components/leads/LeadScoringPanel";
import { OutreachPanel } from "@/components/outreach/OutreachPanel";
import { SignalsTimeline } from "@/components/signals/SignalsTimeline";
import { contactsApi } from "@/lib/api";

type Props = {
  contactId: number | null;
  onOpenChange: (v: boolean) => void;
};

export function ContactDrawer({ contactId, onOpenChange }: Props) {
  const open = contactId != null;
  const q = useQuery({
    queryKey: ["contact", contactId],
    queryFn: () => contactsApi.get(contactId as number),
    enabled: open,
  });

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="w-full overflow-y-auto sm:max-w-xl">
        <SheetHeader>
          <SheetTitle>
            {q.data?.contact.full_name ||
              [q.data?.contact.first_name, q.data?.contact.last_name].filter(Boolean).join(" ") ||
              q.data?.contact.email ||
              "Contact"}
          </SheetTitle>
        </SheetHeader>

        {q.isLoading ? (
          <p className="text-muted-foreground p-4 text-sm">Loading…</p>
        ) : !q.data ? null : (
          <div className="space-y-4 p-4 text-sm">
            <div className="flex flex-wrap items-center gap-2">
              <StatusBadge status={q.data.contact.status} />
              {q.data.contact.normalized_role && (
                <Badge variant="secondary">{q.data.contact.normalized_role}</Badge>
              )}
              {q.data.contact.email_status && (
                <StatusPill status={q.data.contact.email_status} />
              )}
              {q.data.contact.email && (
                <a href={`mailto:${q.data.contact.email}`} className="text-blue-400 underline">
                  {q.data.contact.email}
                </a>
              )}
              {q.data.contact.linkedin_url && (
                <a href={q.data.contact.linkedin_url} target="_blank" rel="noreferrer"
                   className="text-blue-400 underline">LinkedIn</a>
              )}
            </div>

            <DetailGrid c={q.data.contact} />

            <ContactEnrichmentSection contactId={q.data.contact.id} />

            <SignalsTimeline scope={{ kind: "contact", id: q.data.contact.id }} />

            <LeadScoringPanel leadId={q.data.leads?.[0]?.id ?? null} />

            <OutreachPanel leadId={q.data.leads?.[0]?.id ?? null} />

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

            <div>
              <div className="mb-2 font-semibold">Leads ({q.data.leads.length})</div>
              <div className="space-y-1">
                {q.data.leads.map((l) => (
                  <div key={l.id}
                       className="bg-muted/40 flex items-center justify-between rounded-md p-2 text-xs">
                    <div>
                      <span className="font-medium">#{l.id}</span>
                      <span className="text-muted-foreground ml-2">ICP {l.icp_id} · Company {l.company_id}</span>
                    </div>
                    <StatusBadge status={l.lead_status} />
                  </div>
                ))}
                {q.data.leads.length === 0 && (
                  <p className="text-muted-foreground text-xs">Not linked to any lead yet.</p>
                )}
              </div>
            </div>
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
}

function DetailGrid({ c }: { c: import("@/lib/api").Contact }) {
  const rows: [string, unknown][] = [
    ["First name", c.first_name],
    ["Last name", c.last_name],
    ["Job title", c.job_title],
    ["Email status", c.email_status],
    ["Country", c.country],
    ["City", c.city],
    ["Company ID", c.company_id],
    ["Email confidence", c.email_confidence],
  ];
  return (
    <div className="grid grid-cols-2 gap-2 text-xs">
      {rows.map(([k, v]) => (
        <div key={k} className="bg-muted/30 rounded px-2 py-1">
          <div className="text-muted-foreground text-[10px] uppercase">{k}</div>
          <div className="truncate">{v == null || v === "" ? "—" : String(v)}</div>
        </div>
      ))}
    </div>
  );
}
