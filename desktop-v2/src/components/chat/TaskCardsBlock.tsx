import { ArrowUpRight, Calendar, Layers, Triangle } from "lucide-react";
import { open as openShell } from "@tauri-apps/plugin-shell";
import { Card, CardContent, CardDescription, CardTitle } from "../ui/card";
import { ScrollArea, ScrollBar } from "../ui/scroll-area";
import { cn } from "../../lib/utils";
import type { ChatTaskCard, ChatMessagePart } from "../../stores/chatStore";
import { dueLabel } from "../tasks/taskDates";

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

/** Renders structured `data.tasks[]` from a plugin's `list_my_issues` (or
 *  similar) chat tool as horizontally-scrollable cards. Mirrors the look of
 *  the existing `RichList` component but knows about ticket-specific fields
 *  (key, status, due, assignee, priority). */
export function TaskCardsBlock({ part }: { part: Part }) {
  if (!part.tasks || part.tasks.length === 0) return null;
  const SourceIcon = SOURCE_ICON[part.appName] ?? Layers;

  return (
    <div className="not-prose my-3 -mx-1 space-y-1.5">
      <div className="flex items-center gap-1.5 px-1 text-xs text-muted-foreground">
        {part.appImage ? (
          <img src={part.appImage} alt="" className="size-3.5 rounded-sm" aria-hidden />
        ) : (
          <SourceIcon className="size-3.5" />
        )}
        <span>
          {part.tasks.length} {part.tasks.length === 1 ? "ticket" : "tickets"} from {part.appName}
        </span>
      </div>
      <ScrollArea className="w-full whitespace-nowrap">
        <div className="flex gap-3 px-1 pb-3">
          {part.tasks.map((t) => (
            <TaskCardItem key={`${t.external_id}-${t.title}`} task={t} sourceLabel={part.appName} />
          ))}
        </div>
        <ScrollBar orientation="horizontal" />
      </ScrollArea>
    </div>
  );
}

function TaskCardItem({ task, sourceLabel }: { task: ChatTaskCard; sourceLabel: string }) {
  const interactive = !!task.url;
  const onClick = () => {
    if (task.url) void openShell(task.url).catch(() => {});
  };
  const dotClass = STATUS_TYPE_DOT[task.status_type ?? "todo"] ?? STATUS_TYPE_DOT.todo;

  return (
    <Card
      role={interactive ? "button" : undefined}
      tabIndex={interactive ? 0 : undefined}
      onClick={interactive ? onClick : undefined}
      onKeyDown={
        interactive
          ? (e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onClick();
              }
            }
          : undefined
      }
      className={cn(
        "group relative w-[300px] shrink-0 gap-0 overflow-hidden p-0 transition-all",
        interactive &&
          "cursor-pointer hover:border-ring focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px] focus-visible:outline-none",
      )}
    >
      <CardContent className="space-y-2 whitespace-normal p-4">
        <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
          <span className={cn("inline-block size-1.5 rounded-full", dotClass)} aria-hidden />
          <span className="font-mono uppercase tracking-tight">{task.external_id}</span>
          {task.project && (
            <>
              <span className="text-muted-foreground/50">·</span>
              <span>{task.project}</span>
            </>
          )}
          {task.status && (
            <>
              <span className="text-muted-foreground/50">·</span>
              <span>{task.status}</span>
            </>
          )}
        </div>
        <CardTitle className="text-sm leading-snug line-clamp-3">{task.title}</CardTitle>
        {(task.due_at || task.assignee || task.priority) && (
          <CardDescription className="flex flex-wrap gap-x-3 gap-y-1 text-[11px]">
            {task.due_at && (
              <span className="inline-flex items-center gap-1">
                <Calendar size={10} /> {dueLabel(task.due_at)}
              </span>
            )}
            {task.priority && <span>{task.priority}</span>}
            {task.assignee && <span>{task.assignee}</span>}
          </CardDescription>
        )}
      </CardContent>
      {interactive && (
        <span className="absolute right-2 top-2 flex size-6 items-center justify-center rounded-full border bg-background/80 text-muted-foreground backdrop-blur-sm transition-colors group-hover:border-ring group-hover:text-foreground">
          <ArrowUpRight className="size-3" />
        </span>
      )}
      <span className="sr-only">Open {task.external_id} in {sourceLabel}</span>
    </Card>
  );
}
