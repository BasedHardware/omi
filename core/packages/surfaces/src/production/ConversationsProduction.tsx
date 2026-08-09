import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Conversation, Folder } from "@omi-core/contracts";
import { formatDate, formatDuration, t } from "@omi-core/i18n";
import type { StoreStatus } from "@omi-core/domain";
import { CONVERSATION_FIXED_NOW, type ConversationFixtureState } from "./conversation-fixtures.js";
import type { ProductionConversationStore, ProductionFolderStore } from "./ProductionStores.js";
import { deadLetterView } from "./dead-letter-presentation.js";
import { refreshPhaseNoticeKey } from "./lifecycle-presentation.js";
import { ProductionChrome, ProductionLibrarySegment } from "./ProductionChrome.js";
import { ProductionFilterChips, ProductionSearchField, type ProductionFilterOption } from "./ProductionPrimitives.js";
import "./conversations.css";

type Locale = string;
type RunOperation = (operation: () => Promise<void>) => Promise<boolean>;
type ConversationFilter = "all" | "starred" | `folder:${string}`;

function phaseLabel(status: StoreStatus, locale: Locale): string | null {
  const key = refreshPhaseNoticeKey(status.refresh.phase);
  return key === null ? null : t(locale, key);
}

function visibilityLabel(value: Conversation["visibility"], locale: Locale): string {
  if (value === "public") return t(locale, "conversations.public");
  if (value === "shared") return t(locale, "conversations.visibilityShared");
  return t(locale, "conversations.private");
}

function duration(conversation: Conversation, locale: Locale): string | null {
  if (conversation.startedAt === null || conversation.finishedAt === null) return null;
  const seconds = Math.max(0, (conversation.finishedAt - conversation.startedAt) / 1000);
  return formatDuration(seconds, locale, "short");
}

function displayTimestamp(conversation: Conversation): number | null {
  for (const value of [conversation.startedAt, conversation.updatedAt, conversation.createdAt]) {
    if (typeof value === "number" && Number.isFinite(value) && value > 0) return value;
  }
  return null;
}

function dateLabel(value: number | null, locale: Locale, deterministic = false): string {
  if (value === null) return t(locale, "conversations.dateUnavailable");
  // Fixture timestamps are UTC so captured screenshots do not drift at a day
  // boundary. Live rows may still be rendered in the user's local zone.
  const options: Intl.DateTimeFormatOptions = { dateStyle: "medium", timeStyle: "short", ...(deterministic ? { timeZone: "UTC" } : {}) };
  return formatDate(value, locale, options);
}

function dayLabel(value: number | null, locale: Locale, deterministic: boolean): string {
  if (value === null) return t(locale, "conversations.dateUnavailable");
  if (deterministic && new Date(value).toISOString().slice(0, 10) === new Date(CONVERSATION_FIXED_NOW).toISOString().slice(0, 10)) {
    return t(locale, "tasks.today");
  }
  return formatDate(value, locale, { dateStyle: "medium", ...(deterministic ? { timeZone: "UTC" } : {}) });
}

function timeLabel(value: number | null, locale: Locale, deterministic: boolean): string {
  if (value === null) return t(locale, "conversations.dateUnavailable");
  return formatDate(value, locale, { timeStyle: "short", ...(deterministic ? { timeZone: "UTC" } : {}) });
}

function sourceAttribution(source: string, locale: Locale): string | null {
  // `source` is an open legacy enum. Never render an unknown backend value as
  // product copy: the only attribution this slice can name honestly is Omi.
  return source.trim().toLowerCase() === "omi" ? t(locale, "conversations.sourceOmi") : null;
}

function folderLabel(folderId: string | null, folders: Folder[], locale: Locale): string {
  if (!folderId) return t(locale, "conversations.unfiled");
  return folders.find((folder) => folder.id === folderId)?.name ?? t(locale, "conversations.unfiled");
}

function conversationHref(id: Conversation["id"], fixture?: ConversationFixtureState): string {
  const params = new URLSearchParams(location.search);
  params.delete("qa");
  params.delete("state");
  params.set("route", "conversations");
  if (fixture) {
    params.set("qa", "conversations");
    params.set("state", fixture);
  }
  params.set("conversation", id);
  return `?${params.toString()}`;
}

function listHref(fixture?: ConversationFixtureState): string {
  const params = new URLSearchParams(location.search);
  params.delete("conversation");
  params.delete("qa");
  params.set("route", "conversations");
  if (fixture) {
    params.set("qa", "conversations");
    params.set("state", fixture);
  }
  return `?${params.toString()}`;
}

function ConversationRow({ conversation, locale, run, store, fixture }: {
  conversation: Conversation;
  locale: Locale;
  run: RunOperation;
  store: ProductionConversationStore;
  fixture?: ConversationFixtureState | undefined;
}): React.JSX.Element {
  const canPatch = !conversation.isLocked && !conversation.discarded;
  const title = conversation.title.trim() || t(locale, "conversations.untitled");
  const rowDuration = duration(conversation, locale);
  const timestamp = displayTimestamp(conversation);
  return (
    <article className={`conversation-row${conversation.isLocked ? " is-locked" : ""}${conversation.discarded ? " is-discarded" : ""}`} data-conversation-id={conversation.id}>
      <span className="conversation-avatar" aria-hidden={true} />
      <a className="conversation-row-main" href={conversationHref(conversation.id, fixture)}>
        <h3 className="conversation-row-title">{title}</h3>
        <div className="conversation-row-meta">
          <span>{timeLabel(timestamp, locale, Boolean(fixture))}</span>
          {rowDuration && <span>{rowDuration}</span>}
          {conversation.isLocked && <span>{t(locale, "locked.title")}</span>}
          {conversation.discarded && <span>{t(locale, "conversations.discarded")}</span>}
        </div>
      </a>
      <div className="conversation-row-actions" aria-label={t(locale, "conversations.title")}>
        <button
          type="button"
          className={`conversation-star${conversation.starred ? " is-starred" : ""}`}
          disabled={!canPatch}
          aria-label={conversation.starred ? t(locale, "conversations.unstar") : t(locale, "conversations.star")}
          onClick={() => void run(() => store.patch(conversation.id, { starred: !conversation.starred }))}
        >
          <span aria-hidden={true} />
        </button>
      </div>
    </article>
  );
}

function ConversationDetail({ conversation, folders, locale, run, store, fixture }: {
  conversation: Conversation;
  folders: Folder[];
  locale: Locale;
  run: RunOperation;
  store: ProductionConversationStore;
  fixture?: ConversationFixtureState | undefined;
}): React.JSX.Element {
  const [titleDraft, setTitleDraft] = useState(conversation.title);
  const [editingTitle, setEditingTitle] = useState(false);
  const [expanded, setExpanded] = useState(false);
  useEffect(() => { setTitleDraft(conversation.title); }, [conversation.title]);
  const canPatch = !conversation.isLocked && !conversation.discarded;
  const title = conversation.title.trim() || t(locale, "conversations.untitled");
  const summary = conversation.overview.trim() || t(locale, "conversations.noSummary");
  const timestamp = displayTimestamp(conversation);
  const attribution = sourceAttribution(conversation.source, locale);
  const isLong = summary.length > 320;
  const saveTitle = async (): Promise<void> => {
    const next = titleDraft.trim();
    if (!canPatch || !next || next === conversation.title) { setEditingTitle(false); return; }
    if (await run(() => store.patch(conversation.id, { title: next }))) setEditingTitle(false);
  };
  return (
    <section className="conversation-detail" data-conversation-detail={conversation.id}>
      <a className="conversation-back" href={listHref(fixture)}>{t(locale, "conversation.detail.back")}</a>
      <header className="conversation-detail-header">
        <div className="conversation-detail-title-editor">
          {editingTitle ? (
            <>
              <input
                autoFocus
                value={titleDraft}
                aria-label={t(locale, "conversations.editTitle")}
                onChange={(event) => setTitleDraft(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") void saveTitle();
                  if (event.key === "Escape") { setTitleDraft(conversation.title); setEditingTitle(false); }
                }}
              />
              <div className="conversation-detail-actions">
                <button type="button" onClick={() => void saveTitle()} disabled={!canPatch || !titleDraft.trim()}>{t(locale, "conversations.saveTitle")}</button>
                <button type="button" onClick={() => { setTitleDraft(conversation.title); setEditingTitle(false); }}>{t(locale, "common.cancel")}</button>
              </div>
            </>
          ) : <h2>{title}</h2>}
        </div>
        {!conversation.isLocked && !conversation.discarded && <button type="button" onClick={() => setEditingTitle(true)}>{t(locale, "conversations.editTitle")}</button>}
      </header>
      {conversation.isLocked && <p className="locked-explanation">{t(locale, "conversations.lockedBody")}</p>}
      {conversation.discarded && <p className="locked-explanation">{t(locale, "conversations.discardedBody")}</p>}
      <dl className="conversation-detail-meta">
        <div><dt>{t(locale, "conversations.date")}</dt><dd>{dateLabel(timestamp, locale, Boolean(fixture))}</dd></div>
        <div><dt>{t(locale, "conversations.duration")}</dt><dd>{duration(conversation, locale) ?? t(locale, "conversations.noDuration")}</dd></div>
        <div><dt>{t(locale, "conversations.visibility")}</dt><dd>{visibilityLabel(conversation.visibility, locale)}</dd></div>
        <div><dt>{t(locale, "conversations.folder")}</dt><dd>{folderLabel(conversation.folderId, folders, locale)}</dd></div>
      </dl>
      {attribution && <p className="conversation-source">{attribution}</p>}
      <section className="conversation-summary" aria-labelledby="conversation-summary-heading">
        <h3 id="conversation-summary-heading">{t(locale, "conversations.detailSummary")}</h3>
        <p className={`conversation-long-body${expanded ? " is-expanded" : ""}`}>{summary}</p>
        {isLong && <button type="button" aria-expanded={expanded} onClick={() => setExpanded((value) => !value)}>{expanded ? t(locale, "conversations.showLess") : t(locale, "conversations.showMore")}</button>}
      </section>
      {canPatch && <div className="conversation-detail-actions">
        <button type="button" onClick={() => void run(() => store.patch(conversation.id, { starred: !conversation.starred }))}>{conversation.starred ? t(locale, "conversations.unstar") : t(locale, "conversations.star")}</button>
        <>
          <label>{t(locale, "conversations.visibility")}
            <select value={conversation.visibility} onChange={(event) => void run(() => store.patch(conversation.id, { visibility: event.target.value as Conversation["visibility"] }))}>
              <option value="private">{t(locale, "conversations.visibilityPrivate")}</option>
              <option value="public">{t(locale, "conversations.public")}</option>
              <option value="shared">{t(locale, "conversations.visibilityShared")}</option>
            </select>
          </label>
          <label>{t(locale, "conversations.folder")}
            <select value={conversation.folderId ?? ""} onChange={(event) => void run(() => store.patch(conversation.id, { folderId: event.target.value || null }))}>
              <option value="">{t(locale, "conversations.unfiled")}</option>
              {folders.map((folder) => <option value={folder.id} key={folder.id}>{folder.name}</option>)}
            </select>
          </label>
        </>
        <button type="button" onClick={() => {
          if (!globalThis.confirm(t(locale, "conversations.deleteConfirm"))) return;
          void run(async () => { await store.delete(conversation.id); location.assign(listHref(fixture)); });
        }}>{t(locale, "conversations.delete")}</button>
      </div>}
    </section>
  );
}

export function ConversationsProduction({ store, foldersStore, fixture, detailId, locale = "en", onReady }: {
  store: ProductionConversationStore;
  foldersStore: ProductionFolderStore;
  fixture?: ConversationFixtureState | undefined;
  detailId?: string | undefined;
  locale?: Locale;
  onReady?: () => void;
}): React.JSX.Element {
  const [rows, setRows] = useState<Conversation[]>([]);
  const [folders, setFolders] = useState<Folder[]>([]);
  const [dead, setDead] = useState<Awaited<ReturnType<ProductionConversationStore["deadLetters"]>>>([]);
  const [status, setStatus] = useState(store.status());
  const [operationError, setOperationError] = useState<string | null>(null);
  const [filter, setFilter] = useState<ConversationFilter>("all");
  const [query, setQuery] = useState("");
  const readyRef = useRef(false);
  const onReadyRef = useRef(onReady);
  useEffect(() => { onReadyRef.current = onReady; }, [onReady]);

  const reload = useCallback(async (): Promise<void> => {
    try {
      const [nextRows, nextDead, nextFolders] = await Promise.all([store.list(), store.deadLetters(), foldersStore.list()]);
      setRows(nextRows);
      setDead(nextDead);
      setFolders(nextFolders);
    } catch {
      setOperationError(t(locale, "lifecycle.error"));
    }
    setStatus(store.status());
  }, [foldersStore, locale, store]);

  const run = useCallback<RunOperation>(async (operation) => {
    setOperationError(null);
    try { await operation(); await reload(); return true; }
    catch { setOperationError(t(locale, "lifecycle.error")); setStatus(store.status()); return false; }
  }, [locale, reload, store]);

  useEffect(() => {
    let active = true;
    const unsubscribe = store.subscribe(() => { if (active) void reload(); });
    const unsubscribeFolders = foldersStore.subscribe(() => { if (active) void reload(); });
    const boot = async (): Promise<void> => {
      await reload();
      try { await Promise.all([store.refresh(), foldersStore.refresh()]); }
      catch { setOperationError(t(locale, "lifecycle.error")); }
      await reload();
      if (active && !readyRef.current) { readyRef.current = true; onReadyRef.current?.(); }
    };
    void boot();
    return () => { active = false; unsubscribe(); unsubscribeFolders(); };
  }, [foldersStore, locale, reload, store]);

  const notice = phaseLabel(status, locale);
  const queueLabel = useMemo(() => {
    const count = status.queue.pendingCount;
    if (!count) return null;
    if (status.queue.phase === "needs-auth") return t(locale, "queue.paused");
    if (status.queue.phase === "retrying") return t(locale, "queue.retrying");
    if (status.queue.phase === "sending") return t(locale, "queue.sending", { count });
    return t(locale, "queue.queuedCount", { count });
  }, [locale, status]);
  const selected = detailId ? rows.find((row) => row.id === detailId) : undefined;
  const visibleRows = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase();
    const folderId = filter.startsWith("folder:") ? filter.slice("folder:".length) : null;
    const scopedRows = filter === "starred" ? rows.filter((row) => row.starred) : rows;
    return scopedRows.filter((row) => {
      if (folderId !== null && row.folderId !== folderId) return false;
      if (!needle) return true;
      return `${row.title} ${row.overview}`.toLocaleLowerCase().includes(needle);
    });
  }, [filter, query, rows]);
  const dayGroups = useMemo(() => {
    const groups = new Map<string, { label: string; rows: Conversation[] }>();
    for (const row of visibleRows) {
      const timestamp = displayTimestamp(row);
      const label = dayLabel(timestamp, locale, Boolean(fixture));
      const existing = groups.get(label);
      if (existing) existing.rows.push(row);
      else groups.set(label, { label, rows: [row] });
    }
    return [...groups.values()];
  }, [fixture, locale, visibleRows]);
  const filterOptions = useMemo<ProductionFilterOption<ConversationFilter>[]>(() => [
    { value: "all", label: t(locale, "conversations.all") },
    { value: "starred", label: t(locale, "conversations.starred") },
    ...folders.filter((folder) => !folder.isSystem).map((folder) => ({
      value: `folder:${folder.id}` as const,
      label: folder.name,
    })),
  ], [folders, locale]);

  return (
    <main className="production-shell" data-production-shell="true" data-route="conversations" data-surface-state={status.refresh.phase} data-qa-fixture={fixture ?? "none"}>
      <ProductionChrome locale={locale} active="conversations" placement="top" />
      <section className="desktop-page-panel">
      <ProductionLibrarySegment locale={locale} active="conversations" />
      <header className="production-header">
        <div><p className="eyebrow">{t(locale, "nav.conversations")}</p><h1>{t(locale, "conversations.title")}</h1><p>{t(locale, "conversations.subtitle")}</p></div>
        {status.refresh.phase !== "ready" && <button type="button" onClick={() => void run(() => store.refresh())} aria-label={t(locale, "common.retry")}>{t(locale, "common.retry")}</button>}
      </header>
      {fixture && <p className="qa-label">{t(locale, "qa.fixtureLabel", { name: t(locale, "qa.syntheticData"), fixture })}</p>}
      {notice && <div className={`status-notice ${status.refresh.phase}`} role="status">{notice}</div>}
      {queueLabel && <div className={`queue-notice ${status.queue.phase}`} role="status">{queueLabel}</div>}
      {operationError && <div className="operation-error" role="alert">{operationError}</div>}
      {selected ? <ConversationDetail conversation={selected} folders={folders} locale={locale} run={run} store={store} fixture={fixture} /> : detailId ? <p className="empty-state">{t(locale, "conversations.detailNotFound")}</p> : <>
        <div className="conversation-controls">
          <ProductionSearchField className="conversation-search" label={t(locale, "conversations.filterSavedPlaceholder")} placeholder={t(locale, "conversations.filterSavedPlaceholder")} value={query} onValueChange={setQuery} />
        </div>
        <ProductionFilterChips className="conversation-filter" label={t(locale, "conversations.title")} value={filter} options={filterOptions} onValueChange={setFilter} />
        {status.refresh.phase === "ready" && rows.length === 0 ? <div className="empty-state"><strong>{t(locale, "conversations.emptyTitle")}</strong><p>{t(locale, "conversations.emptyBody")}</p></div> : visibleRows.length === 0 ? <p className="empty-state">{t(locale, "common.noResults")}</p> : <section className="conversation-list" aria-label={t(locale, "conversations.title")}>
          {dayGroups.map((group) => <section className="conversation-day-group" key={group.label} aria-label={group.label}>
            <h2>{group.label}</h2>
            {group.rows.map((conversation) => <ConversationRow key={conversation.id} conversation={conversation} locale={locale} run={run} store={store} fixture={fixture} />)}
          </section>)}
        </section>}
      </>}
      {dead.length > 0 && <section className="dead-letter-panel" aria-label={t(locale, "dead.title")}><h2>{t(locale, "dead.title")}</h2>{dead.map(deadLetterView).map((view) => <div className="dead-letter" key={view.opId}><span>{t(locale, view.messageKey)}</span>{view.savedEdit !== null && <pre className="dead-letter-payload">{view.savedEdit}</pre>}{/* Discard only — a retry resubmits an envelope the epoch fence refuses forever (dead-letter-presentation.ts). */}<button type="button" onClick={() => void run(() => store.discardDeadLetter(view.opId))}>{t(locale, "dead.remove")}</button></div>)}</section>}
      </section>
      <ProductionChrome locale={locale} active="conversations" placement="bottom" />
    </main>
  );
}
