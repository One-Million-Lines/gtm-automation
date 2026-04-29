import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import type { WeightDiffRow } from "@/lib/api";
import { cn } from "@/lib/utils";

function fmt(n: number): string {
  return Number.isFinite(n) ? n.toFixed(4) : "—";
}

export function WeightDiff({ rows }: { rows: WeightDiffRow[] }) {
  if (!rows.length) {
    return <p className="text-sm text-zinc-500">no weight changes</p>;
  }
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>namespace</TableHead>
          <TableHead>feature</TableHead>
          <TableHead className="text-right">baseline</TableHead>
          <TableHead className="text-right">proposed</TableHead>
          <TableHead className="text-right">delta</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((r) => {
          const dir = r.delta > 0 ? "up" : r.delta < 0 ? "down" : "flat";
          return (
            <TableRow key={`${r.namespace}.${r.key}`}>
              <TableCell className="font-mono text-xs text-zinc-400">{r.namespace}</TableCell>
              <TableCell className="font-mono text-xs">{r.key}</TableCell>
              <TableCell className="text-right font-mono text-xs">{fmt(r.baseline)}</TableCell>
              <TableCell className="text-right font-mono text-xs">{fmt(r.proposed)}</TableCell>
              <TableCell
                className={cn(
                  "text-right font-mono text-xs",
                  dir === "up" && "text-emerald-400",
                  dir === "down" && "text-rose-400",
                  dir === "flat" && "text-zinc-500",
                )}
              >
                {r.delta > 0 ? "+" : ""}{fmt(r.delta)}
              </TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}
