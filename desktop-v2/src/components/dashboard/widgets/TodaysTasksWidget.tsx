import { useEffect, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowRight, CheckCircle2, ListChecks } from "lucide-react";
import { useTaskStore } from "@/stores/taskStore";
import type { Task } from "@/stores/taskStore";
import { bucketFor, dueLabel } from "@/components/tasks/taskDates";

const MAX_ROWS = 5;

interface TaskLineProps {
  task: Task;
  onToggle: (id: string) => void;
}

function TaskLine({ task, onToggle }: TaskLineProps) {
  const bucket = bucketFor(task);
  const chipClass =
    bucket === "overdue"
      ? "dashboard-task-due dashboard-task-due-overdue"
      : bucket === "today"
        ? "dashboard-task-due dashboard-task-due-today"
        : "dashboard-task-due";

  return (
    <div className="dashboard-task-row">
      <button
        type="button"
        className={`dashboard-task-check${task.completed ? " dashboard-task-check-on" : ""}`}
        onClick={() => onToggle(task.id)}
        aria-label={task.completed ? "Mark incomplete" : "Mark complete"}
      >
        {task.completed && (
          <svg width="11" height="11" viewBox="0 0 12 12" fill="none">
            <path
              d="M2 6L5 9L10 3"
              stroke="currentColor"
              strokeWidth="2.2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        )}
      </button>
      <span
        className={`dashboard-task-text${task.completed ? " dashboard-task-text-done" : ""}`}
      >
        {task.description}
      </span>
      {task.due_at && (
        <span className={chipClass}>{dueLabel(task.due_at)}</span>
      )}
    </div>
  );
}

/**
 * Shows up to 5 relevant open tasks: overdue first, then today's due tasks,
 * then recent tasks with no due date. "View all" routes to `/tasks`.
 */
export function TodaysTasksWidget() {
  const navigate = useNavigate();
  const tasks = useTaskStore((s) => s.tasks);
  const isLoading = useTaskStore((s) => s.isLoading);
  const loadTasks = useTaskStore((s) => s.loadTasks);
  const toggleTask = useTaskStore((s) => s.toggleTask);

  useEffect(() => {
    void loadTasks();
  }, [loadTasks]);

  const { visible, remaining, incompleteCount } = useMemo(() => {
    const open = tasks.filter((t) => !t.completed);
    const overdue: Task[] = [];
    const today: Task[] = [];
    const rest: Task[] = [];

    for (const t of open) {
      const b = bucketFor(t);
      if (b === "overdue") overdue.push(t);
      else if (b === "today") today.push(t);
      else rest.push(t);
    }

    const sortByDue = (a: Task, b: Task) => {
      const ta = a.due_at ? Date.parse(a.due_at) : Number.POSITIVE_INFINITY;
      const tb = b.due_at ? Date.parse(b.due_at) : Number.POSITIVE_INFINITY;
      if (ta !== tb) return ta - tb;
      const ca = a.created_at ? Date.parse(a.created_at) : 0;
      const cb = b.created_at ? Date.parse(b.created_at) : 0;
      return cb - ca;
    };

    overdue.sort(sortByDue);
    today.sort(sortByDue);
    rest.sort(sortByDue);

    const ordered = [...overdue, ...today, ...rest];
    return {
      visible: ordered.slice(0, MAX_ROWS),
      remaining: Math.max(0, ordered.length - MAX_ROWS),
      incompleteCount: open.length,
    };
  }, [tasks]);

  const empty = !isLoading && incompleteCount === 0;

  return (
    <section className="dashboard-card dashboard-tasks-card">
      <div className="dashboard-card-head">
        <div className="dashboard-card-head-icon">
          <ListChecks size={14} />
        </div>
        <h2 className="dashboard-card-title">Today's Tasks</h2>
        <span className="dashboard-card-badge">{incompleteCount}</span>
        <button
          type="button"
          className="dashboard-card-link"
          onClick={() => navigate("/tasks")}
          aria-label="View all tasks"
        >
          View all <ArrowRight size={12} />
        </button>
      </div>

      {isLoading && incompleteCount === 0 ? (
        <div className="dashboard-card-empty">Loading tasks...</div>
      ) : empty ? (
        <div className="dashboard-card-empty dashboard-card-empty-pos">
          <CheckCircle2 size={22} className="dashboard-card-empty-icon" />
          <span>You're all caught up.</span>
        </div>
      ) : (
        <div className="dashboard-tasks-list">
          {visible.map((task) => (
            <TaskLine
              key={task.id}
              task={task}
              onToggle={(id) => void toggleTask(id)}
            />
          ))}
          {remaining > 0 && (
            <button
              type="button"
              className="dashboard-tasks-more"
              onClick={() => navigate("/tasks")}
            >
              {remaining} more {remaining === 1 ? "task" : "tasks"} <ArrowRight size={11} />
            </button>
          )}
        </div>
      )}
    </section>
  );
}
