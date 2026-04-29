import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  Briefcase, Newspaper, DollarSign, Layers, TrendingUp,
  Share2, UserCog, Globe, Sparkles, Activity,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  signalsApi, SIGNAL_TYPES, type SignalRow, type SignalType,
} from "@/lib/api";

type Scope = { kind: "company"; id: number } | { kind: "contact"; id: number };

const ICONS: Record<string, typeof Briefcase> = {
  hiring_intent: Briefcase,
  news_mention: Newspaper,
  funding: DollarSign,
  tech_stack_change: Layers,
  hiring_pace: TrendingUp,
  social_activity: Share2,
  role_change: UserCog,
  linkedin_activity: Globe,
};

const TYPE_COLOR: Record<string, string> = {
  hiring_intent: "bg-emerald-500/15 text-emerald-300 border-emerald-700",
  news_mention: "bg-sky-500/15 text-sky-300 border-sky-700",
  funding: "bg-amber-500/15 text-amber-300 border-amber-700",
  tech_stack_change: "bg-fuchsia-500/15 text-fuchsia-300 border-fuchsia-700",
  hiring_pace: "bg-emerald-500/15 text-emerald-300 border-emerald-700",
  social_activity: "bg-indigo-500/15 text-indigo-300 border-indigo-700",
  role_change: "bg-rose-500/15 text-rose-300 border-rose-700",
  linkedin_activity: "bg-zinc-500/15 text-zinc-300 border-zinc-700",
};

function StrengthBar({ value }: { value: number | null | undefined }) {
  const v = Math.max(0, Math.min(1, value ?? 0));
  const pct = Math.round(v * 100);
  return (
    <div className="bg-muted h-1.5 w-20 overflow-hidden rounded">
      <div
        className="h-full bg-emerald-500"
        style={{ width: `${pct}%` }}
        title={`strength ${pct}%`}
      />
    </div>
  );
}

function TypeChip({
  type, active, onClick,
}: { type: string; active: boolean; onClick: () => void }) {
  const Icon = ICONS[type] ?? Activity;
  const cls = TYPE_COLOR[type] ?? "bg-zinc-500/15 text-zinc-300 border-zinc-700";
  return (
    <button
      onClick={onClick}
      className={`inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[10px] uppercase ${
        active ? cls : "border-border/50 text-muted-foreground hover:text-foreground"
      }`}
    >
      <Icon className="h-3 w-3" />
      {type.replace(/_/g, " ")}
    </button>
  );
}

function SignalRowItem({ s }: { s: SignalRow }) {
  const Icon = ICONS[s.signal_type] ?? Activity;
  const cls = TYPE_COLOR[s.signal_type] ?? "bg-zinc-500/15 text-zinc-300 border-zinc-700";
  return (
    <li className="border-border/40 flex items-start gap-2 border-l-2 pl-3">
      <span className={`mt-0.5 inline-flex h-5 w-5 items-center justify-center rounded ${cls}`}>
        <Icon className="h-3 w-3" />
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className={`rounded border px-1 py-0.5 text-[10px] uppercase ${cls}`}>
            {s.signal_type.replace(/_/g, " ")}
          </span>
          <StrengthBar value={s.strength_score} />
          {s.confidence_score != null && (
            <span className="text-muted-foreground text-[10px]">
              conf {Math.round((s.confidence_score ?? 0) * 100)}%
            </span>
          )}
          <span className="text-muted-foreground ml-auto text-[10px]">
            {new Date(s.created_at).toLocaleString()}
          </span>
        </div>
        {s.description && <div className="mt-0.5 text-xs">{s.description}</div>}
        {s.source_url && (
          <a
            href={s.source_url}
            target="_blank"
            rel="noreferrer"
            className="text-blue-400 text-[11px] underline"
          >
            {s.source_url}
          </a>
        )}
      </div>
    </li>
  );
}

export function SignalsTimeline({ scope }: { scope: Scope }) {
  const qc = useQueryClient();
  const [typeFilter, setTypeFilter] = useState<SignalType | null>(null);

  const queryKey = ["signals", scope.kind, scope.id, typeFilter ?? "all"];
  const q = useQuery({
    queryKey,
    queryFn: () =>
      scope.kind === "company"
        ? signalsApi.listForCompany(scope.id, { type: typeFilter ?? undefined, limit: 100 })
        : signalsApi.listForContact(scope.id, { type: typeFilter ?? undefined, limit: 100 }),
  });

  const m = useMutation({
    mutationFn: () =>
      scope.kind === "company"
        ? signalsApi.extractForCompany(scope.id, { only_missing: false })
        : signalsApi.extractForContact(scope.id, { only_missing: false }),
    onSuccess: (res) => {
      toast.success(
        res.skipped
          ? `Skipped: ${res.error}`
          : `Extracted ${res.persisted}/${res.detected} signals`,
      );
      qc.invalidateQueries({ queryKey: ["signals", scope.kind, scope.id] });
    },
    onError: (err: unknown) => {
      const e = err as { response?: { data?: { detail?: string } }; message?: string };
      toast.error(e.response?.data?.detail ?? e.message ?? "Extraction failed");
    },
  });

  const presentTypes = useMemo(() => {
    const set = new Set<string>();
    for (const s of q.data?.data ?? []) set.add(s.signal_type);
    return Array.from(set);
  }, [q.data?.data]);

  return (
    <div className="border-border/40 rounded-md border p-3">
      <div className="mb-2 flex items-center justify-between">
        <div className="font-semibold">Signals</div>
        <Button
          size="sm"
          variant="outline"
          onClick={() => m.mutate()}
          disabled={m.isPending}
        >
          <Sparkles className="mr-1 h-3.5 w-3.5" />
          {m.isPending ? "Running…" : "Run signals"}
        </Button>
      </div>

      <div className="mb-2 flex flex-wrap gap-1">
        <TypeChip
          type="all"
          active={typeFilter === null}
          onClick={() => setTypeFilter(null)}
        />
        {SIGNAL_TYPES.filter((t) => presentTypes.includes(t) || typeFilter === t).map((t) => (
          <TypeChip
            key={t}
            type={t}
            active={typeFilter === t}
            onClick={() => setTypeFilter(typeFilter === t ? null : t)}
          />
        ))}
      </div>

      {q.isLoading ? (
        <p className="text-muted-foreground text-xs">Loading…</p>
      ) : (q.data?.count ?? 0) === 0 ? (
        <p className="text-muted-foreground text-xs">No signals yet.</p>
      ) : (
        <>
          <div className="mb-1 text-xs">
            <Badge variant="secondary">{q.data?.count} total</Badge>
          </div>
          <ul className="space-y-2">
            {(q.data?.data ?? []).map((s) => (
              <SignalRowItem key={s.id} s={s} />
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
