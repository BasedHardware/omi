import { useEffect, useState } from "react";
import { Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useGoalStore } from "@/stores/goalStore";
import type { Goal } from "@/stores/goalStore";
import { GoalRow } from "./GoalRow";
import { GoalEditModal } from "./GoalEditModal";

/**
 * Embeddable goals card. Same content as `GoalsPage` without the page-level
 * header — meant to drop into a dashboard/widget grid.
 */
export function GoalsWidget() {
  const { goals, loadGoals, updateGoalProgress, deleteGoal } = useGoalStore();
  const [editing, setEditing] = useState<Goal | null>(null);
  const [modalOpen, setModalOpen] = useState(false);

  useEffect(() => {
    loadGoals();
  }, [loadGoals]);

  const handleNew = () => {
    setEditing(null);
    setModalOpen(true);
  };

  const canAdd = goals.length < 4;

  return (
    <div className="goals-widget">
      <div className="goals-widget-header">
        <h2>Goals</h2>
        <Button size="sm" variant="ghost" onClick={handleNew} disabled={!canAdd}>
          <Plus size={14} />
        </Button>
      </div>
      {goals.length === 0 ? (
        <p className="goals-widget-empty">Add a goal to start tracking.</p>
      ) : (
        <div className="goals-list">
          {goals.map((goal) => (
            <GoalRow
              key={goal.id}
              goal={goal}
              onEdit={() => {
                setEditing(goal);
                setModalOpen(true);
              }}
              onUpdateProgress={(v) => updateGoalProgress(goal.id, v)}
              onDelete={() => deleteGoal(goal.id)}
            />
          ))}
        </div>
      )}
      <GoalEditModal open={modalOpen} goal={editing} onOpenChange={setModalOpen} />
    </div>
  );
}
