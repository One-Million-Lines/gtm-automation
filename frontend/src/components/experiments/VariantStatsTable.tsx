import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { VariantStat } from "@/lib/api";
import { VariantBadge } from "./VariantBadge";
import { cn } from "@/lib/utils";

function pct(n: number | null | undefined): string {
  if (n === null || n === undefined) return "—";
  return `${(n * 100).toFixed(1)}%`;
}

function liftStr(n: number | null): string {
  if (n === null || n === undefined) return "—";
  const s = (n * 100).toFixed(1);
  return n > 0 ? `+${s}%` : `${s}%`;
}

export function VariantStatsTable({
  stats,
  winnerVariantId,
  leaderVariantId,
}: {
  stats: VariantStat[];
  winnerVariantId?: number | null;
  leaderVariantId?: number | null;
}) {
  if (!stats.length) {
    return (
      <div className="rounded-md border border-border/40 p-6 text-center text-sm text-muted-foreground">
        No variant data yet.
      </div>
    );
  }
  return (
    <div className="rounded-md border border-border/40 overflow-hidden">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Variant</TableHead>
            <TableHead className="text-right">Sent</TableHead>
            <TableHead className="text-right">Reply rate</TableHead>
            <TableHead className="text-right">Positive rate</TableHead>
            <TableHead className="text-right">Lift vs control</TableHead>
            <TableHead className="text-right">Wilson lower</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {stats.map((s) => {
            const isWinner = winnerVariantId === s.variant_id;
            const isLeader = !isWinner && leaderVariantId === s.variant_id;
            return (
              <TableRow
                key={s.variant_id}
                className={cn(
                  isWinner && "bg-emerald-500/15",
                  isLeader && "bg-sky-500/10",
                )}
              >
                <TableCell>
                  <div className="flex items-center gap-2">
                    <VariantBadge name={s.name} isControl={s.is_control} />
                    {isWinner && (
                      <span className="text-[10px] uppercase font-mono text-emerald-300">
                        winner
                      </span>
                    )}
                    {isLeader && (
                      <span className="text-[10px] uppercase font-mono text-sky-300">
                        leader
                      </span>
                    )}
                  </div>
                </TableCell>
                <TableCell className="text-right font-mono text-sm">{s.sent}</TableCell>
                <TableCell className="text-right font-mono text-sm">
                  {pct(s.reply_rate)}
                </TableCell>
                <TableCell className="text-right font-mono text-sm">
                  {pct(s.positive_reply_rate)}
                </TableCell>
                <TableCell
                  className={cn(
                    "text-right font-mono text-sm",
                    s.lift_vs_control != null && s.lift_vs_control > 0 && "text-emerald-300",
                    s.lift_vs_control != null && s.lift_vs_control < 0 && "text-rose-300",
                  )}
                >
                  {liftStr(s.lift_vs_control)}
                </TableCell>
                <TableCell className="text-right font-mono text-sm">
                  {pct(s.wilson_lower)}
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}
