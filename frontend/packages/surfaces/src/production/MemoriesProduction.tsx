import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Memory } from "@omi-core/contracts";
import { formatDate, t } from "@omi-core/i18n";
import type { StoreStatus } from "@omi-core/domain";
import type { ProductionMemoryStore } from "./ProductionStores.js";
import { ProductionChrome, ProductionLibrarySegment } from "./ProductionChrome.js";
import { ProductionFilterChips, ProductionSearchField } from "./ProductionPrimitives.js";
import { presentMemoryContent } from "./memory-presentation.js";

type Locale = string;
type RunOperation = (operation: () => Promise<void>) => Promise<boolean>;

function phaseLabel(status: StoreStatus, locale: Locale): string | null {
  switch (status.refresh.phase) {
    case "initial-loading": return t(locale, "lifecycle.loading");
    case "refreshing": return t(locale, "lifecycle.refreshing");
    case "saved-but-refresh-failed": return t(locale, "lifecycle.savedFailed");
    case "unavailable": return t(locale, "lifecycle.unavailable");
    default: return null;
  }
}

function MemoryCard({ memory, store, locale, run }: {
  memory: Memory;
  store: ProductionMemoryStore;
  locale: Locale;
  run: RunOperation;
}): React.JSX.Element {
  const [draft, setDraft] = useState(memory.content);
  const [expanded, setExpanded] = useState(false);
  const [editing, setEditing] = useState(false);
  // Split the stored value first, then collapse only its body. This keeps the
  // provenance prefix visible without ever changing the value sent to a store.
  const { provenance, body } = presentMemoryContent(memory.content);
  const isLong = body.length > 240;
  const visibleText = !expanded && isLong ? `${body.slice(0, 240)}…` : body;
  const targetVisibility = memory.visibility === "public" ? "private" : "public";
  useEffect(() => setDraft(memory.content), [memory.content]);

  const cancelEdit = (): void => {
    setDraft(memory.content);
    setEditing(false);
  };
  const save = async (): Promise<void> => {
    const value = draft.trim();
    if (!value || value === memory.content) { setEditing(false); return; }
    if (await run(() => store.patch(memory.id, { content: value }))) setEditing(false);
  };
  return (
    <article className={`memory-card${memory.locked ? " is-locked" : ""}`} data-memory-id={memory.id} data-long={isLong || undefined}>
      <header className="memory-card-header">
        <span className="memory-provenance">{provenance ?? memory.category}</span>
        <div className="memory-meta">
          <span>{t(locale, "memories.capturedOn", { date: formatDate(memory.updatedAt, locale) })}</span>
          <span className="memory-visibility">{memory.visibility === "public" ? t(locale, "memories.public") : t(locale, "memories.private")}</span>
        </div>
      </header>
      {memory.locked ? (
        <>
          <p className="memory-content locked-content">{visibleText}</p>
          <p className="locked-explanation">{t(locale, "locked.body")}</p>
        </>
      ) : editing ? (
        <textarea className="memory-editor" value={draft} aria-label={t(locale, "memories.edit")} autoFocus onChange={(event) => setDraft(event.target.value)} onKeyDown={(event) => {
          if (event.key === "Escape") cancelEdit();
          if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) void save();
        }} />
      ) : (
        <p className="memory-content">{visibleText}</p>
      )}
      <div className="memory-actions" aria-label={t(locale, "memories.action")}>
        {memory.locked ? (
          <>
            <span className="locked-label">{t(locale, "locked.title")}</span>
            <button type="button" onClick={() => void run(() => store.patch(memory.id, { visibility: targetVisibility }))}>
              {targetVisibility === "public" ? t(locale, "memories.makePublic") : t(locale, "memories.makePrivate")}
            </button>
          </>
        ) : (
          <>
            <button type="button" onClick={() => editing ? cancelEdit() : setEditing(true)} aria-label={t(locale, "memories.edit")}>
              {editing ? t(locale, "common.cancel") : t(locale, "common.edit")}
            </button>
            {editing && <button type="button" onClick={() => void save()}>{t(locale, "common.save")}</button>}
            <button type="button" onClick={() => void run(() => store.patch(memory.id, { visibility: targetVisibility }))}>
              {targetVisibility === "public" ? t(locale, "memories.makePublic") : t(locale, "memories.makePrivate")}
            </button>
          </>
        )}
        {isLong && <button type="button" onClick={() => setExpanded((value) => !value)} aria-expanded={expanded}>
          {expanded ? t(locale, "content.showLess") : t(locale, "content.showMore")}
        </button>}
        <button className="danger-action" type="button" onClick={() => { if (globalThis.confirm(t(locale, "memories.deleteConfirm"))) void run(() => store.delete(memory.id)); }} aria-label={t(locale, "common.delete")}>{t(locale, "common.delete")}</button>
      </div>
    </article>
  );
}

export function MemoriesProduction({ store, fixture, locale = "en", onReady }: {
  store: ProductionMemoryStore;
  fixture?: string;
  locale?: Locale;
  onReady?: () => void;
}): React.JSX.Element {
  const [rows, setRows] = useState<Memory[]>([]);
  const [dead, setDead] = useState<Awaited<ReturnType<ProductionMemoryStore["deadLetters"]>>>([]);
  const [status, setStatus] = useState(store.status());
  const [draft, setDraft] = useState("");
  const [draftVisibility, setDraftVisibility] = useState<"public" | "private">("private");
  const [composerOpen, setComposerOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [visibilityFilter, setVisibilityFilter] = useState<"all" | "public" | "private">("all");
  const [operationError, setOperationError] = useState<string | null>(null);
  const readyRef = useRef(false);
  const onReadyRef = useRef(onReady);
  useEffect(() => { onReadyRef.current = onReady; }, [onReady]);

  const reload = useCallback(async (): Promise<void> => {
    try {
      const [nextRows, nextDead] = await Promise.all([store.list(), store.deadLetters()]);
      setRows(nextRows);
      setDead(nextDead);
    } catch {
      setOperationError(t(locale, "lifecycle.error"));
    }
    setStatus(store.status());
  }, [locale, store]);

  const run = useCallback<RunOperation>(async (operation) => {
    setOperationError(null);
    try {
      await operation();
      await reload();
      return true;
    } catch {
      setOperationError(t(locale, "lifecycle.error"));
      setStatus(store.status());
      return false;
    }
  }, [locale, reload, store]);

  useEffect(() => {
    let active = true;
    const unsubscribe = store.subscribe(() => { if (active) void reload(); });
    const boot = async (): Promise<void> => {
      await reload();
      try {
        await store.refresh();
      } catch {
        setOperationError(t(locale, "lifecycle.error"));
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
  }, [locale, reload, store]);

  const notice = phaseLabel(status, locale);
  const queueLabel = useMemo(() => {
    const count = status.queue.pendingCount;
    if (!count) return null;
    if (status.queue.phase === "needs-auth") return t(locale, "queue.paused");
    if (status.queue.phase === "retrying") return t(locale, "queue.retrying");
    if (status.queue.phase === "sending") return t(locale, "queue.sending", { count });
    return t(locale, "queue.queuedCount", { count });
  }, [locale, status]);

  const add = async (): Promise<void> => {
    const content = draft.trim();
    if (!content) return;
    if (await run(() => store.create(content, { visibility: draftVisibility }))) {
      setDraft((current) => current.trim() === content ? "" : current);
      setComposerOpen(false);
    }
  };
  const visibleRows = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase(locale);
    return rows.filter((memory) => {
      if (visibilityFilter !== "all" && memory.visibility !== visibilityFilter) return false;
      return !needle || memory.content.toLocaleLowerCase(locale).includes(needle);
    });
  }, [locale, query, rows, visibilityFilter]);

  return (
    <main className="production-shell" data-production-shell="true" data-route="memories" data-surface-state={status.refresh.phase} data-qa-fixture={fixture ?? "none"}>
      <ProductionChrome locale={locale} active="memories" placement="top" />
      <section className="desktop-page-panel">
      <ProductionLibrarySegment locale={locale} active="memories" />
      <header className="production-header memories-header">
        <div><p className="eyebrow">{t(locale, "nav.memories")}</p><h1>{t(locale, "memories.title")}</h1><p>{t(locale, "memories.subtitle")}</p></div>
        <div className="header-actions">
          {status.refresh.phase !== "ready" && <button type="button" onClick={() => void run(() => store.refresh())} aria-label={t(locale, "common.retry")}>{t(locale, "common.retry")}</button>}
        </div>
      </header>
      <div className="surface-notices" aria-live="polite">
        {fixture && <p className="qa-label">{t(locale, "qa.fixtureLabel", { name: t(locale, "qa.syntheticData"), fixture })}</p>}
        {notice && <div className={`status-notice ${status.refresh.phase}`} role="status">{notice}</div>}
        {queueLabel && <div className={`queue-notice ${status.queue.phase}`} role="status">{queueLabel}</div>}
        {operationError && <div className="operation-error" role="alert">{operationError}</div>}
      </div>
      {composerOpen && <form className="memory-create" aria-label={t(locale, "memories.create")} onSubmit={(event) => { event.preventDefault(); void add(); }}>
        <textarea autoFocus value={draft} onChange={(event) => setDraft(event.target.value)} placeholder={t(locale, "memories.create")} aria-label={t(locale, "memories.create")} />
        <label className="visibility-control">{t(locale, "memories.visibility")}
          <select value={draftVisibility} onChange={(event) => setDraftVisibility(event.target.value as "public" | "private")}>
            <option value="private">{t(locale, "memories.private")}</option>
            <option value="public">{t(locale, "memories.public")}</option>
          </select>
        </label>
        <button type="submit" disabled={!draft.trim()}>{t(locale, "common.save")}</button>
      </form>}
      <div className="memory-controls">
        <ProductionSearchField className="memory-search" label={t(locale, "memories.filterSavedPlaceholder")} placeholder={t(locale, "memories.filterSavedPlaceholder")} value={query} onValueChange={setQuery} />
        <ProductionFilterChips
          className="memory-filter"
          label={t(locale, "memories.visibility")}
          value={visibilityFilter}
          options={[
            { value: "all", label: t(locale, "memories.all") },
            { value: "private", label: t(locale, "memories.private") },
            { value: "public", label: t(locale, "memories.public") },
          ]}
          onValueChange={setVisibilityFilter}
        />
        <div className="memory-toolbar-actions">
          <button className="memory-create-trigger" type="button" aria-expanded={composerOpen} aria-label={composerOpen ? t(locale, "common.cancel") : t(locale, "memories.create")} title={composerOpen ? t(locale, "common.cancel") : t(locale, "memories.create")} onClick={() => setComposerOpen((open) => !open)}>{composerOpen ? "×" : "+"}</button>
          <button className="memory-more-trigger" type="button" disabled aria-label={t(locale, "common.more")} title={t(locale, "common.more")}>•••</button>
        </div>
      </div>
      {status.refresh.phase === "ready" && rows.length === 0 ? <p className="empty-state">{t(locale, "memories.emptyBody")}</p> : visibleRows.length === 0 ? <p className="empty-state">{t(locale, "common.noResults")}</p> : <section className="memory-grid" aria-label={t(locale, "memories.title")}>{visibleRows.map((memory) => <MemoryCard key={memory.id} memory={memory} store={store} locale={locale} run={run} />)}</section>}
      {dead.length > 0 && <section className="dead-letter-panel" aria-label={t(locale, "dead.title")}><h2>{t(locale, "dead.title")}</h2>{dead.map((letter) => <div className="dead-letter" key={letter.opId}><span>{t(locale, "dead.body")}</span><button type="button" onClick={() => void run(async () => { await store.discardDeadLetter(letter.opId); await reload(); })}>{t(locale, "dead.remove")}</button></div>)}</section>}
      </section>
      <ProductionChrome locale={locale} active="memories" placement="bottom" />
    </main>
  );
}
