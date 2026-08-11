import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { t } from "@omi-core/i18n";
import type { StoreStatus } from "@omi-core/domain";
import type { ProductionSynthesizedMemoryStore } from "./ProductionStores.js";
import type { SynthesizedMemoryItem, SynthesizedRecallState } from "@omi-core/contracts";
import { ProductionChrome, ProductionLibrarySegment } from "./ProductionChrome.js";
import { ProductionDataSourceBadge, ProductionLifecycleRegion, ProductionLiveAnnouncement, ProductionSearchField, type SurfaceDataSource } from "./ProductionPrimitives.js";
import {
  citationSummary,
  completenessNotice,
  emptyPresentation,
  filterLoadedPropositions,
  lineageRows,
  paginationAffordance,
} from "./proposition-presentation.js";
import "./memories-platform.css";

/**
 * Platform-generation Memories (board ruling PR-2).
 *
 * A READ model over ratified contracts 0.1.1: stable human-readable propositions with
 * lineage, latest projection by default, citations and provenance shown when present and
 * absent-safe when not. There is no editing, no visibility toggle, no delete and no
 * create, because the wire carries none of those. The legacy editable surface still lives
 * in `MemoriesProduction.tsx`; the two are different generations, not versions.
 *
 * Every honesty decision on this screen comes from `proposition-presentation.ts`, which is
 * pure and directly tested. This component renders those decisions and adds none.
 */

type Locale = string;

function PropositionCard({ item, locale }: {
  item: SynthesizedMemoryItem;
  locale: Locale;
}): React.JSX.Element {
  const [lineageOpen, setLineageOpen] = useState(false);
  const lineage = lineageRows(item);
  const citations = citationSummary(item);
  return (
    <article className="proposition-card" data-proposition-id={item.id}>
      <p className="proposition-text">{item.text}</p>
      <footer className="proposition-footer">
        {citations.count > 0 && (
          <span className="proposition-citations" aria-label={t(locale, "memoriesPlatform.citations")}>
            {t(locale, "memoriesPlatform.citationsCount", { count: citations.count })}
          </span>
        )}
        {lineage.length > 0 && (
          <button
            className="proposition-lineage-toggle"
            type="button"
            aria-expanded={lineageOpen}
            onClick={() => setLineageOpen((open) => !open)}
          >
            {lineageOpen ? t(locale, "memoriesPlatform.hideLineage") : t(locale, "memoriesPlatform.showLineage")}
          </button>
        )}
      </footer>
      {lineageOpen && lineage.length > 0 && (
        <dl className="proposition-lineage" aria-label={t(locale, "memoriesPlatform.lineage")}>
          {lineage.map((row) => (
            <div className="proposition-lineage-row" key={row.labelKey}>
              <dt>{t(locale, row.labelKey)}</dt>
              <dd>{row.value}</dd>
            </div>
          ))}
        </dl>
      )}
    </article>
  );
}

export function MemoriesPlatformProduction({ store, source, locale = "en", onReady }: {
  store: ProductionSynthesizedMemoryStore;
  /**
   * Required, not optional: every call site must declare whether these rows are a review
   * corpus or the signed-in account's real data. A surface that cannot say which one it
   * is showing is worse than no surface.
   */
  source: SurfaceDataSource;
  locale?: Locale;
  onReady?: () => void;
}): React.JSX.Element {
  const [items, setItems] = useState<readonly SynthesizedMemoryItem[]>([]);
  const [recall, setRecall] = useState<SynthesizedRecallState>({ kind: "unknown" });
  const [status, setStatus] = useState<StoreStatus>(store.status());
  const [query, setQuery] = useState("");
  const [loadingMore, setLoadingMore] = useState(false);
  const [operationError, setOperationError] = useState<string | null>(null);
  const readyRef = useRef(false);
  const onReadyRef = useRef(onReady);
  useEffect(() => { onReadyRef.current = onReady; }, [onReady]);

  const reload = useCallback(async (): Promise<void> => {
    try {
      setItems(await store.list());
      setRecall(store.recall());
    } catch {
      setOperationError(t(locale, "lifecycle.error"));
    }
    setStatus(store.status());
  }, [locale, store]);

  useEffect(() => {
    let active = true;
    const unsubscribe = store.subscribe(() => { if (active) void reload(); });
    const boot = async (): Promise<void> => {
      await reload();
      try {
        await store.refresh();
      } catch {
        setOperationError(t(locale, "lifecycle.error"));
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

  const completeness = useMemo(() => completenessNotice(recall), [recall]);
  const pagination = useMemo(() => paginationAffordance(recall), [recall]);
  const presentation = useMemo(() => emptyPresentation(items.length, recall), [items.length, recall]);
  const visibleItems = useMemo(
    () => filterLoadedPropositions(items, query, locale),
    [items, locale, query],
  );

  const loadMore = async (): Promise<void> => {
    if (!pagination.canLoadMore || loadingMore) return;
    setLoadingMore(true);
    setOperationError(null);
    try {
      // The store owns the server's opaque cursor and the accumulation; the surface never
      // touches either, so it cannot continue from a cursor it invented.
      await store.loadMore();
      await reload();
    } catch {
      setOperationError(t(locale, "lifecycle.error"));
    }
    setLoadingMore(false);
  };

  return (
    <main
      className="production-shell"
      data-production-shell="true"
      data-route="memories"
      data-generation="platform"
      data-data-source={source.kind}
      data-surface-state={status.refresh.phase}
      data-qa-fixture={source.kind === "fixture" ? source.fixture : "none"}
      data-consumer-semantic={`memories:visible:${visibleItems.length}:total:${items.length}`}
      data-completeness={completeness.kind}
    >
      <ProductionChrome locale={locale} active="memories" placement="top" />
      <section className="desktop-page-panel">
        <ProductionLibrarySegment locale={locale} active="memories" />
        <ProductionDataSourceBadge source={source} locale={locale} />
        <header className="production-header memories-platform-header">
          <div>
            <p className="eyebrow">{t(locale, "nav.memories")}</p>
            <h1>{t(locale, "memoriesPlatform.title")}</h1>
            <p>{t(locale, "memoriesPlatform.subtitle")}</p>
          </div>
        </header>
        <ProductionLifecycleRegion
          className="surface-notices"
          phase={status.refresh.phase}
          hasSavedData={status.refresh.hasSavedData}
          locale={locale}
          operationError={operationError}
          nextAction={status.refresh.phase !== "ready" ? t(locale, "common.retry") : null}
          retry={status.refresh.phase !== "ready" ? { onRetry: reload } : null}
        />
        <div className="surface-notices">
          {completeness.titleKey && (
            <div
              className={`completeness-notice tone-${completeness.tone}`}
              role="status"
              data-completeness-status={completeness.kind}
              aria-label={t(locale, "memoriesPlatform.completenessLabel")}
            >
              <p className="completeness-title">{t(locale, completeness.titleKey)}</p>
              {completeness.reasonKeys.length > 0 && (
                <ul className="completeness-reasons" aria-label={t(locale, "memoriesPlatform.reasonsLabel")}>
                  {completeness.reasonKeys.map((key) => <li key={key}>{t(locale, key)}</li>)}
                </ul>
              )}
            </div>
          )}
        </div>
        <ProductionLiveAnnouncement message={t(locale, "lifecycle.resultsCount", { count: visibleItems.length })} />
        <p className="proposition-read-only-note">{t(locale, "memoriesPlatform.readOnlyNote")}</p>
        <div className="proposition-controls">
          <ProductionSearchField
            className="proposition-search"
            label={t(locale, "memoriesPlatform.filterSavedPlaceholder")}
            placeholder={t(locale, "memoriesPlatform.filterSavedPlaceholder")}
            value={query}
            onValueChange={setQuery}
          />
        </div>
        {presentation === "recall-unknown" ? (
          <div className="empty-state" data-empty-kind="recall-unknown">
            <p className="empty-title">{t(locale, "memoriesPlatform.recallUnknownTitle")}</p>
            <p>{t(locale, "memoriesPlatform.recallUnknownBody")}</p>
          </div>
        ) : presentation === "query-gap" ? (
          <div className="empty-state" data-empty-kind="query-gap">
            <p className="empty-title">{t(locale, "memoriesPlatform.queryGapTitle")}</p>
            <p>{t(locale, "memoriesPlatform.queryGapBody")}</p>
          </div>
        ) : presentation === "empty-projection" ? (
          <p className="empty-state" data-empty-kind="empty-projection">
            {t(locale, "memoriesPlatform.emptyBody")}
          </p>
        ) : visibleItems.length === 0 ? (
          <p className="empty-state" data-empty-kind="filtered-out">{t(locale, "common.noResults")}</p>
        ) : (
          <section className="proposition-list" aria-label={t(locale, "memoriesPlatform.propositions")}>
            {visibleItems.map((item) => <PropositionCard key={item.id} item={item} locale={locale} />)}
          </section>
        )}
        <div className="proposition-pagination">
          {pagination.canLoadMore && (
            <button type="button" className="proposition-load-more" disabled={loadingMore} onClick={() => void loadMore()}>
              {loadingMore ? t(locale, "memoriesPlatform.loadingMore") : t(locale, "memoriesPlatform.loadMore")}
            </button>
          )}
          {pagination.terminal && presentation === "rows" && (
            <p className="proposition-terminal">{t(locale, "memoriesPlatform.terminalPage")}</p>
          )}
        </div>
      </section>
      <ProductionChrome locale={locale} active="memories" placement="bottom" />
    </main>
  );
}
