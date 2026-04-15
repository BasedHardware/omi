import { useEffect, useMemo, useState } from "react";
import { useTaskStore } from "../../stores/taskStore";
import type { Task } from "../../stores/taskStore";

function TaskItem({
  task,
  onToggle,
  onDelete,
}: {
  task: Task;
  onToggle: () => void;
  onDelete: () => void;
}) {
  return (
    <div className="task-item">
      <button
        className={`task-checkbox${task.completed ? " task-checkbox-checked" : ""}`}
        onClick={onToggle}
        aria-label={task.completed ? "Mark incomplete" : "Mark complete"}
      >
        {task.completed && (
          <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
            <path
              d="M2 6L5 9L10 3"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        )}
      </button>
      <span
        className={`task-description${task.completed ? " task-description-done" : ""}`}
      >
        {task.description}
      </span>
      <button
        className="task-delete-button"
        onClick={(e) => { e.stopPropagation(); onDelete(); }}
        aria-label="Delete task"
      >
        <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
          <path d="M3 3L11 11M11 3L3 11" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
        </svg>
      </button>
    </div>
  );
}

function TaskGroup({
  title,
  tasks,
  onToggle,
  onDelete,
}: {
  title: string;
  tasks: Task[];
  onToggle: (id: string) => void;
  onDelete: (id: string) => void;
}) {
  if (tasks.length === 0) return null;

  return (
    <div className="task-group">
      <h3 className="task-group-title">
        {title}
        <span className="task-group-count">{tasks.length}</span>
      </h3>
      <div className="task-group-list">
        {tasks.map((task) => (
          <TaskItem
            key={task.id}
            task={task}
            onToggle={() => onToggle(task.id)}
            onDelete={() => onDelete(task.id)}
          />
        ))}
      </div>
    </div>
  );
}

export function TasksPage() {
  const { tasks, isLoading, loadTasks, toggleTask, createTask, deleteTask } = useTaskStore();
  const [newTaskText, setNewTaskText] = useState("");

  useEffect(() => {
    loadTasks();
  }, [loadTasks]);

  const grouped = useMemo(() => {
    const pending = tasks.filter((t) => !t.completed);
    const done = tasks.filter((t) => t.completed);
    return { pending, done };
  }, [tasks]);

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

  return (
    <div className="tasks-page">
      <div className="page-header">
        <h2>Tasks</h2>
      </div>
      <div className="task-create-bar">
        <input
          type="text"
          className="task-create-input"
          placeholder="Add a new task..."
          value={newTaskText}
          onChange={(e) => setNewTaskText(e.target.value)}
          onKeyDown={handleKeyDown}
        />
        <button
          className="task-create-button"
          onClick={handleCreate}
          disabled={!newTaskText.trim()}
        >
          Add
        </button>
      </div>
      <div className="tasks-content">
        {isLoading && tasks.length === 0 && (
          <div className="page-empty">Loading tasks...</div>
        )}
        {!isLoading && tasks.length === 0 && (
          <div className="page-empty">No tasks yet. Tasks from your meetings will appear here.</div>
        )}
        <TaskGroup title="Pending" tasks={grouped.pending} onToggle={toggleTask} onDelete={deleteTask} />
        <TaskGroup title="Done" tasks={grouped.done} onToggle={toggleTask} onDelete={deleteTask} />
      </div>
    </div>
  );
}
