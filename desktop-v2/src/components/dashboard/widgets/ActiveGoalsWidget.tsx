import { useEffect, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowRight, Target } from "lucide-react";
import { useGoalStore } from "@/stores/goalStore";
import type { Goal } from "@/stores/goalStore";
import { getEmojiForTitle } from "@/components/goals/emoji";

const MAX_GOALS = 3;

/** Same ramp as GoalRow.colorForProgress — kept local to avoid a cross-import
 *  from a scoped-out directory. */
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
  return Math.max(0, Math.min(1, (goal.current_value - goal.min_value) / span));
}

function GoalLine({ goal }: { goal: Goal }) {
  const fraction = fractionFor(goal);
  const percent = Math.round(fraction * 100);
  const color = colorForProgress(fraction);
  const currentLabel = `${Math.round(goal.current_value)}${goal.unit ? ` ${goal.unit}` : ""}`;
  const targetLabel = `${Math.round(goal.target_value)}${goal.unit ? ` ${goal.unit}` : ""}`;

  return (
    <div className="dashboard-goal-row">
      <div className="dashboard-goal-emoji" aria-hidden="true">
        {getEmojiForTitle(goal.title)}
      </div>
      <div className="dashboard-goal-body">
        <div className="dashboard-goal-head">
          <span className="dashboard-goal-title">{goal.title}</span>
          <span className="dashboard-goal-percent" style={{ color }}>
            {percent}%
          </span>
        </div>
        <div className="dashboard-goal-bar">
          <div
            className="dashboard-goal-bar-fill"
            style={{
              width: `${fraction * 100}%`,
              background: `linear-gradient(90deg, ${color}B3, ${color})`,
            }}
          />
        </div>
        <div className="dashboard-goal-numbers tabular-nums">
          {currentLabel} <span className="dashboard-goal-numbers-sep">/</span>{" "}
          {targetLabel}
        </div>
      </div>
    </div>
  );
}

/**
 * Top-3 active goals with inline progress bars. Read-only surface; click
 * "View all" to manage goals on `/goals`.
 */
export function ActiveGoalsWidget() {
  const navigate = useNavigate();
  const goals = useGoalStore((s) => s.goals);
  const loadGoals = useGoalStore((s) => s.loadGoals);

  useEffect(() => {
    void loadGoals();
  }, [loadGoals]);

  const { visible, activeCount } = useMemo(() => {
    const active = goals.filter((g) => g.is_active && !g.deleted);
    return {
      visible: active.slice(0, MAX_GOALS),
      activeCount: active.length,
    };
  }, [goals]);

  return (
    <section className="dashboard-card dashboard-goals-card">
      <div className="dashboard-card-head">
        <div className="dashboard-card-head-icon">
          <Target size={14} />
        </div>
        <h2 className="dashboard-card-title">Active Goals</h2>
        <span className="dashboard-card-badge">{activeCount}</span>
        <button
          type="button"
          className="dashboard-card-link"
          onClick={() => navigate("/goals")}
          aria-label="View all goals"
        >
          View all <ArrowRight size={12} />
        </button>
      </div>

      {visible.length === 0 ? (
        <div className="dashboard-card-empty dashboard-card-empty-pos">
          <Target size={22} className="dashboard-card-empty-icon" />
          <span>No active goals.</span>
          <button
            type="button"
            className="dashboard-card-empty-cta"
            onClick={() => navigate("/goals")}
          >
            Set a goal
          </button>
        </div>
      ) : (
        <div className="dashboard-goals-list">
          {visible.map((goal) => (
            <GoalLine key={goal.id} goal={goal} />
          ))}
        </div>
      )}
    </section>
  );
}
