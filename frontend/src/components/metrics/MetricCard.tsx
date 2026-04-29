import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

type Props = {
  label: string;
  value: string | number;
  delta?: number | null;
  deltaSuffix?: string;
  hint?: string;
};

function formatDelta(delta: number): string {
  const sign = delta > 0 ? "+" : "";
  return `${sign}${(delta * 100).toFixed(1)}%`;
}

export function MetricCard({ label, value, delta, deltaSuffix, hint }: Props) {
  const deltaClass =
    delta == null
      ? "text-muted-foreground"
      : delta > 0
      ? "text-emerald-400"
      : delta < 0
      ? "text-rose-400"
      : "text-muted-foreground";

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-xs uppercase tracking-wide text-muted-foreground">
          {label}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="text-3xl font-mono">{value}</div>
        {delta != null && (
          <div className={`text-xs mt-1 ${deltaClass}`}>
            {formatDelta(delta)} {deltaSuffix ?? "vs prior"}
          </div>
        )}
        {hint && (
          <div className="text-[10px] text-muted-foreground mt-1">{hint}</div>
        )}
      </CardContent>
    </Card>
  );
}
