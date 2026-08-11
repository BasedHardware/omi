import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Task, TaskPatch } from "@omi-core/contracts";
import type { MessageKey, MessageVariables } from "@omi-core/i18n";
import type { ProductionTaskStore } from "./ProductionStores.js";
import { deadLetterView } from "./dead-letter-presentation.js";
import { ProductionChrome } from "./ProductionChrome.js";
import { ProductionDataSourceBadge, ProductionEmptyState, ProductionLifecycleRegion, ProductionLiveAnnouncement, ProductionPageHeader, ProductionSearchField, type SurfaceDataSource } from "./ProductionPrimitives.js";
import { ProductionIcon } from "./ProductionIcon.js";
import { tasksEmptyKind } from "./tasks-presentation.js";
import "./tasks.css";

type Translate = <K extends MessageKey>(key: K, vars?: MessageVariables<K>) => string;
type RunOperation = (operation: () => Promise<void>) => Promise<boolean>;
type GroupKey = "overdue" | "today" | "tomorrow" | "later" | "noDeadline";
const GROUP_KEYS: Record<GroupKey, MessageKey> = {
  overdue: "tasks.overdue",
  today: "tasks.today",
  tomorrow: "tasks.tomorrow",
  later: "tasks.later",
  noDeadline: "tasks.noDeadline",
};
const TASK_EMPTY_ICON = "tasks" as const;

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

function dateInputValue(timestamp: number | null): string {
  if (timestamp === null) return "";
  const date = new Date(timestamp);
  const year = String(date.getFullYear()).padStart(4, "0");
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function groupFor(task: Task, now: number, calendarDay: (timestamp: number) => string): GroupKey {
  if (task.dueAt === null) return "noDeadline";
  if (task.dueAt < now) return "overdue";
  const current = calendarDay(now);
  const due = calendarDay(task.dueAt);
  if (due === current) return "today";
  const tomorrow = calendarDay(now + 86_400_000);
  if (due === tomorrow) return "tomorrow";
  return "later";
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
  const [dueDraft, setDueDraft] = useState(dateInputValue(task.dueAt));
  const [editing, setEditing] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const isLong = task.description.length > 240;
  const visibleDescription = !expanded && isLong ? `${task.description.slice(0, 240)}…` : task.description;
  useEffect(() => {
    setDraft(task.description);
    setDueDraft(dateInputValue(task.dueAt));
  }, [task.description, task.dueAt]);

  const save = async (): Promise<void> => {
    const description = draft.trim();
    const dueAt = dueDraft ? parseDateInput(dueDraft) : null;
    if (!description || dueAt === undefined) return;
    const patch: TaskPatch = {};
    if (description !== task.description) patch.description = description;
    if (dueAt !== task.dueAt) patch.dueAt = dueAt;
    if (Object.keys(patch).length > 0 && !(await run(() => store.patch(task.id, patch)))) return;
    setEditing(false);
  };

  const cancelEdit = (): void => {
    setDraft(task.description);
    setDueDraft(dateInputValue(task.dueAt));
    setEditing(false);
  };

  const indentLevel = Math.max(0, Math.min(3, task.indentLevel));
  const requestDelete = (): void => {
    if (!globalThis.confirm(translate("tasks.deleteConfirm"))) return;
    void run(() => store.delete(task.id));
  };

  return (
    <article
      className={`task-card is-indent-${indentLevel}${task.completed ? " is-completed" : ""}${selected ? " is-selected" : ""}`}
      data-task-id={task.id}
      data-indent-level={indentLevel}
      tabIndex={0}
      onClick={() => onSelect(task.id)}
      onFocus={() => onSelect(task.id)}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onSelect(task.id);
        }
      }}
    >
      <div className="task-card-main">
        <button
          type="button"
          className="task-check"
          aria-label={task.completed ? translate("tasks.markIncomplete") : translate("tasks.markComplete")}
          aria-pressed={task.completed}
          onClick={(event) => {
            event.stopPropagation();
            void run(() => store.patch(task.id, { completed: !task.completed } satisfies TaskPatch));
          }}
        >
          {task.completed ? "✓" : ""}
        </button>
        <div className="task-copy">
          {editing ? (
            <div className="task-edit-fields">
              <textarea className="task-editor" value={draft} aria-label={translate("common.edit")} onChange={(event) => setDraft(event.target.value)} />
              <label>
                <span>{translate("tasks.dueDateLabel")}</span>
                <input type="date" value={dueDraft} onChange={(event) => setDueDraft(event.target.value)} aria-label={translate("tasks.dueDateLabel")} />
                <small className="task-date-hint">{translate("tasks.dueDateHint")}</small>
              </label>
            </div>
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
      <div className="task-actions" role="group" aria-label={translate("tasks.details")} onClick={(event) => event.stopPropagation()}>
        {editing ? <button type="button" onClick={cancelEdit}>{translate("common.cancel")}</button> :
          <button type="button" onClick={() => setEditing(true)} aria-label={translate("common.edit")}>{translate("common.edit")}</button>}
        {editing && <button type="button" onClick={() => void save()} disabled={!draft.trim()}>{translate("common.save")}</button>}
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
  const [createOpen, setCreateOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [selectedTaskId, setSelectedTaskId] = useState<Task["id"] | null>(null);
  const [operationError, setOperationError] = useState<string | null>(null);
  const draftRef = useRef<HTMLTextAreaElement>(null);
  const shellRef = useRef<HTMLElement>(null);
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

  const grouped = useMemo(() => {
    const groups: Record<GroupKey, Task[]> = { overdue: [], today: [], tomorrow: [], later: [], noDeadline: [] };
    const needle = query.trim().toLocaleLowerCase(locale);
    for (const task of rows) {
      if (!needle || task.description.toLocaleLowerCase(locale).includes(needle)) groups[groupFor(task, now, dayFormatter)].push(task);
    }
    for (const group of Object.values(groups)) {
      group.sort((left, right) => {
        if (left.dueAt === null && right.dueAt !== null) return 1;
        if (left.dueAt !== null && right.dueAt === null) return -1;
        if (left.dueAt !== right.dueAt) return (left.dueAt ?? Number.MAX_SAFE_INTEGER) - (right.dueAt ?? Number.MAX_SAFE_INTEGER);
        return left.description < right.description ? -1 : left.description > right.description ? 1 : 0;
      });
    }
    return groups;
  }, [dayFormatter, locale, now, query, rows]);

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
      setCreateOpen(false);
    }
  };

  const groups: GroupKey[] = ["overdue", "today", "tomorrow", "later", "noDeadline"];
  const selectedTask = selectedTaskId ? rows.find((task) => task.id === selectedTaskId) : undefined;
  const filtering = query.trim().length > 0;
  const visibleCount = groups.reduce((count, group) => count + grouped[group].length, 0);
  const emptyKind = tasksEmptyKind({
    phase: status.refresh.phase,
    rowCount: rows.length,
    visibleCount,
    filtering,
  });
  const source = (fixture
    ? { kind: "fixture", fixture }
    : { kind: "live", origin: "bridge" }) satisfies SurfaceDataSource;

  const openCreate = (): void => {
    setCreateOpen(true);
    requestAnimationFrame(() => draftRef.current?.focus());
  };
  const navigateTask = (event?: KeyboardEvent): void => {
    if (!selectedTask || !event) return;
    const cards = Array.from(shellRef.current?.querySelectorAll<HTMLElement>(".task-card") ?? []);
    const current = cards.findIndex((card) => card.dataset["taskId"] === selectedTask.id);
    const next = event.key === "ArrowDown" ? Math.min(cards.length - 1, current + 1) : Math.max(0, current - 1);
    cards[next]?.focus();
  };
  const deleteTask = (): void => {
    if (!selectedTask || !globalThis.confirm(translate("tasks.deleteConfirm"))) return;
    void (async () => {
      if (await run(() => store.delete(selectedTask.id))) setSelectedTaskId(null);
    })();
  };
  const indentTask = (event?: KeyboardEvent): void => {
    if (!selectedTask || !event) return;
    const nextIndent = Math.max(0, Math.min(3, selectedTask.indentLevel + (event.key === "[" ? -1 : 1)));
    if (nextIndent !== selectedTask.indentLevel) void run(() => store.patch(selectedTask.id, { indentLevel: nextIndent } satisfies TaskPatch));
  };

  return (
    <main ref={shellRef} className="production-shell tasks-production-shell" data-production-shell="true" data-route="tasks" data-surface-state={status.refresh.phase} data-qa-fixture={fixture ?? "none"} data-consumer-semantic={`tasks:visible:${visibleCount}:total:${rows.length}`}>
      <ProductionChrome locale={locale} active="tasks" placement="top" commandHandlers={{
        "new-task": openCreate,
        "navigate-task": navigateTask,
        "delete-task": deleteTask,
        "indent-task": indentTask,
        "outdent-task": indentTask,
      }} commandEnabled={{
        "navigate-task": Boolean(selectedTask),
        "delete-task": Boolean(selectedTask),
        "indent-task": Boolean(selectedTask),
        "outdent-task": Boolean(selectedTask),
      }} />
      <section className="desktop-page-panel">
      <ProductionPageHeader className="tasks-header" eyebrow={translate("tasks.title")} title={translate("tasks.title")} description={translate("tasks.subtitle")} actions={<div className="tasks-header-actions">
          <ProductionSearchField className="tasks-search" label={translate("tasks.filterSavedPlaceholder")} placeholder={translate("tasks.filterSavedPlaceholder")} value={query} onValueChange={setQuery} />
          <button className="tasks-add-trigger" type="button" aria-expanded={createOpen} aria-label={createOpen ? translate("common.cancel") : translate("tasks.newTask")} onClick={() => { setCreateOpen((open) => !open); if (!createOpen) requestAnimationFrame(() => draftRef.current?.focus()); }}><ProductionIcon name={createOpen ? "close" : "plus"} /></button>
          <button className="tasks-settings-trigger" type="button" disabled aria-label={translate("nav.settings")}><ProductionIcon name="more" /></button>
        </div>} />
      <ProductionDataSourceBadge source={source} locale={locale} />
      <ProductionLifecycleRegion
        className="surface-notices"
        phase={status.refresh.phase}
        hasSavedData={status.refresh.hasSavedData}
        locale={locale}
        queue={status.queue}
        deadLetterCount={dead.length}
        operationError={operationError}
        nextAction={status.refresh.phase !== "ready" ? translate("common.retry") : null}
        retry={status.refresh.phase !== "ready" ? { onRetry: async () => { await run(() => store.refresh()); } } : null}
      />
      <section className={`tasks-create${createOpen ? " is-open" : ""}`} aria-label={translate("tasks.newTask")}>
        <textarea ref={draftRef} value={draft} onChange={(event) => setDraft(event.target.value)} onKeyDown={(event) => {
          if (event.key === "Escape") {
            setCreateOpen(false);
            event.currentTarget.blur();
          }
        }} placeholder={translate("tasks.newTask")} aria-label={translate("tasks.newTask")} />
        <label>
          <span>{translate("tasks.dueDateLabel")}</span>
          <input type="date" value={dueDraft} onChange={(event) => setDueDraft(event.target.value)} aria-label={translate("tasks.dueDateLabel")} />
          <small className="task-date-hint">{translate("tasks.dueDateHint")}</small>
        </label>
        <button type="button" onClick={() => void add()} disabled={!draft.trim()}>{translate("tasks.add")}</button>
        <button type="button" className="tasks-create-cancel" onClick={() => setCreateOpen(false)}>{translate("common.cancel")}</button>
      </section>
      <div className="tasks-shortcuts" aria-label={translate("tasks.shortcuts")}>
        <span>{translate("tasks.shortcuts")}</span>
        <span><kbd>{translate("tasks.keyNavigate")}</kbd> {translate("tasks.shortcutNavigate")}</span>
        <span><kbd>{translate("tasks.keyNew")}</kbd> {translate("tasks.shortcutNew")}</span>
        <span><kbd>{translate("tasks.keyDelete")}</kbd> {translate("tasks.shortcutDelete")}</span>
        <span><kbd>{translate("tasks.keyIndent")}</kbd> {translate("tasks.shortcutIndent")}</span>
        <span><kbd>{translate("tasks.keyOutdent")}</kbd> {translate("tasks.shortcutOutdent")}</span>
      </div>
      {status.refresh.phase === "initial-loading" ? (
        <p className="tasks-empty-state">{translate("common.loading")}</p>
      ) : status.refresh.phase === "ready" && rows.length === 0 ? (
        <div data-empty-kind="empty-projection">
          <ProductionEmptyState
            icon={TASK_EMPTY_ICON}
            title={translate("tasks.emptyTitle")}
            detail={translate("tasks.emptyBody")}
            action={<button type="button" onClick={openCreate}>{translate("tasks.newTask")}</button>}
          />
        </div>
      ) : status.refresh.phase === "unavailable" && rows.length === 0 ? (
        <p className="tasks-empty-state">{translate("lifecycle.unavailable")}</p>
      ) : emptyKind === "filtered-out" ? (
        <p className="tasks-empty-state" data-empty-kind="filtered-out">{translate("common.noResults")}</p>
      ) : (
        <section className="tasks-groups" aria-label={translate("tasks.title")}>
          {groups.filter((group) => grouped[group].length > 0).map((group) => (
            <section className={`tasks-group tasks-group-${group}`} key={group} aria-labelledby={`tasks-heading-${group}`}>
              <div className="tasks-group-heading">
                <ProductionIcon name={group === "noDeadline" ? "history" : "calendar"} size={18} />
                <h2 id={`tasks-heading-${group}`}>{groupLabel(group, translate)}</h2>
                <span className="tasks-group-count">{grouped[group].length}</span>
              </div>
              {grouped[group].map((task) => (
                <TaskCard key={task.id} task={task} store={store} translate={translate} formatDate={dateFormatter} run={run} selected={task.id === selectedTaskId} onSelect={setSelectedTaskId} />
              ))}
            </section>
          ))}
        </section>
      )}
      <ProductionLiveAnnouncement message={translate("lifecycle.resultsCount", { count: visibleCount })} />
      {dead.length > 0 && <section className="tasks-dead-panel" aria-labelledby="tasks-dead-heading">
          <h2 id="tasks-dead-heading">{translate("dead.title")}</h2>
          {dead.map(deadLetterView).map((view) => <div className="tasks-dead-row" key={view.opId}>
          <span>{translate(view.messageKey)}</span>
          {/* "Your edit is saved below" is only true if it is. The view hands
              back a saved edit exactly when the message promises one. */}
          {view.savedEdit !== null && <pre className="tasks-dead-payload">{view.savedEdit}</pre>}
          {/* DISCARD ONLY. Not an oversight and not a gap to fill: a retry
              here resubmits an envelope stamped with a superseded epoch, which
              the fence refuses forever. See dead-letter-presentation.ts. */}
          <button type="button" onClick={() => void run(() => store.discardDeadLetter(view.opId))}>{translate("dead.remove")}</button>
        </div>)}
      </section>}
      <button type="button" className="tasks-mobile-fab" aria-expanded={createOpen} onClick={() => {
        setCreateOpen(true);
        requestAnimationFrame(() => draftRef.current?.focus());
      }} aria-label={translate("tasks.add")}><ProductionIcon name="plus" /></button>
      </section>
      <ProductionChrome locale={locale} active="tasks" placement="bottom" />
    </main>
  );
}
