import type { DailySeriesPoint } from "@/lib/api";

type Props = {
  series: DailySeriesPoint[];
  height?: number;
  width?: number;
};

const SERIES_COLORS = {
  sent: "#60a5fa",     // blue-400
  opened: "#34d399",   // emerald-400
  replied: "#a78bfa",  // violet-400
  bounced: "#fb7185",  // rose-400
} as const;

type SeriesKey = keyof typeof SERIES_COLORS;

export function SparklineChart({ series, height = 120, width = 600 }: Props) {
  if (series.length === 0) {
    return (
      <div
        className="flex items-center justify-center text-xs text-muted-foreground border border-border/30 rounded"
        style={{ height }}
      >
        no data
      </div>
    );
  }

  const keys: SeriesKey[] = ["sent", "opened", "replied", "bounced"];
  const maxValue = Math.max(
    1,
    ...series.flatMap((p) => keys.map((k) => p[k] ?? 0)),
  );
  const xStep = series.length > 1 ? width / (series.length - 1) : width;

  const polyline = (k: SeriesKey) =>
    series
      .map((p, i) => {
        const x = i * xStep;
        const y = height - ((p[k] ?? 0) / maxValue) * (height - 4) - 2;
        return `${x.toFixed(1)},${y.toFixed(1)}`;
      })
      .join(" ");

  return (
    <div className="space-y-2">
      <div className="flex gap-3 text-xs">
        {keys.map((k) => (
          <div key={k} className="flex items-center gap-1">
            <span
              className="inline-block w-2 h-2 rounded-full"
              style={{ backgroundColor: SERIES_COLORS[k] }}
            />
            <span className="text-muted-foreground capitalize">{k}</span>
          </div>
        ))}
      </div>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="w-full"
        preserveAspectRatio="none"
        style={{ height }}
      >
        {keys.map((k) => (
          <polyline
            key={k}
            fill="none"
            stroke={SERIES_COLORS[k]}
            strokeWidth={1.5}
            points={polyline(k)}
          />
        ))}
      </svg>
      <div className="flex justify-between text-[10px] text-muted-foreground">
        <span>{series[0]?.date}</span>
        <span>{series[series.length - 1]?.date}</span>
      </div>
    </div>
  );
}
