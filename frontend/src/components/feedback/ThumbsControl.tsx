import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ThumbsDown, ThumbsUp } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { feedbackApi, type FeedbackKind } from "@/lib/api";

type Props = {
  projectId: number;
  leadId?: number | null;
  outreachMessageId?: number | null;
  variantId?: number | null;
  size?: "sm" | "default";
  invalidateKeys?: unknown[][];
};

export function ThumbsControl({
  projectId, leadId, outreachMessageId, variantId,
  size = "sm", invalidateKeys = [],
}: Props) {
  const qc = useQueryClient();
  const mut = useMutation({
    mutationFn: (kind: FeedbackKind) =>
      feedbackApi.create({
        project_id: projectId,
        kind,
        source: "human",
        lead_id: leadId ?? null,
        outreach_message_id: outreachMessageId ?? null,
        variant_id: variantId ?? null,
      }),
    onSuccess: (_res, kind) => {
      toast.success(kind === "thumbs_up" ? "Thanks!" : "Noted");
      for (const key of invalidateKeys) {
        qc.invalidateQueries({ queryKey: key });
      }
      qc.invalidateQueries({ queryKey: ["feedback-list"] });
      qc.invalidateQueries({ queryKey: ["feedback-summary"] });
    },
    onError: (e: unknown) => toast.error((e as Error)?.message ?? "feedback failed"),
  });

  return (
    <div className="flex items-center gap-1">
      <Button
        variant="outline"
        size={size}
        disabled={mut.isPending}
        onClick={() => mut.mutate("thumbs_up")}
        title="Thumbs up"
      >
        <ThumbsUp className="h-4 w-4" />
      </Button>
      <Button
        variant="outline"
        size={size}
        disabled={mut.isPending}
        onClick={() => mut.mutate("thumbs_down")}
        title="Thumbs down"
      >
        <ThumbsDown className="h-4 w-4" />
      </Button>
    </div>
  );
}
