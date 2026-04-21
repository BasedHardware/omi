import { useEffect, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowRight, Target } from "lucide-react";
import { useGoalStore } from "@/stores/goalStore";
import type { Goal } from "@/stores/goalStore";
import { getEmojiForTitle } from "@/components/goals/emoji";
import {
  Card,
  CardAction,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

const MAX_GOALS = 3;

function colorForProgress(progress: number): string {
  if (progress >= 1) return "#22C55E";
  if (progress >= 0.8) return "#4ADE80";
  if (progress >= 0.6) return "#84CC16";
  if (progress >= 0.4) return "#FACC15";
  if (progress >= 0.2) return "#F97316";
  return "#60A5FA";
}

function fractionFor(goal: Goal): number {
  const span = goal.target_value - goal.min_value;
  if (span <= 0) return 0;
  return Math.max(
    0,
    Math.min(1, (goal.current_value - goal.min_value) / span),
  );
}

function GoalLine({ goal }: { goal: Goal }) {
  const fraction = fractionFor(goal);
  const percent = Math.round(fraction * 100);
  const color = colorForProgress(fraction);
  const currentLabel = `${Math.round(goal.current_value)}${goal.unit ? ` ${goal.unit}` : ""}`;
  const targetLabel = `${Math.round(goal.target_value)}${goal.unit ? ` ${goal.unit}` : ""}`;

  return (
    <div className="flex items-center gap-3 rounded-md px-2 py-1.5 -mx-2 transition-colors hover:bg-accent/50">
      <div className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-muted text-base">
        {getEmojiForTitle(goal.title)}
      </div>
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <div className="flex items-baseline justify-between gap-2">
          <span className="truncate text-sm font-medium text-foreground">
            {goal.title}
          </span>
          <span
            className="shrink-0 text-xs font-semibold tabular-nums"
            style={{ color }}
          >
            {percent}%
          </span>
        </div>
        <div className="relative h-1 w-full overflow-hidden rounded-full bg-muted">
          <div
            className="h-full rounded-full transition-all duration-500 ease-out"
            style={{
              width: `${fraction * 100}%`,
              background: `linear-gradient(90deg, ${color}B3, ${color})`,
            }}
          />
        </div>
        <div className="text-[11px] tabular-nums text-muted-foreground">
          {currentLabel}{" "}
          <span className="opacity-50">/</span> {targetLabel}
        </div>
      </div>
    </div>
  );
}

export function ActiveGoalsWidget() {
  const navigate = useNavigate();
  const goals = useGoalStore((s) => s.goals);
  const loadGoals = useGoalStore((s) => s.loadGoals);

  useEffect(() => {
    void loadGoals(true);
  }, [loadGoals]);

  const { visible, activeCount } = useMemo(() => {
    // The store's `goals` list is already filtered to active + non-deleted
    // by the Rust `list_active` query, so just paginate here.
    return {
      visible: goals.slice(0, MAX_GOALS),
      activeCount: goals.length,
    };
  }, [goals]);

  return (
    <Card className="h-full gap-3 border-border/50 bg-card/40 py-5 shadow-none">
      <CardHeader className="px-5">
        <CardTitle className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
          <Target size={14} />
          Active Goals
          {activeCount > 0 && (
            <Badge variant="secondary" className="ml-1 h-5 px-1.5 text-[10px]">
              {activeCount}
            </Badge>
          )}
        </CardTitle>
        <CardAction>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => navigate("/goals")}
            className="h-7 gap-1 text-xs text-muted-foreground hover:text-foreground"
          >
            View all
            <ArrowRight size={12} />
          </Button>
        </CardAction>
      </CardHeader>
      <CardContent className="flex flex-1 flex-col px-5">
        {visible.length === 0 ? (
          <div className="flex flex-1 flex-col items-center justify-center gap-2 py-6 text-sm text-muted-foreground">
            <div className="flex size-10 items-center justify-center rounded-full bg-muted">
              <Target size={18} className="opacity-60" />
            </div>
            <span>No active goals yet.</span>
            <button
              type="button"
              onClick={() => navigate("/goals")}
              className="text-xs font-medium text-primary hover:underline"
            >
              Set your first goal
            </button>
          </div>
        ) : (
          <div className="flex flex-col gap-1">
            {visible.map((goal) => (
              <GoalLine key={goal.id} goal={goal} />
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
