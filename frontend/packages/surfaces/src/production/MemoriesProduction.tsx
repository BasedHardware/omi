import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Memory } from "@omi-core/contracts";
import { formatDate, t } from "@omi-core/i18n";
import type { ProductionMemoryStore } from "./ProductionStores.js";
import { deadLetterView } from "./dead-letter-presentation.js";
import { ProductionChrome, ProductionLibrarySegment } from "./ProductionChrome.js";
import { ProductionDataSourceBadge, ProductionFilterChips, ProductionLifecycleRegion, ProductionLiveAnnouncement, ProductionSearchField, type SurfaceDataSource } from "./ProductionPrimitives.js";
import { listEmptyKind } from "./list-empty-presentation.js";
import { presentMemoryContent } from "./memory-presentation.js";
import { createProductionCommandRegistry, dispatchProductionCommand } from "./command-registry.js";

type Locale = string;
type RunOperation = (operation: () => Promise<void>) => Promise<boolean>;
const commandRegistry = createProductionCommandRegistry();

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
          dispatchProductionCommand(event.nativeEvent, commandRegistry, {
            activeRoute: "memories",
            navigate: () => undefined,
            handlers: { "save-memory": () => void save(), "cancel-memory": cancelEdit },
          });
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
  const emptyKind = listEmptyKind({
    phase: status.refresh.phase,
    rowCount: rows.length,
    visibleCount: visibleRows.length,
  });
  const source = (fixture
    ? { kind: "fixture", fixture }
    : { kind: "live", origin: "bridge" }) satisfies SurfaceDataSource;

  return (
    <main className="production-shell" data-production-shell="true" data-route="memories" data-surface-state={status.refresh.phase} data-qa-fixture={fixture ?? "none"} data-consumer-semantic={`memories:visible:${visibleRows.length}:total:${rows.length}`}>
      <ProductionChrome locale={locale} active="memories" placement="top" />
      <section className="desktop-page-panel">
      <ProductionLibrarySegment locale={locale} active="memories" />
      <header className="production-header memories-header">
        <div><p className="eyebrow">{t(locale, "nav.memories")}</p><h1>{t(locale, "memories.title")}</h1><p>{t(locale, "memories.subtitle")}</p></div>
      </header>
      <ProductionDataSourceBadge source={source} locale={locale} />
      <ProductionLifecycleRegion
        className="surface-notices"
        phase={status.refresh.phase}
        hasSavedData={status.refresh.hasSavedData}
        locale={locale}
        queue={status.queue}
        deadLetterCount={dead.length}
        operationError={operationError}
        nextAction={status.refresh.phase !== "ready" || operationError ? t(locale, "common.retry") : null}
        retry={status.refresh.phase !== "ready" ? { onRetry: async () => { await run(() => store.refresh()); } } : null}
      />
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
      <ProductionLiveAnnouncement message={t(locale, "lifecycle.resultsCount", { count: visibleRows.length })} />
      {status.refresh.phase === "ready" && rows.length === 0 ? <div className="empty-state" data-empty-kind="empty-projection"><strong>{t(locale, "memories.emptyTitle")}</strong><p>{t(locale, "memories.emptyBody")}</p></div> : emptyKind === "filtered-out" ? <p className="empty-state" data-empty-kind="filtered-out">{t(locale, "common.noResults")}</p> : visibleRows.length === 0 ? null : <section className="memory-grid" aria-label={t(locale, "memories.title")}>{visibleRows.map((memory) => <MemoryCard key={memory.id} memory={memory} store={store} locale={locale} run={run} />)}</section>}
      {dead.length > 0 && <section className="dead-letter-panel" aria-label={t(locale, "dead.title")}><h2>{t(locale, "dead.title")}</h2>{dead.map(deadLetterView).map((view) => <div className="dead-letter" key={view.opId}><span>{t(locale, view.messageKey)}</span>{view.savedEdit !== null && <pre className="dead-letter-payload">{view.savedEdit}</pre>}{/* Discard only — a retry resubmits an envelope the epoch fence refuses forever (dead-letter-presentation.ts). */}<button type="button" onClick={() => void run(async () => { await store.discardDeadLetter(view.opId); await reload(); })}>{t(locale, "dead.remove")}</button></div>)}</section>}
      </section>
      <ProductionChrome locale={locale} active="memories" placement="bottom" />
    </main>
  );
}
