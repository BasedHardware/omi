import { useEffect } from "react";
import { ArrowLeft, Check, Trophy } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { useGoalStore } from "@/stores/goalStore";
import type { Goal } from "@/stores/goalStore";
import { getEmojiForTitle } from "./emoji";

function relativeDate(iso: string | null | undefined): string {
  if (!iso) return "";
  const then = new Date(iso).getTime();
  if (!Number.isFinite(then)) return "";
  const diffMs = Date.now() - then;
  const mins = Math.floor(diffMs / 60_000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins} minute${mins === 1 ? "" : "s"} ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours} hour${hours === 1 ? "" : "s"} ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days} day${days === 1 ? "" : "s"} ago`;
  const months = Math.floor(days / 30);
  return `${months} month${months === 1 ? "" : "s"} ago`;
}

export function GoalsHistoryPage() {
  const { completedGoals, loadCompletedGoals } = useGoalStore();
  const navigate = useNavigate();

  useEffect(() => {
    loadCompletedGoals();
  }, [loadCompletedGoals]);

  return (
    <div className="goals-page">
      <div className="goals-header">
        <div>
          <Button variant="ghost" size="sm" onClick={() => navigate("/goals")}>
            <ArrowLeft size={14} className="mr-1" /> Back
          </Button>
          <h1 className="goals-title" style={{ marginTop: 8 }}>History</h1>
          <p className="goals-subtitle">Goals you've completed or removed.</p>
        </div>
      </div>

      {completedGoals.length === 0 ? (
        <div className="goals-empty">
          <Trophy size={24} className="goals-empty-icon" />
          <h3>No goals history yet</h3>
          <p>Completed and removed goals will show up here.</p>
        </div>
      ) : (
        <div className="goals-list">
          {completedGoals.map((goal) => (
            <CompletedGoalRow key={goal.id} goal={goal} />
          ))}
        </div>
      )}
    </div>
  );
}

function CompletedGoalRow({ goal }: { goal: Goal }) {
  const wasCompleted =
    goal.completed_at &&
    goal.target_value > 0 &&
    goal.current_value >= goal.target_value;

  return (
    <div className="goal-row" style={{ opacity: 0.85 }}>
      <div className="goal-emoji">{getEmojiForTitle(goal.title)}</div>
      <div className="goal-body">
        <div className="goal-top">
          <div className="goal-title" style={{ cursor: "default" }}>{goal.title}</div>
          <div className="goal-top-actions">
            <span className="goal-progress-text">
              {Math.round(goal.current_value)}/{Math.round(goal.target_value)}
              {goal.unit ? ` ${goal.unit}` : ""}
            </span>
            {wasCompleted ? (
              <span
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 4,
                  color: "#22C55E",
                  fontSize: 11,
                }}
                title="Completed"
              >
                <Check size={12} />
              </span>
            ) : (
              <span style={{ color: "rgba(255,255,255,0.4)", fontSize: 11 }}>
                Removed
              </span>
            )}
          </div>
        </div>
        <div style={{ fontSize: 11, color: "rgba(255,255,255,0.45)" }}>
          {relativeDate(goal.completed_at ?? goal.updated_at)}
        </div>
      </div>
    </div>
  );
}
