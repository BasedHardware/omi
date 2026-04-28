import { useEffect, useMemo, useState } from "react";
import { History, Plus, Sparkles, Target } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/ui/page-header";
import { useGoalStore } from "@/stores/goalStore";
import type { Goal } from "@/stores/goalStore";
import { GoalRow } from "./GoalRow";
import { GoalEditModal } from "./GoalEditModal";
import { GoalAdviceModal } from "./GoalAdviceModal";
import { generateNow } from "@/services/goalGenerationService";

const MAX_ACTIVE_GOALS = 4;

function goalFraction(g: Goal): number {
  if (g.target_value <= g.min_value) return 0;
  return Math.max(
    0,
    Math.min(1, (g.current_value - g.min_value) / (g.target_value - g.min_value)),
  );
}

export function GoalsPage() {
  const { goals, isLoading, isGenerating, loadGoals, updateGoalProgress, deleteGoal } =
    useGoalStore();
  const navigate = useNavigate();
  const [editing, setEditing] = useState<Goal | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [adviceGoal, setAdviceGoal] = useState<Goal | null>(null);
  const [adviceOpen, setAdviceOpen] = useState(false);

  useEffect(() => {
    loadGoals();
    const id = setInterval(() => loadGoals(true), 60_000);
    return () => clearInterval(id);
  }, [loadGoals]);

  const handleNew = () => {
    setEditing(null);
    setModalOpen(true);
  };

  const handleEdit = (goal: Goal) => {
    setEditing(goal);
    setModalOpen(true);
  };

  const handleAdvice = (goal: Goal) => {
    setAdviceGoal(goal);
    setAdviceOpen(true);
  };

  const handleGenerate = async () => {
    await generateNow();
  };

  // The 4-goal cap only applies to native goals — integration goals (Jira
  // releases, etc.) flow in from the source tracker and shouldn't be
  // throttled by a UI limit.
  const isNativeGoal = (g: Goal) => !g.source_app_id;
  const nativeGoals = useMemo(() => goals.filter(isNativeGoal), [goals]);
  const integrationGoals = useMemo(() => goals.filter((g) => !isNativeGoal(g)), [goals]);
  const canAdd = nativeGoals.length < MAX_ACTIVE_GOALS;
  const empty = !isLoading && goals.length === 0;

  const summary = useMemo(() => {
    if (goals.length === 0) return null;
    const fractions = goals.map(goalFraction);
    const avg = fractions.reduce((a, b) => a + b, 0) / fractions.length;
    const onTrack = fractions.filter((f) => f >= 0.5).length;
    const completed = fractions.filter((f) => f >= 1).length;
    return { avg, onTrack, completed, total: goals.length };
  }, [goals]);

  return (
    <div className="goals-page">
      <PageHeader
        title="Goals"
        subtitle={
          goals.length === 0
            ? "Track what you're working toward"
            : integrationGoals.length > 0
              ? `${nativeGoals.length} of ${MAX_ACTIVE_GOALS} active · ${integrationGoals.length} from integrations`
              : `${nativeGoals.length} of ${MAX_ACTIVE_GOALS} active`
        }
        actions={
          <>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => navigate("/goals/history")}
            >
              <History size={14} className="mr-1.5" /> History
            </Button>
            <Button size="sm" onClick={handleNew} disabled={!canAdd}>
              <Plus size={14} className="mr-1.5" /> New goal
            </Button>
          </>
        }
      />

      <div className="goals-content">
        {empty ? (
          <div className="goals-empty">
            <div className="goals-empty-icon-wrap">
              <Target size={28} />
            </div>
            <h3>Set your first goal</h3>
            <p>
              Goals help Nooto understand what matters to you. Add one yourself
              or let Nooto suggest one based on your recent conversations.
            </p>
            <div className="goals-empty-actions">
              <Button onClick={handleNew}>
                <Plus size={14} className="mr-1.5" /> Add goal
              </Button>
              <Button
                variant="secondary"
                onClick={handleGenerate}
                disabled={isGenerating}
              >
                <Sparkles size={14} className="mr-1.5" />
                {isGenerating ? "Generating…" : "Suggest with AI"}
              </Button>
            </div>
          </div>
        ) : (
          <>
            {summary && (
              <div className="goals-summary">
                <div className="goals-summary-item">
                  <span className="goals-summary-value">
                    {Math.round(summary.avg * 100)}%
                  </span>
                  <span className="goals-summary-label">Average</span>
                </div>
                <div className="goals-summary-divider" />
                <div className="goals-summary-item">
                  <span className="goals-summary-value">
                    {summary.onTrack}
                    <span className="goals-summary-denom">/{summary.total}</span>
                  </span>
                  <span className="goals-summary-label">On track</span>
                </div>
                <div className="goals-summary-divider" />
                <div className="goals-summary-item">
                  <span className="goals-summary-value">{summary.completed}</span>
                  <span className="goals-summary-label">Completed</span>
                </div>
                <div className="goals-summary-spacer" />
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={handleGenerate}
                  disabled={isGenerating || !canAdd}
                  className="goals-summary-suggest"
                >
                  <Sparkles size={14} className="mr-1.5" />
                  {isGenerating ? "Thinking…" : "Suggest"}
                </Button>
              </div>
            )}

            <div className="goals-list">
              {nativeGoals.map((goal) => (
                <GoalRow
                  key={goal.id}
                  goal={goal}
                  onEdit={() => handleEdit(goal)}
                  onUpdateProgress={(v) => updateGoalProgress(goal.id, v)}
                  onDelete={() => deleteGoal(goal.id)}
                  onGetAdvice={() => handleAdvice(goal)}
                />
              ))}
              {!canAdd && (
                <p className="goals-limit-note">
                  You've reached the {MAX_ACTIVE_GOALS}-goal limit. Complete or
                  delete one to add another.
                </p>
              )}
              {integrationGoals.length > 0 && (
                <>
                  <h3 className="goals-section-heading">From your integrations</h3>
                  {integrationGoals.map((goal) => (
                    <GoalRow
                      key={goal.id}
                      goal={goal}
                      onEdit={() => handleEdit(goal)}
                      onUpdateProgress={(v) => updateGoalProgress(goal.id, v)}
                      onDelete={() => deleteGoal(goal.id)}
                      onGetAdvice={() => handleAdvice(goal)}
                    />
                  ))}
                </>
              )}
            </div>
          </>
        )}
      </div>

      <GoalEditModal open={modalOpen} goal={editing} onOpenChange={setModalOpen} />
      <GoalAdviceModal open={adviceOpen} goal={adviceGoal} onOpenChange={setAdviceOpen} />
    </div>
  );
}
