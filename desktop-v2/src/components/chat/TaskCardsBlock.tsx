import { Layers, Triangle } from "lucide-react";
import { open as openShell } from "@tauri-apps/plugin-shell";
import { Suggestion, Suggestions } from "../ai-elements/suggestion";
import { cn } from "../../lib/utils";
import type { ChatTaskCard, ChatMessagePart } from "../../stores/chatStore";

type Part = Extract<ChatMessagePart, { type: "task_cards" }>;

const SOURCE_ICON: Record<string, typeof Layers> = {
  Jira: Layers,
  Linear: Triangle,
};

const STATUS_TYPE_DOT: Record<string, string> = {
  todo: "bg-muted-foreground/40",
  in_progress: "bg-amber-400",
  done: "bg-emerald-400",
  canceled: "bg-rose-400",
};

const TITLE_TRUNCATE = 60;

function trimTitle(s: string): string {
  if (!s) return "";
  return s.length > TITLE_TRUNCATE ? s.slice(0, TITLE_TRUNCATE - 1).trimEnd() + "…" : s;
}

/** Compact horizontal-scroll strip of ticket pills, built on `ai-elements`'s
 *  `Suggestions` (matches the prompt-area suggestion pills). One pill per
 *  ticket: status dot + key + truncated title, click to open in source. */
export function TaskCardsBlock({ part }: { part: Part }) {
  if (!part.tasks || part.tasks.length === 0) return null;
  const SourceIcon = SOURCE_ICON[part.appName] ?? Layers;

  return (
    <div className="not-prose my-2 -mx-1 space-y-1">
      <div className="flex items-center gap-1.5 px-1 text-[11px] text-muted-foreground">
        {part.appImage ? (
          <img src={part.appImage} alt="" className="size-3 rounded-sm" aria-hidden />
        ) : (
          <SourceIcon className="size-3" />
        )}
        <span>
          {part.tasks.length} {part.tasks.length === 1 ? "ticket" : "tickets"} from {part.appName}
        </span>
      </div>
      <Suggestions className="px-1">
        {part.tasks.map((t) => (
          <TicketPill key={`${t.external_id}-${t.title}`} task={t} />
        ))}
      </Suggestions>
    </div>
  );
}

function TicketPill({ task }: { task: ChatTaskCard }) {
  const dotClass = STATUS_TYPE_DOT[task.status_type ?? "todo"] ?? STATUS_TYPE_DOT.todo;
  const display = `${task.external_id}${task.title ? ` — ${trimTitle(task.title)}` : ""}`;
  const tooltip = [
    task.title,
    task.status,
    task.assignee && `Assigned: ${task.assignee}`,
    task.priority && `Priority: ${task.priority}`,
  ]
    .filter(Boolean)
    .join("\n");

  return (
    <Suggestion
      suggestion={display}
      title={tooltip}
      onClick={() => {
        if (task.url) void openShell(task.url).catch(() => {});
      }}
      className={cn(
        "h-7 max-w-[24rem] gap-1.5 truncate text-[12px] font-normal",
        !task.url && "cursor-default",
      )}
    >
      <span
        className={cn("inline-block size-1.5 shrink-0 rounded-full", dotClass)}
        aria-hidden
      />
      <span className="truncate">{display}</span>
    </Suggestion>
  );
}
