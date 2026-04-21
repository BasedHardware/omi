import { useEffect, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowRight, CheckCircle2, ListChecks } from "lucide-react";
import { useTaskStore } from "@/stores/taskStore";
import type { Task } from "@/stores/taskStore";
import { bucketFor, dueLabel } from "@/components/tasks/taskDates";
import {
  Card,
  CardAction,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const MAX_ROWS = 5;

function TaskLine({
  task,
  onToggle,
}: {
  task: Task;
  onToggle: (id: string) => void;
}) {
  const bucket = bucketFor(task);
  const dueClass = cn(
    "inline-flex items-center rounded-md px-1.5 py-0.5 text-[10px] font-medium tabular-nums",
    bucket === "overdue" && "bg-destructive/10 text-destructive",
    bucket === "today" && "bg-amber-500/10 text-amber-500",
    bucket !== "overdue" &&
      bucket !== "today" &&
      "bg-muted text-muted-foreground",
  );

  return (
    <div className="group flex items-center gap-3 rounded-md px-2 py-1.5 -mx-2 transition-colors hover:bg-accent/50">
      <button
        type="button"
        onClick={() => onToggle(task.id)}
        aria-label={task.completed ? "Mark incomplete" : "Mark complete"}
        className={cn(
          "flex size-4 shrink-0 items-center justify-center rounded-full border transition-colors",
          task.completed
            ? "border-primary bg-primary text-primary-foreground"
            : "border-muted-foreground/40 hover:border-foreground",
        )}
      >
        {task.completed && (
          <svg width="10" height="10" viewBox="0 0 12 12" fill="none">
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
        className={cn(
          "flex-1 truncate text-sm text-foreground",
          task.completed && "text-muted-foreground line-through",
        )}
      >
        {task.description}
      </span>
      {task.due_at && <span className={dueClass}>{dueLabel(task.due_at)}</span>}
    </div>
  );
}

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
    <Card className="h-full gap-3 border-border/50 bg-card/40 py-5 shadow-none">
      <CardHeader className="px-5">
        <CardTitle className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
          <ListChecks size={14} />
          Today's Tasks
          {incompleteCount > 0 && (
            <Badge variant="secondary" className="ml-1 h-5 px-1.5 text-[10px]">
              {incompleteCount}
            </Badge>
          )}
        </CardTitle>
        <CardAction>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => navigate("/tasks")}
            className="h-7 gap-1 text-xs text-muted-foreground hover:text-foreground"
          >
            View all
            <ArrowRight size={12} />
          </Button>
        </CardAction>
      </CardHeader>
      <CardContent className="px-5">
        {isLoading && incompleteCount === 0 ? (
          <div className="flex h-20 items-center justify-center text-sm text-muted-foreground">
            Loading tasks...
          </div>
        ) : empty ? (
          <div className="flex h-24 flex-col items-center justify-center gap-1.5 text-sm text-muted-foreground">
            <CheckCircle2 size={20} className="text-emerald-500/70" />
            <span>You're all caught up.</span>
          </div>
        ) : (
          <div className="flex flex-col">
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
                onClick={() => navigate("/tasks")}
                className="mt-1 inline-flex items-center gap-1 self-start rounded-md px-2 py-1 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
              >
                {remaining} more {remaining === 1 ? "task" : "tasks"}
                <ArrowRight size={11} />
              </button>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
