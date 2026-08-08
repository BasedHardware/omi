import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Task, TaskPatch } from "@omi-core/contracts";
import type { StoreStatus } from "@omi-core/domain";
import type { MessageKey, MessageVariables } from "@omi-core/i18n";
import type { ProductionTaskStore } from "./task-fixtures.js";
import { ProductionChrome } from "./ProductionChrome.js";
import "./tasks.css";

type Translate = <K extends MessageKey>(key: K, vars?: MessageVariables<K>) => string;
type RunOperation = (operation: () => Promise<void>) => Promise<boolean>;
type GroupKey = "today" | "tomorrow" | "later";
const GROUP_KEYS: Record<GroupKey, MessageKey> = {
  today: "tasks.today",
  tomorrow: "tasks.tomorrow",
  later: "tasks.later",
};

export type TasksProductionProps = {
  store: ProductionTaskStore;
  fixture?: string;
  locale?: string | undefined;
  translate: Translate;
  now: number;
  /** Keep fixture screenshots stable; a host may provide its own calendar. */
  calendarDay?: ((timestamp: number) => string) | undefined;
  formatDate?: ((timestamp: number) => string) | undefined;
  onReady?: () => void;
};

function utcCalendarDay(timestamp: number): string {
  return new Date(timestamp).toISOString().slice(0, 10);
}

function localCalendarDay(timestamp: number): string {
  return new Intl.DateTimeFormat(undefined, { year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date(timestamp));
}

function utcDate(timestamp: number): string {
  return new Intl.DateTimeFormat("en-US", { dateStyle: "medium", timeZone: "UTC" }).format(new Date(timestamp));
}

function localDate(timestamp: number): string {
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(new Date(timestamp));
}

function parseDateInput(value: string): number | undefined {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (!match) return undefined;
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const parsed = new Date(year, month - 1, day, 12, 0, 0, 0);
  return parsed.getFullYear() === year && parsed.getMonth() === month - 1 && parsed.getDate() === day
    ? parsed.getTime()
    : undefined;
}

function groupFor(task: Task, now: number, calendarDay: (timestamp: number) => string): GroupKey {
  if (task.dueAt === null) return "later";
  const current = calendarDay(now);
  const due = calendarDay(task.dueAt);
  if (due === current) return "today";
  const tomorrow = calendarDay(now + 86_400_000);
  if (due === tomorrow) return "tomorrow";
  return "later";
}

function phaseLabel(status: StoreStatus, translate: Translate): string | null {
  switch (status.refresh.phase) {
    case "initial-loading": return translate("lifecycle.loading");
    case "refreshing": return translate("lifecycle.refreshing");
    case "saved-but-refresh-failed": return translate("lifecycle.savedFailed");
    case "unavailable": return translate("lifecycle.unavailable");
    default: return null;
  }
}

function groupLabel(group: GroupKey, translate: Translate): string {
  return translate(GROUP_KEYS[group]);
}

function TaskCard({ task, store, translate, formatDate, run, selected, onSelect }: {
  task: Task;
  store: ProductionTaskStore;
  translate: Translate;
  formatDate: (timestamp: number) => string;
  run: RunOperation;
  selected: boolean;
  onSelect: (id: Task["id"]) => void;
}): React.JSX.Element {
  const [draft, setDraft] = useState(task.description);
  const [editing, setEditing] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const isLong = task.description.length > 240;
  const visibleDescription = !expanded && isLong ? `${task.description.slice(0, 240)}…` : task.description;
  useEffect(() => setDraft(task.description), [task.description]);

  const save = (): void => {
    const description = draft.trim();
    setEditing(false);
    if (description && description !== task.description) {
      void run(() => store.patch(task.id, { description } satisfies TaskPatch));
    }
  };

  const indentLevel = Math.max(0, Math.min(3, task.indentLevel));
  const requestDelete = (): void => {
    if (!globalThis.confirm(translate("tasks.deleteConfirm"))) return;
    void run(() => store.delete(task.id));
  };

  return (
    <article className={`task-card is-indent-${indentLevel}${task.completed ? " is-completed" : ""}${selected ? " is-selected" : ""}`} data-task-id={task.id} data-indent-level={indentLevel} onClick={() => onSelect(task.id)}>
      <div className="task-card-main">
        <button
          type="button"
          className="task-check"
          aria-label={task.completed ? translate("tasks.markIncomplete") : translate("tasks.markComplete")}
          aria-pressed={task.completed}
          onClick={() => void run(() => store.patch(task.id, { completed: !task.completed } satisfies TaskPatch))}
        >
          {task.completed ? "✓" : ""}
        </button>
        <div className="task-copy">
          {editing ? (
            <textarea className="task-editor" value={draft} aria-label={translate("common.edit")} onChange={(event) => setDraft(event.target.value)} />
          ) : (
            <p className="task-description">{visibleDescription}</p>
          )}
          <div className="task-meta">
            {task.dueAt === null
              ? <span>{translate("tasks.noDueDate")}</span>
              : <span>{translate("tasks.dueDate", { date: formatDate(task.dueAt) })}</span>}
          </div>
        </div>
      </div>
      <div className="task-actions" aria-label={translate("tasks.details")}>
        <button type="button" onClick={() => setEditing((value) => !value)} aria-label={translate("common.edit")}>
          {editing ? translate("common.cancel") : translate("common.edit")}
        </button>
        {editing && <button type="button" onClick={save}>{translate("common.save")}</button>}
        {isLong && <button type="button" onClick={() => setExpanded((value) => !value)} aria-expanded={expanded}>
          {expanded ? translate("content.showLess") : translate("content.showMore")}
        </button>}
        <button type="button" onClick={requestDelete} aria-label={translate("common.delete")}>
          {translate("common.delete")}
        </button>
      </div>
    </article>
  );
}

export function TasksProduction({ store, fixture, locale = "en", translate, now, calendarDay, formatDate, onReady }: TasksProductionProps): React.JSX.Element {
  const [rows, setRows] = useState<Task[]>([]);
  const [dead, setDead] = useState<Awaited<ReturnType<ProductionTaskStore["deadLetters"]>>>([]);
  const [status, setStatus] = useState(store.status());
  const [draft, setDraft] = useState("");
  const [dueDraft, setDueDraft] = useState("");
  const [selectedTaskId, setSelectedTaskId] = useState<Task["id"] | null>(null);
  const [operationError, setOperationError] = useState<string | null>(null);
  const draftRef = useRef<HTMLTextAreaElement>(null);
  const onReadyRef = useRef(onReady);
  const readyRef = useRef(false);
  useEffect(() => { onReadyRef.current = onReady; }, [onReady]);
  const dayFormatter = calendarDay ?? (fixture ? utcCalendarDay : localCalendarDay);
  const dateFormatter = formatDate ?? (fixture ? utcDate : localDate);

  const reload = useCallback(async (): Promise<void> => {
    try {
      const [nextRows, nextDead] = await Promise.all([store.list(), store.deadLetters()]);
      setRows(nextRows);
      setDead(nextDead);
    } catch {
      setOperationError(translate("lifecycle.error"));
    }
    setStatus(store.status());
  }, [store, translate]);

  const run = useCallback<RunOperation>(async (operation) => {
    setOperationError(null);
    try {
      await operation();
      await reload();
      return true;
    } catch {
      setOperationError(translate("lifecycle.error"));
      setStatus(store.status());
      return false;
    }
  }, [reload, store, translate]);

  useEffect(() => {
    let active = true;
    const unsubscribe = store.subscribe(() => { if (active) void reload(); });
    const boot = async (): Promise<void> => {
      await reload();
      try {
        await store.refresh();
      } catch {
        setOperationError(translate("lifecycle.error"));
        await reload();
      }
      await reload();
      if (active && !readyRef.current) {
        readyRef.current = true;
        onReadyRef.current?.();
      }
    };
    void boot();
    return () => { active = false; unsubscribe(); };
  }, [reload, store, translate]);

  const queueLabel = useMemo(() => {
    const count = status.queue.pendingCount;
    if (!count) return null;
    if (status.queue.phase === "needs-auth") return translate("queue.paused");
    if (status.queue.phase === "retrying") return translate("queue.retrying");
    if (status.queue.phase === "sending") return translate("queue.sending", { count });
    return translate("queue.queuedCount", { count });
  }, [status, translate]);

  const grouped = useMemo(() => {
    const groups: Record<GroupKey, Task[]> = { today: [], tomorrow: [], later: [] };
    for (const task of rows) groups[groupFor(task, now, dayFormatter)].push(task);
    for (const group of Object.values(groups)) {
      group.sort((left, right) => {
        if (left.dueAt === null && right.dueAt !== null) return 1;
        if (left.dueAt !== null && right.dueAt === null) return -1;
        if (left.dueAt !== right.dueAt) return (left.dueAt ?? Number.MAX_SAFE_INTEGER) - (right.dueAt ?? Number.MAX_SAFE_INTEGER);
        return left.description < right.description ? -1 : left.description > right.description ? 1 : 0;
      });
    }
    return groups;
  }, [dayFormatter, now, rows]);

  const add = async (): Promise<void> => {
    const description = draft.trim();
    if (!description) return;
    const dueAt = dueDraft ? parseDateInput(dueDraft) : undefined;
    if (dueDraft && dueAt === undefined) return;
    const submittedDueDraft = dueDraft;
    const succeeded = await run(() => store.create(description, dueAt));
    if (succeeded) {
      setDraft((current) => current.trim() === description ? "" : current);
      setDueDraft((current) => current === submittedDueDraft ? "" : current);
    }
  };

  const notice = phaseLabel(status, translate);
  const groups: GroupKey[] = ["today", "tomorrow", "later"];
  const selectedTask = selectedTaskId ? rows.find((task) => task.id === selectedTaskId) : undefined;

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent): void => {
      const target = event.target;
      if (target instanceof HTMLElement && target.closest("input, textarea, select, button, a, [contenteditable='true']")) return;
      const modifier = event.metaKey || event.ctrlKey;
      if (modifier && event.key.toLowerCase() === "n") {
        event.preventDefault();
        draftRef.current?.focus();
        return;
      }
      if (!selectedTask) return;
      if (modifier && event.key.toLowerCase() === "d") {
        event.preventDefault();
        if (!globalThis.confirm(translate("tasks.deleteConfirm"))) return;
        void run(() => store.delete(selectedTask.id));
        setSelectedTaskId(null);
        return;
      }
      if (event.key === "Tab") {
        event.preventDefault();
        const nextIndent = Math.max(0, Math.min(3, selectedTask.indentLevel + (event.shiftKey ? -1 : 1)));
        if (nextIndent !== selectedTask.indentLevel) {
          void run(() => store.patch(selectedTask.id, { indentLevel: nextIndent } satisfies TaskPatch));
        }
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [run, selectedTask, store, translate]);

  return (
    <main className="production-shell tasks-production-shell" data-production-shell="true" data-route="tasks" data-surface-state={status.refresh.phase} data-qa-fixture={fixture ?? "none"}>
      <ProductionChrome locale={locale} active="tasks" placement="top" />
      <header className="tasks-header">
        <div>
          <p className="tasks-eyebrow">{translate("tasks.title")}</p>
          <h1>{translate("tasks.title")}</h1>
          <p>{translate("tasks.subtitle")}</p>
        </div>
        {status.refresh.phase !== "ready" && <button type="button" onClick={() => void run(() => store.refresh())} aria-label={translate("common.retry")}>{translate("common.retry")}</button>}
      </header>
      {fixture && <p className="tasks-fixture-label">{translate("qa.fixtureLabel", { name: translate("qa.syntheticData"), fixture })}</p>}
      {notice && <div className={`tasks-status-notice ${status.refresh.phase}`} role="status">{notice}</div>}
      {queueLabel && <div className={`tasks-queue-notice ${status.queue.phase}`} role="status">{queueLabel}</div>}
      {operationError && <div className="tasks-operation-error" role="alert">{operationError}</div>}
      <section className="tasks-create" aria-label={translate("tasks.newTask")}>
        <textarea ref={draftRef} value={draft} onChange={(event) => setDraft(event.target.value)} placeholder={translate("tasks.newTask")} aria-label={translate("tasks.newTask")} />
        <label>
          <span>{translate("tasks.dueDateLabel")}</span>
          <input type="date" value={dueDraft} onChange={(event) => setDueDraft(event.target.value)} aria-label={translate("tasks.dueDateLabel")} />
        </label>
        <button type="button" onClick={() => void add()} disabled={!draft.trim()}>{translate("tasks.add")}</button>
      </section>
      <div className="tasks-shortcuts" aria-label={translate("tasks.shortcuts")}>
        <span>{translate("tasks.shortcuts")}</span>
        <span><kbd>{translate("tasks.keyNew")}</kbd> {translate("tasks.shortcutNew")}</span>
        <span><kbd>{translate("tasks.keyDelete")}</kbd> {translate("tasks.shortcutDelete")}</span>
        <span><kbd>{translate("tasks.keyIndent")}</kbd> {translate("tasks.shortcutIndent")}</span>
        <span><kbd>{translate("tasks.keyOutdent")}</kbd> {translate("tasks.shortcutOutdent")}</span>
      </div>
      {status.refresh.phase === "initial-loading" ? (
        <p className="tasks-empty-state">{translate("common.loading")}</p>
      ) : status.refresh.phase === "ready" && rows.length === 0 ? (
        <div className="tasks-empty-state"><strong>{translate("tasks.emptyTitle")}</strong><p>{translate("tasks.emptyBody")}</p></div>
      ) : status.refresh.phase === "unavailable" && rows.length === 0 ? (
        <p className="tasks-empty-state">{translate("lifecycle.unavailable")}</p>
      ) : (
        <section className="tasks-groups" aria-label={translate("tasks.title")}>
          {groups.map((group) => (
            <section className={`tasks-group tasks-group-${group}`} key={group} aria-labelledby={`tasks-heading-${group}`}>
              <h2 id={`tasks-heading-${group}`}>{groupLabel(group, translate)}</h2>
              {grouped[group].length === 0 ? <p className="tasks-group-empty">{translate("lifecycle.empty")}</p> : grouped[group].map((task) => (
                <TaskCard key={task.id} task={task} store={store} translate={translate} formatDate={dateFormatter} run={run} selected={task.id === selectedTaskId} onSelect={setSelectedTaskId} />
              ))}
            </section>
          ))}
        </section>
      )}
      {dead.length > 0 && <section className="tasks-dead-panel" aria-labelledby="tasks-dead-heading">
          <h2 id="tasks-dead-heading">{translate("dead.title")}</h2>
        <p>{translate("dead.body")}</p>
          {dead.map((letter) => <div className="tasks-dead-row" key={letter.opId}>
          <span>{translate("queue.pending")}</span>
          <button type="button" onClick={() => void run(() => store.discardDeadLetter(letter.opId))}>{translate("dead.remove")}</button>
        </div>)}
      </section>}
      <button type="button" className="tasks-mobile-fab" onClick={() => draftRef.current?.focus()} aria-label={translate("tasks.add")}>+</button>
      <ProductionChrome locale={locale} active="tasks" placement="bottom" />
    </main>
  );
}
