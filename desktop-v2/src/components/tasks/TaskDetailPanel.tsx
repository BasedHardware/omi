import { useEffect } from "react";
import { open as openShell } from "@tauri-apps/plugin-shell";
import {
  Calendar,
  CheckCircle2,
  ExternalLink,
  Flag,
  FolderKanban,
  Layers,
  Link2,
  Triangle,
  User,
  X,
} from "lucide-react";
import type { Task } from "../../stores/taskStore";
import { dueLabel } from "./taskDates";

interface Props {
  task: Task;
  onClose: () => void;
  onToggle: () => void;
  onOpenConversation?: (conversationId: string) => void;
}

const SOURCE_ICON: Record<string, typeof ExternalLink> = {
  jira: Layers,
  linear: Triangle,
};

const SOURCE_LABEL: Record<string, string> = {
  jira: "Jira",
  linear: "Linear",
};

const STATUS_BADGE: Record<string, string> = {
  todo: "bg-muted text-muted-foreground",
  in_progress: "bg-amber-500/15 text-amber-300",
  done: "bg-emerald-500/15 text-emerald-300",
  canceled: "bg-rose-500/15 text-rose-300",
};

/** Side panel that surfaces task metadata in-place — clicking a row in the
 *  Plan list opens this instead of navigating away or popping the source
 *  ticket. Integration tasks get an "Open in {source}" button so users can
 *  jump out only when they actually need to. */
export function TaskDetailPanel({ task, onClose, onToggle, onOpenConversation }: Props) {
  // Esc closes — feels native for an inline drawer and keeps keyboard users
  // from getting trapped when they accidentally select a task.
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose]);

  const isIntegration = !!task.source && task.source !== "native";
  const SourceIcon = isIntegration ? (SOURCE_ICON[task.source!] ?? ExternalLink) : null;
  const sourceLabel = isIntegration
    ? (SOURCE_LABEL[task.source!] ?? task.source_app_name ?? task.source!)
    : "Nooto";

  const handleOpenExternal = () => {
    if (!task.external_url) return;
    void openShell(task.external_url).catch((err) =>
      console.warn("[TaskDetailPanel] open external failed:", err),
    );
  };

  return (
    <aside className="task-detail-panel">
      <header className="task-detail-header">
        <div className="task-detail-source">
          {SourceIcon && <SourceIcon size={13} />}
          <span>{sourceLabel}</span>
          {task.external_id && (
            <>
              <span className="text-muted-foreground/60">·</span>
              <span className="font-mono text-[11px]">{task.external_id}</span>
            </>
          )}
        </div>
        <button
          type="button"
          className="task-detail-close"
          onClick={onClose}
          aria-label="Close details"
        >
          <X size={14} />
        </button>
      </header>

      <h2 className="task-detail-title">{task.description}</h2>

      <div className="task-detail-meta">
        {task.status_label && (
          <span
            className={`task-chip ${
              STATUS_BADGE[task.status_type ?? "todo"] ?? STATUS_BADGE.todo
            }`}
          >
            {task.status_label}
          </span>
        )}
        {task.due_at && (
          <span className="task-chip">
            <Calendar size={11} /> {dueLabel(task.due_at)}
          </span>
        )}
        {task.priority && (
          <span className="task-chip">
            <Flag size={11} /> {task.priority}
          </span>
        )}
        {task.project && (
          <span className="task-chip">
            <FolderKanban size={11} /> {task.project}
          </span>
        )}
        {task.source_app_name && task.source_app_image && (
          <img
            src={task.source_app_image}
            alt=""
            className="size-4 rounded"
            aria-hidden
          />
        )}
      </div>

      <dl className="task-detail-fields">
        {!isIntegration && task.completed && (
          <div className="task-detail-field">
            <dt>
              <CheckCircle2 size={12} /> Status
            </dt>
            <dd>Completed{task.completed_at ? ` · ${dueLabel(task.completed_at)}` : ""}</dd>
          </div>
        )}
        {task.assignee && (
          <div className="task-detail-field">
            <dt>
              <User size={12} /> Assignee
            </dt>
            <dd>{task.assignee}</dd>
          </div>
        )}
        {task.updated_at && (
          <div className="task-detail-field">
            <dt>Last updated</dt>
            <dd>{dueLabel(task.updated_at)}</dd>
          </div>
        )}
      </dl>

      <div className="task-detail-actions">
        {!isIntegration ? (
          <button
            type="button"
            className="task-detail-action"
            onClick={onToggle}
          >
            <CheckCircle2 size={13} />
            {task.completed ? "Mark incomplete" : "Mark complete"}
          </button>
        ) : task.external_url ? (
          <button
            type="button"
            className="task-detail-action"
            onClick={handleOpenExternal}
            title={`Open this ticket in ${sourceLabel}`}
          >
            <ExternalLink size={13} />
            Open in {sourceLabel}
          </button>
        ) : null}
        {!isIntegration && task.conversation_id && onOpenConversation && (
          <button
            type="button"
            className="task-detail-action"
            onClick={() => onOpenConversation(task.conversation_id!)}
          >
            <Link2 size={13} />
            Open conversation
          </button>
        )}
      </div>
    </aside>
  );
}
