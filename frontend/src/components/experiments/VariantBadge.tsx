import { Badge } from "@/components/ui/badge";

const PALETTE = [
  "border-sky-600     bg-sky-500/15     text-sky-300",
  "border-emerald-600 bg-emerald-500/15 text-emerald-300",
  "border-amber-600   bg-amber-500/15   text-amber-200",
  "border-rose-600    bg-rose-500/15    text-rose-300",
  "border-violet-600  bg-violet-500/15  text-violet-300",
  "border-fuchsia-600 bg-fuchsia-500/15 text-fuchsia-300",
];

function hashName(name: string): number {
  let h = 0;
  for (let i = 0; i < name.length; i++) {
    h = (h * 31 + name.charCodeAt(i)) | 0;
  }
  return Math.abs(h);
}

export function VariantBadge({
  name,
  isControl,
  small,
}: {
  name: string;
  isControl?: boolean | number | null;
  small?: boolean;
}) {
  const cls = isControl
    ? "border-indigo-600 bg-indigo-500/20 text-indigo-200"
    : PALETTE[hashName(name) % PALETTE.length];
  return (
    <Badge
      variant="outline"
      className={`border ${cls} font-mono ${small ? "text-[10px]" : "text-xs"}`}
    >
      {isControl ? "★ " : ""}
      {name}
    </Badge>
  );
}
