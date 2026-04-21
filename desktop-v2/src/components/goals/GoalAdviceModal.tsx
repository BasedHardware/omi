import { useEffect, useState } from "react";
import { Lightbulb, RefreshCw } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import type { Goal } from "@/stores/goalStore";
import { getGoalAdvice } from "@/services/goalsAIService";
import { getEmojiForTitle } from "./emoji";

interface Props {
  open: boolean;
  goal: Goal | null;
  onOpenChange: (open: boolean) => void;
}

export function GoalAdviceModal({ open, goal, onOpenChange }: Props) {
  const [advice, setAdvice] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open || !goal) return;
    setAdvice(null);
    setError(null);
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, goal?.id]);

  const load = async () => {
    if (!goal) return;
    setLoading(true);
    setError(null);
    try {
      const text = await getGoalAdvice(goal.id);
      if (text) setAdvice(text);
      else setError("Couldn't generate advice. Try again in a moment.");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  if (!goal) return null;

  const progress =
    goal.target_value > 0
      ? Math.min(100, Math.round((goal.current_value / goal.target_value) * 100))
      : 0;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Lightbulb size={16} className="text-yellow-400" />
            Advice
          </DialogTitle>
        </DialogHeader>

        <div className="flex items-center gap-3 rounded-lg bg-white/5 p-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-md bg-white/10 text-xl">
            {getEmojiForTitle(goal.title)}
          </div>
          <div className="flex-1 min-w-0">
            <div className="truncate text-sm font-medium">{goal.title}</div>
            <div className="text-xs text-muted-foreground">
              {Math.round(goal.current_value)}/{Math.round(goal.target_value)} · {progress}%
            </div>
          </div>
        </div>

        <div className="min-h-24 py-2 text-sm leading-relaxed text-foreground">
          {loading && <p className="text-muted-foreground">Thinking…</p>}
          {error && !loading && <p className="text-destructive">{error}</p>}
          {advice && !loading && <p>{advice}</p>}
        </div>

        <div className="flex items-center justify-between">
          <Button variant="ghost" size="sm" onClick={load} disabled={loading}>
            <RefreshCw size={14} className={`mr-1 ${loading ? "animate-spin" : ""}`} />
            New advice
          </Button>
          <Button variant="ghost" size="sm" onClick={() => onOpenChange(false)}>
            Close
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
