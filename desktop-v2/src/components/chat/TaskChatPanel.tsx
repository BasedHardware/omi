/**
 * TaskChatPanel — inline panel that appears beneath an assistant message
 * when the user clicks "Save as task". Pre-fills the description from the
 * surrounding chat context so the user can confirm, edit, optionally pick
 * a due date, and save.
 *
 * The actual task creation is delegated to taskStore.createTask.
 */

import { useMemo, useState } from "react";
import { format } from "date-fns";
import {
  CalendarIcon,
  CheckCircle2,
  Loader2,
  Target,
  X,
} from "lucide-react";
import { useTaskStore } from "@/stores/taskStore";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { Calendar } from "@/components/ui/calendar";
import { cn } from "@/lib/utils";

export interface TaskChatPanelProps {
  /** Suggested task description derived from the assistant response. */
  suggestion: string;
  /** Optional link back to the underlying chat message id. */
  sourceMessageId?: string;
  onClose: () => void;
}

export function TaskChatPanel({ suggestion, sourceMessageId, onClose }: TaskChatPanelProps) {
  const createTask = useTaskStore((s) => s.createTask);

  const initial = useMemo(() => suggestion.trim().slice(0, 280), [suggestion]);
  const [description, setDescription] = useState(initial);
  const [dueDate, setDueDate] = useState<Date | undefined>(undefined);
  const [isSaving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const canSave = description.trim().length > 0 && !isSaving && !saved;

  const handleSave = async () => {
    if (!canSave) return;
    setSaving(true);
    setError(null);
    try {
      const text = dueDate
        ? `${description.trim()} (due ${format(dueDate, "MMM d, yyyy")})`
        : description.trim();
      await createTask(text);
      setSaved(true);
      // Auto-dismiss after a short confirmation delay.
      window.setTimeout(onClose, 900);
    } catch (err) {
      console.error("[TaskChatPanel] createTask failed", err);
      setError(err instanceof Error ? err.message : "Failed to save task");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="task-chat-panel" data-source-message-id={sourceMessageId}>
      <div className="task-chat-panel__header">
        <div className="task-chat-panel__title">
          <Target className="size-3.5" aria-hidden="true" />
          <span>Save as task</span>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="task-chat-panel__close"
          aria-label="Close task panel"
        >
          <X className="size-3" />
        </button>
      </div>

      <Textarea
        value={description}
        onChange={(e) => setDescription(e.target.value)}
        placeholder="Describe the task..."
        className="task-chat-panel__textarea"
        rows={3}
        disabled={isSaving || saved}
      />

      <div className="task-chat-panel__row">
        <Popover>
          <PopoverTrigger asChild>
            <Button
              type="button"
              variant={dueDate ? "secondary" : "outline"}
              size="sm"
              className={cn("gap-1.5 text-xs font-normal", dueDate && "pr-1.5")}
              disabled={isSaving || saved}
            >
              <CalendarIcon className="size-3" />
              {dueDate ? format(dueDate, "MMM d, yyyy") : "Add due date"}
              {dueDate && (
                <span
                  role="button"
                  className="ml-0.5 flex size-4 items-center justify-center rounded-sm hover:bg-muted-foreground/20"
                  onClick={(e) => {
                    e.stopPropagation();
                    setDueDate(undefined);
                  }}
                >
                  <X className="size-2.5" />
                </span>
              )}
            </Button>
          </PopoverTrigger>
          <PopoverContent className="w-auto p-0" align="start">
            <Calendar
              mode="single"
              selected={dueDate}
              onSelect={(d) => setDueDate(d)}
              disabled={{ before: new Date(new Date().setHours(0, 0, 0, 0)) }}
            />
          </PopoverContent>
        </Popover>

        <div className="task-chat-panel__actions">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={onClose}
            disabled={isSaving}
          >
            Cancel
          </Button>
          <Button
            type="button"
            variant="default"
            size="sm"
            onClick={handleSave}
            disabled={!canSave}
          >
            {isSaving ? (
              <Loader2 className="size-3.5 animate-spin" />
            ) : saved ? (
              <CheckCircle2 className="size-3.5" />
            ) : null}
            {saved ? "Saved" : isSaving ? "Saving…" : "Save task"}
          </Button>
        </div>
      </div>

      {error && <div className="task-chat-panel__error">{error}</div>}
    </div>
  );
}
