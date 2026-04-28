import { useEffect, useRef, useState } from "react";
import { Calendar, Link2, Trash2, X } from "lucide-react";
import { open as openShell } from "@tauri-apps/plugin-shell";
import type { Task } from "../../stores/taskStore";
import { useAppStore } from "../../stores/appStore";
import { bucketFor, dueLabel, isNew } from "./taskDates";
import { IntegrationBadge } from "./IntegrationBadge";

interface Props {
  task: Task;
  /** When provided, clicking the row title opens the side detail panel
   *  instead of toggling inline edit / opening the source ticket. The panel
   *  surfaces the same actions; the row just becomes a selector. */
  selected?: boolean;
  onSelect?: () => void;
  onToggle: () => void;
  onUpdate: (patch: { description?: string; due_at?: string | null }) => void;
  onDelete: () => void;
  onOpenConversation?: (conversationId: string) => void;
}

function toIsoAtNoon(dateStr: string): string {
  // dateStr is "YYYY-MM-DD" from <input type="date">
  const d = new Date(`${dateStr}T12:00:00`);
  return d.toISOString();
}

function toDateInput(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
}

export function TaskRow({
  task,
  selected = false,
  onSelect,
  onToggle,
  onUpdate,
  onDelete,
  onOpenConversation,
}: Props) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(task.description);
  const [completing, setCompleting] = useState(false);
  const [showDate, setShowDate] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const dateInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (editing) inputRef.current?.focus();
  }, [editing]);

  useEffect(() => {
    setDraft(task.description);
  }, [task.description]);

  const bucket = bucketFor(task);
  const fresh = !task.completed && isNew(task);
  // Integration rows (Jira/Linear/…) are read-only by default — the actual
  // ticket lives in the source tracker. The user can opt in per-app via
  // Settings → Apps → <app> → Two-way sync; when on, the checkbox dispatches
  // a status writeback through the plugin's update_issue_status tool.
  const isIntegration = !!task.source && task.source !== "native";
  const twoWaySync = useAppStore((s) =>
    task.source_app_id ? Boolean(s.twoWaySyncByAppId[task.source_app_id]) : false,
  );
  const checkboxDisabled = isIntegration && !twoWaySync;

  const handleToggle = () => {
    if (checkboxDisabled) return;
    if (task.completed) {
      onToggle();
      return;
    }
    setCompleting(true);
    setTimeout(() => {
      onToggle();
      setCompleting(false);
    }, 320);
  };

  const openExternal = () => {
    if (!task.external_url) return;
    void openShell(task.external_url).catch((err) =>
      console.warn("[TaskRow] open external failed:", err),
    );
  };

  const saveDraft = () => {
    const text = draft.trim();
    setEditing(false);
    if (text && text !== task.description) {
      onUpdate({ description: text });
    } else {
      setDraft(task.description);
    }
  };

  const cancelDraft = () => {
    setDraft(task.description);
    setEditing(false);
  };

  const pickDate = () => {
    setShowDate(true);
    setTimeout(() => dateInputRef.current?.showPicker?.(), 0);
  };

  const onDateChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const v = e.target.value;
    setShowDate(false);
    if (v) onUpdate({ due_at: toIsoAtNoon(v) });
  };

  const clearDate = () => {
    onUpdate({ due_at: null });
  };

  const dueClass =
    bucket === "overdue"
      ? "task-due-chip task-due-overdue"
      : bucket === "today"
        ? "task-due-chip task-due-today"
        : bucket === "tomorrow"
          ? "task-due-chip task-due-soon"
          : "task-due-chip";

  return (
    <div
      className={[
        "task-row",
        task.completed ? "task-row-done" : "",
        completing ? "task-row-completing" : "",
        selected ? "task-row-selected" : "",
      ]
        .filter(Boolean)
        .join(" ")}
    >
      <button
        type="button"
        className={[
          "task-check",
          task.completed || completing ? "task-check-on" : "",
          checkboxDisabled ? "task-check-readonly" : "",
        ]
          .filter(Boolean)
          .join(" ")}
        onClick={handleToggle}
        disabled={checkboxDisabled}
        aria-label={
          checkboxDisabled
            ? `Manage in ${task.source_app_name ?? "the source app"}`
            : task.completed
              ? "Mark incomplete"
              : "Mark complete"
        }
        title={
          checkboxDisabled
            ? `Manage in ${task.source_app_name ?? "the source app"}`
            : isIntegration
              ? `Mark done in ${task.source_app_name ?? "source app"}`
              : undefined
        }
      >
        {(task.completed || completing) && (
          <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
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

      <div className="task-body">
        {editing ? (
          <input
            ref={inputRef}
            type="text"
            className="task-edit-input"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onBlur={saveDraft}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                saveDraft();
              } else if (e.key === "Escape") {
                e.preventDefault();
                cancelDraft();
              }
            }}
          />
        ) : onSelect ? (
          // When the page wants a detail panel, hand off the click to it.
          // The panel surfaces edit + open-external + complete affordances,
          // so the row stays a one-click "select me" affordance.
          <button
            type="button"
            className="task-text"
            onClick={onSelect}
            title="Open details"
          >
            {task.description}
          </button>
        ) : isIntegration ? (
          <button
            type="button"
            className="task-text"
            onClick={openExternal}
            title={task.external_url ? `Open in ${task.source_app_name ?? "source app"}` : undefined}
          >
            {task.description}
          </button>
        ) : (
          <button
            type="button"
            className="task-text"
            onClick={() => !task.completed && setEditing(true)}
            title={task.completed ? "" : "Click to edit"}
          >
            {task.description}
          </button>
        )}

        <div className="task-chips">
          <IntegrationBadge task={task} />
          {fresh && <span className="task-chip task-chip-new">New</span>}
          {task.due_at && (
            <button
              type="button"
              className={dueClass}
              onClick={isIntegration ? undefined : pickDate}
              title={isIntegration ? "Due date set in source app" : "Change due date"}
              disabled={isIntegration}
            >
              <Calendar size={11} />
              <span>{dueLabel(task.due_at)}</span>
            </button>
          )}
          {!isIntegration && task.conversation_id && onOpenConversation && (
            <button
              type="button"
              className="task-chip task-chip-link"
              onClick={() => onOpenConversation(task.conversation_id!)}
              title="Open source conversation"
            >
              <Link2 size={11} />
              <span>Conversation</span>
            </button>
          )}
          {isIntegration && task.status_label && (
            <span className="task-chip" title="Status in source app">
              {task.status_label}
            </span>
          )}
        </div>
      </div>

      <div className="task-actions">
        {!isIntegration && !task.due_at && !task.completed && (
          <button
            type="button"
            className="task-action"
            onClick={pickDate}
            aria-label="Add due date"
            title="Add due date"
          >
            <Calendar size={14} />
          </button>
        )}
        {!isIntegration && task.due_at && !task.completed && (
          <button
            type="button"
            className="task-action"
            onClick={clearDate}
            aria-label="Clear due date"
            title="Clear due date"
          >
            <X size={14} />
          </button>
        )}
        {!isIntegration && (
          <button
            type="button"
            className="task-action task-action-danger"
            onClick={onDelete}
            aria-label="Delete task"
            title="Delete"
          >
            <Trash2 size={14} />
          </button>
        )}
      </div>

      {showDate && (
        <input
          ref={dateInputRef}
          type="date"
          className="task-date-hidden"
          defaultValue={toDateInput(task.due_at)}
          onChange={onDateChange}
          onBlur={() => setShowDate(false)}
        />
      )}
    </div>
  );
}
