import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Memory } from "@omi-core/contracts";
import { formatDate, t } from "@omi-core/i18n";
import type { StoreStatus } from "@omi-core/domain";
import type { ProductionMemoryStore } from "./memory-fixtures.js";
import { ProductionChrome } from "./ProductionChrome.js";

type Locale = string;
type RunOperation = (operation: () => Promise<void>) => Promise<void>;

function splitProvenance(content: string): { prefix: string | null; text: string } {
  const match = /^([a-z][a-z0-9_-]{1,30}):\s+(.+)$/i.exec(content);
  return match ? { prefix: `${match[1]}:`, text: match[2] ?? "" } : { prefix: null, text: content };
}

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
  const isLong = memory.content.length > 240;
  // Split the stored value first, then collapse only its body. This keeps the
  // provenance prefix visible without ever changing the value sent to a store.
  const { prefix, text } = splitProvenance(memory.content);
  const visibleText = !expanded && isLong ? `${text.slice(0, 240)}…` : text;
  const targetVisibility = memory.visibility === "public" ? "private" : "public";
  useEffect(() => setDraft(memory.content), [memory.content]);

  const save = (): void => {
    const value = draft.trim();
    setEditing(false);
    if (value && value !== memory.content) void run(() => store.patch(memory.id, { content: value }));
  };
  return (
    <article className={`memory-card${memory.locked ? " is-locked" : ""}`} data-memory-id={memory.id}>
      <div className="memory-meta">
        <span className="memory-provenance">{prefix ?? memory.category}</span>
        <span>{t(locale, "memories.capturedOn", { date: formatDate(memory.updatedAt, locale) })}</span>
        <span>{memory.visibility === "public" ? t(locale, "memories.public") : t(locale, "memories.private")}</span>
      </div>
      {memory.locked ? (
        <>
          <p className="memory-content locked-content">{visibleText}</p>
          <p className="locked-explanation">{t(locale, "locked.body")}</p>
        </>
      ) : editing ? (
        <textarea className="memory-editor" value={draft} aria-label={t(locale, "memories.edit")} onChange={(event) => setDraft(event.target.value)} />
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
            <button type="button" onClick={() => setEditing((value) => !value)} aria-label={t(locale, "memories.edit")}>
              {editing ? t(locale, "common.cancel") : t(locale, "common.edit")}
            </button>
            {editing && <button type="button" onClick={save}>{t(locale, "common.save")}</button>}
            <button type="button" onClick={() => void run(() => store.patch(memory.id, { visibility: targetVisibility }))}>
              {targetVisibility === "public" ? t(locale, "memories.makePublic") : t(locale, "memories.makePrivate")}
            </button>
          </>
        )}
        {isLong && <button type="button" onClick={() => setExpanded((value) => !value)} aria-expanded={expanded}>
          {expanded ? t(locale, "content.showLess") : t(locale, "content.showMore")}
        </button>}
        <button type="button" onClick={() => void run(() => store.delete(memory.id))} aria-label={t(locale, "common.delete")}>{t(locale, "common.delete")}</button>
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
    } catch {
      setOperationError(t(locale, "lifecycle.error"));
      setStatus(store.status());
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

  const add = (): void => {
    const content = draft.trim();
    if (!content) return;
    setDraft("");
    void run(() => store.create(content, { visibility: draftVisibility }));
  };

  return (
    <main className="production-shell" data-production-shell="true" data-route="memories" data-surface-state={status.refresh.phase} data-qa-fixture={fixture ?? "none"}>
      <ProductionChrome locale={locale} active="memories" placement="top" />
      <header className="production-header">
        <div><p className="eyebrow">{t(locale, "nav.memories")}</p><h1>{t(locale, "memories.title")}</h1><p>{t(locale, "memories.subtitle")}</p></div>
        {status.refresh.phase !== "ready" && <button type="button" onClick={() => void run(() => store.refresh())} aria-label={t(locale, "common.retry")}>{t(locale, "common.retry")}</button>}
      </header>
      {fixture && <p className="qa-label">{t(locale, "qa.fixtureLabel", { name: t(locale, "qa.syntheticData"), fixture })}</p>}
      {notice && <div className={`status-notice ${status.refresh.phase}`} role="status">{notice}</div>}
      {queueLabel && <div className={`queue-notice ${status.queue.phase}`} role="status">{queueLabel}</div>}
      {operationError && <div className="operation-error" role="alert">{operationError}</div>}
      <section className="memory-create" aria-label={t(locale, "memories.create")}>
        <textarea value={draft} onChange={(event) => setDraft(event.target.value)} placeholder={t(locale, "memories.create")} aria-label={t(locale, "memories.create")} />
        <label className="visibility-control">{t(locale, "memories.visibility")}
          <select value={draftVisibility} onChange={(event) => setDraftVisibility(event.target.value as "public" | "private")}>
            <option value="private">{t(locale, "memories.private")}</option>
            <option value="public">{t(locale, "memories.public")}</option>
          </select>
        </label>
        <button type="button" onClick={add} disabled={!draft.trim()}>{t(locale, "common.save")}</button>
      </section>
      {status.refresh.phase === "ready" && rows.length === 0 ? <p className="empty-state">{t(locale, "memories.emptyBody")}</p> : <section className="memory-grid" aria-label={t(locale, "memories.title")}>{rows.map((memory) => <MemoryCard key={memory.id} memory={memory} store={store} locale={locale} run={run} />)}</section>}
      {dead.length > 0 && <section className="dead-letter-panel" aria-label={t(locale, "dead.title")}><h2>{t(locale, "dead.title")}</h2>{dead.map((letter) => <div className="dead-letter" key={letter.opId}><span>{letter.summary}</span><span>{t(locale, "dead.body")}</span><button type="button" onClick={() => void run(async () => { await store.discardDeadLetter(letter.opId); await reload(); })}>{t(locale, "dead.remove")}</button></div>)}</section>}
      <ProductionChrome locale={locale} active="memories" placement="bottom" />
    </main>
  );
}
