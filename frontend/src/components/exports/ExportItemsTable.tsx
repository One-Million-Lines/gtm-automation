import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import type { LeadExportItem } from "@/lib/api";

type Props = {
  items: LeadExportItem[];
};

function pickStr(payload: Record<string, unknown>, ...path: string[]): string {
  let cur: unknown = payload;
  for (const k of path) {
    if (cur && typeof cur === "object" && k in (cur as Record<string, unknown>)) {
      cur = (cur as Record<string, unknown>)[k];
    } else {
      return "—";
    }
  }
  if (cur === null || cur === undefined || cur === "") return "—";
  return String(cur);
}

export function ExportItemsTable({ items }: Props) {
  if (items.length === 0) {
    return <p className="text-sm text-zinc-400">No items.</p>;
  }
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Lead</TableHead>
          <TableHead>Tier</TableHead>
          <TableHead>Company</TableHead>
          <TableHead>Contact</TableHead>
          <TableHead>Email</TableHead>
          <TableHead>Subject</TableHead>
          <TableHead>Variant</TableHead>
          <TableHead>Winner</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {items.map((it) => {
          const p = (it.payload || {}) as Record<string, unknown>;
          const isWin = Boolean((p as { is_winning_variant?: boolean }).is_winning_variant);
          return (
            <TableRow key={it.id}>
              <TableCell className="font-mono text-xs">#{it.lead_id}</TableCell>
              <TableCell className="font-mono">{pickStr(p, "lead", "priority_tier")}</TableCell>
              <TableCell>{pickStr(p, "company", "name")}</TableCell>
              <TableCell>{pickStr(p, "contact", "full_name")}</TableCell>
              <TableCell className="font-mono text-xs">{pickStr(p, "contact", "email")}</TableCell>
              <TableCell className="max-w-80 truncate">{pickStr(p, "outreach_message", "subject")}</TableCell>
              <TableCell className="font-mono text-xs">{pickStr(p, "outreach_message", "variant_name")}</TableCell>
              <TableCell>
                {isWin ? (
                  <span className="rounded border border-emerald-600 bg-emerald-500/15 px-2 py-0.5 font-mono text-[10px] uppercase text-emerald-300">
                    yes
                  </span>
                ) : (
                  <span className="text-zinc-500 text-xs">—</span>
                )}
              </TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}
