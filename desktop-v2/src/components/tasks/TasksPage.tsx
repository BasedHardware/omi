import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Plus } from "lucide-react";
import { useTaskStore } from "../../stores/taskStore";
import type { Task } from "../../stores/taskStore";
import { BUCKET_META, bucketFor, type DueBucket } from "./taskDates";
import { TaskRow } from "./TaskRow";
import { TaskSection } from "./TaskSection";
import { TasksHeader, type FilterKey } from "./TasksHeader";

const VALID_FILTERS: FilterKey[] = [
  "all",
  "overdue",
  "today",
  "nodate",
  "done",
];

const BUCKET_ORDER: DueBucket[] = [
  "overdue",
  "today",
  "tomorrow",
  "thisWeek",
  "later",
  "noDate",
];

export function TasksPage() {
  const {
    tasks,
    isLoading,
    loadTasks,
    toggleTask,
    createTask,
    deleteTask,
  } = useTaskStore();
  const [newTaskText, setNewTaskText] = useState("");
  const [searchParams, setSearchParams] = useSearchParams();
  const paramFilter = searchParams.get("filter") as FilterKey | null;
  const filter: FilterKey =
    paramFilter && VALID_FILTERS.includes(paramFilter) ? paramFilter : "all";

  const setFilter = (next: FilterKey) => {
    const params = new URLSearchParams(searchParams);
    if (next === "all") {
      params.delete("filter");
    } else {
      params.set("filter", next);
    }
    setSearchParams(params, { replace: true });
  };

  useEffect(() => {
    loadTasks();
  }, [loadTasks]);

  const handleCreate = async () => {
    const text = newTaskText.trim();
    if (!text) return;
    setNewTaskText("");
    await createTask(text);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") {
      e.preventDefault();
      handleCreate();
    }
  };

  const filtered = useMemo(() => {
    if (filter === "done") return tasks.filter((t) => t.completed);
    const open = tasks.filter((t) => !t.completed);
    if (filter === "all") return open;
    return open.filter((t) => {
      const b = bucketFor(t);
      if (filter === "overdue") return b === "overdue";
      if (filter === "today") return b === "today";
      if (filter === "nodate") return b === "noDate";
      return true;
    });
  }, [tasks, filter]);

  const buckets = useMemo(() => {
    const map: Record<DueBucket, Task[]> = {
      overdue: [],
      today: [],
      tomorrow: [],
      thisWeek: [],
      later: [],
      noDate: [],
    };
    for (const t of filtered) {
      map[bucketFor(t)].push(t);
    }
    return map;
  }, [filtered]);

  const empty = !isLoading && tasks.length === 0;

  return (
    <div className="tasks-page">
      <TasksHeader
        tasks={tasks}
        stagedCount={0}
        filter={filter}
        onFilter={setFilter}
      />

      <div className="tasks-content">
        <div className="tasks-create-bar">
          <Plus size={14} className="tasks-create-icon" />
          <input
            type="text"
            className="tasks-create-input"
            placeholder="Add a task..."
            value={newTaskText}
            onChange={(e) => setNewTaskText(e.target.value)}
            onKeyDown={handleKeyDown}
          />
          <button
            className="tasks-create-submit"
            onClick={handleCreate}
            disabled={!newTaskText.trim()}
          >
            Add
          </button>
        </div>

        {isLoading && tasks.length === 0 && (
          <div className="page-empty">Loading tasks...</div>
        )}

        {empty && (
          <div className="page-empty">
            No tasks yet. Add one above, or Nooto will extract them from your
            meetings.
          </div>
        )}

        {filter === "done" ? (
          filtered.length === 0 ? (
            <div className="page-empty">No completed tasks.</div>
          ) : (
            <div className="task-list">
              {filtered.map((task) => (
                <TaskRow
                  key={task.id}
                  task={task}
                  onToggle={() => toggleTask(task.id)}
                  onUpdate={() => {}}
                  onDelete={() => deleteTask(task.id)}
                />
              ))}
            </div>
          )
        ) : (
          BUCKET_ORDER.map((bucket) => {
            const items = buckets[bucket];
            if (items.length === 0) return null;
            const meta = BUCKET_META[bucket];
            return (
              <TaskSection
                key={bucket}
                bucket={bucket}
                label={meta.label}
                hint={meta.hint}
                count={items.length}
                defaultOpen={bucket === "overdue" || bucket === "today" || items.length <= 5}
              >
                {items.map((task) => (
                  <TaskRow
                    key={task.id}
                    task={task}
                    onToggle={() => toggleTask(task.id)}
                    onUpdate={() => {}}
                    onDelete={() => deleteTask(task.id)}
                  />
                ))}
              </TaskSection>
            );
          })
        )}
      </div>
    </div>
  );
}
