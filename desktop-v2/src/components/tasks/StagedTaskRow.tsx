import { Flag, Plus, Sparkles, X } from "lucide-react";
import type { StagedTask } from "../../stores/stagedTaskStore";
import { dueLabel } from "./taskDates";

interface Props {
  task: StagedTask;
  onPromote: () => void;
  onDismiss: () => void;
}

function parseTags(raw: string | null): string[] {
  if (!raw) return [];
  try {
    const v = JSON.parse(raw);
    if (Array.isArray(v)) return v.filter((t) => typeof t === "string").slice(0, 3);
  } catch {
    // fall through
  }
  return [];
}

export function StagedTaskRow({ task, onPromote, onDismiss }: Props) {
  const priority = task.priority?.toLowerCase() ?? null;
  const tags = parseTags(task.tags_json);
  const conf = task.confidence != null ? Math.round(task.confidence * 100) : null;
  const relevance = task.relevance_score;

  const priorityClass =
    priority === "high"
      ? "staged-priority staged-priority-high"
      : priority === "medium"
        ? "staged-priority staged-priority-medium"
        : priority === "low"
          ? "staged-priority staged-priority-low"
          : null;

  return (
    <div className="staged-row">
      <div className="staged-accent" />
      <div className="staged-body">
        <div className="staged-top">
          <Sparkles size={12} className="staged-sparkle" />
          <span className="staged-kicker">Suggested</span>
          {task.source_app && (
            <>
              <span className="staged-dot">·</span>
              <span className="staged-source" title={task.window_title ?? undefined}>
                {task.source_app}
              </span>
            </>
          )}
          {conf != null && (
            <>
              <span className="staged-dot">·</span>
              <span className="staged-confidence">{conf}% match</span>
            </>
          )}
        </div>
        <div className="staged-description">{task.description}</div>
        {(priorityClass || task.due_at || tags.length > 0) && (
          <div className="staged-chips">
            {priorityClass && (
              <span className={priorityClass}>
                <Flag size={10} />
                <span>{priority}</span>
              </span>
            )}
            {task.due_at && (
              <span className="task-chip task-chip-link">{dueLabel(task.due_at)}</span>
            )}
            {tags.map((tag) => (
              <span key={tag} className="staged-tag">
                {tag}
              </span>
            ))}
          </div>
        )}
        {relevance != null && (
          <div
            className="staged-relevance"
            title={`Relevance score: ${relevance}/100`}
          >
            <div
              className="staged-relevance-fill"
              style={{ width: `${Math.min(100, Math.max(0, relevance))}%` }}
            />
          </div>
        )}
      </div>
      <div className="staged-actions">
        <button
          type="button"
          className="staged-promote"
          onClick={onPromote}
          aria-label="Add to tasks"
          title="Add to tasks"
        >
          <Plus size={14} />
          <span>Add</span>
        </button>
        <button
          type="button"
          className="task-action"
          onClick={onDismiss}
          aria-label="Dismiss"
          title="Dismiss"
        >
          <X size={14} />
        </button>
      </div>
    </div>
  );
}
