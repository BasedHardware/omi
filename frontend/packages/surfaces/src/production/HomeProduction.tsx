import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Conversation, Memory } from "@omi-core/contracts";
import { formatDate, formatNumber, t } from "@omi-core/i18n";
import type { RefreshStatus, StoreStatus } from "@omi-core/domain";
import { ProductionChrome, productionRouteHref } from "./ProductionChrome.js";
import { ProductionDataSourceBadge, ProductionLifecycleRegion, ProductionLiveAnnouncement, type ProductionAnnouncementScheduler, type SurfaceDataSource } from "./ProductionPrimitives.js";
import { ProductionIcon } from "./ProductionIcon.js";
import { presentMemoryContent } from "./memory-presentation.js";
import { combineHomeRefreshStatuses, homeSurfacePresentation } from "./home-presentation.js";
import { refreshPhaseNoticeKey } from "./lifecycle-presentation.js";
import "./home.css";

type Locale = string;

export type SearchProjection<T> = {
  list(): Promise<T[]>;
  status(): StoreStatus;
  refresh?: () => Promise<void>;
  subscribe(listener: () => void): () => void;
};

export type HomeSearchSources = {
  memories: SearchProjection<Memory>;
  conversations: SearchProjection<Conversation>;
};

type HomeRows = {
  memories: Memory[];
  conversations: Conversation[];
};

type HomeKind = "all" | "conversation" | "memory";
type HomeSpineRow =
  | { kind: "memory"; timestamp: number; value: Memory }
  | { kind: "conversation"; timestamp: number; value: Conversation };

const EMPTY_ROWS: HomeRows = { memories: [], conversations: [] };

function conversationHref(id: Conversation["id"]): string {
  const params = new URLSearchParams(location.search);
  params.delete("qa");
  params.delete("state");
  params.set("route", "conversations");
  params.set("conversation", id);
  return `?${params.toString()}`;
}

function normalize(value: string, locale: Locale): string {
  return value.trim().toLocaleLowerCase(locale);
}

function conversationTimestamp(conversation: Conversation): number {
  return conversation.startedAt ?? conversation.updatedAt ?? conversation.createdAt;
}

function spineSearchText(row: HomeSpineRow): string {
  switch (row.kind) {
    case "memory": return `${row.value.content} ${row.value.category}`;
    case "conversation": return `${row.value.title} ${row.value.overview}`;
  }
}

function readCombinedStatus(sources: HomeSearchSources): RefreshStatus {
  return combineHomeRefreshStatuses(
    sources.memories.status().refresh,
    sources.conversations.status().refresh,
  );
}

export function HomeProduction({ sources, source, locale = "en", onReady, initialLastSuccessAt = null, now, announcementScheduler }: {
  sources: HomeSearchSources;
  source?: SurfaceDataSource;
  locale?: Locale;
  onReady?: () => void;
  initialLastSuccessAt?: number | null;
  now?: () => number;
  announcementScheduler?: ProductionAnnouncementScheduler;
}): React.JSX.Element {
  const [rows, setRows] = useState<HomeRows>(EMPTY_ROWS);
  const [query, setQuery] = useState("");
  const [kind, setKind] = useState<HomeKind>("all");
  const [refresh, setRefresh] = useState<RefreshStatus>(() => readCombinedStatus(sources));
  const [lastSuccessAt, setLastSuccessAt] = useState<number | null>(initialLastSuccessAt);
  const searchRef = useRef<HTMLInputElement>(null);
  const readyRef = useRef(false);
  const onReadyRef = useRef(onReady);
  const memorySource = sources.memories;
  const conversationSource = sources.conversations;
  useEffect(() => { onReadyRef.current = onReady; }, [onReady]);

  const reload = useCallback(async (): Promise<void> => {
    const [memories, conversations] = await Promise.allSettled([
      memorySource.list(),
      conversationSource.list(),
    ]);
    setRows((current) => ({
      memories: memories.status === "fulfilled" ? memories.value : current.memories,
      conversations: conversations.status === "fulfilled" ? conversations.value : current.conversations,
    }));
    setRefresh(combineHomeRefreshStatuses(
      memorySource.status().refresh,
      conversationSource.status().refresh,
    ));
  }, [conversationSource, memorySource]);

  useEffect(() => {
    let active = true;
    const notify = (): void => { if (active) void reload(); };
    const unsubscribers = [
      memorySource.subscribe(notify),
      conversationSource.subscribe(notify),
    ];
    void reload().finally(() => {
      if (active && !readyRef.current) {
        readyRef.current = true;
        onReadyRef.current?.();
      }
    });
    return () => {
      active = false;
      for (const unsubscribe of unsubscribers) unsubscribe();
    };
  }, [conversationSource, memorySource, reload]);

  const needle = normalize(query, locale);
  const spine = useMemo<HomeSpineRow[]>(() => [
    ...rows.memories.map((value): HomeSpineRow => ({ kind: "memory", timestamp: value.updatedAt, value })),
    ...rows.conversations.map((value): HomeSpineRow => ({ kind: "conversation", timestamp: conversationTimestamp(value), value })),
  ].sort((left, right) => right.timestamp - left.timestamp), [rows]);
  const results = useMemo(() => spine.filter((row) => {
    if (kind !== "all" && row.kind !== kind) return false;
    return !needle || normalize(spineSearchText(row), locale).includes(needle);
  }), [kind, locale, needle, spine]);
  const filtering = Boolean(needle) || kind !== "all";
  // Every notice / row visibility decision ships through this helper — JSX does not re-derive.
  const presentation = homeSurfacePresentation(refresh, results.length, refreshPhaseNoticeKey(refresh.phase), filtering);
  const dataSource = source ?? { kind: "live", origin: "bridge" } satisfies SurfaceDataSource;
  const canRetry = Boolean(memorySource.refresh || conversationSource.refresh);
  const retry = async (): Promise<void> => {
    await Promise.allSettled([
      memorySource.refresh?.(),
      conversationSource.refresh?.(),
    ]);
    await reload();
    if (readCombinedStatus(sources).phase === "ready" && now) setLastSuccessAt(now());
  };
  const failedWithSavedData = presentation.phase === "saved-but-refresh-failed";
  const refreshFailed = failedWithSavedData || presentation.phase === "unavailable";
  const lastSuccessAgeMs = failedWithSavedData && lastSuccessAt !== null && now
    ? Math.max(0, now() - lastSuccessAt)
    : null;

  return (
    <main className="production-shell home-production-shell" data-production-shell="true" data-route="home" data-surface-state={presentation.phase}>
      <ProductionChrome locale={locale} active="home" placement="top" commandHandlers={{
        "focus-home-search": () => searchRef.current?.focus(),
      }} />
      <div className="home-workspace">
        <section className="home-search-hero" aria-labelledby="home-title">
          <h1 className="visually-hidden" id="home-title">{t(locale, "home.title")}</h1>
          <label className="home-search">
            <span className="visually-hidden">{t(locale, "common.search")}</span>
            <ProductionIcon name="search" className="home-query-mark" size={22} />
            <input
              ref={searchRef}
              type="search"
              value={query}
              placeholder={t(locale, "home.searchPlaceholder")}
              onChange={(event) => setQuery(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Escape" && query) {
                  event.preventDefault();
                  setQuery("");
                }
              }}
            />
            {query && <button type="button" className="home-search-clear" onClick={() => { setQuery(""); searchRef.current?.focus(); }} aria-label={t(locale, "common.clearSearch")}><ProductionIcon name="close" size={18} /></button>}
          </label>
        </section>

        <a className="home-chat-entry" href={productionRouteHref("chat")}>
          <span className="home-chat-entry-icon"><ProductionIcon name="conversations" size={20} /></span>
          <span className="home-chat-entry-copy">
            <strong>{t(locale, "chat.title")}</strong>
            <small>{t(locale, "chat.subtitle")}</small>
          </span>
          <ProductionIcon name="send" className="home-chat-entry-action" size={20} />
        </a>

        <section className="home-results-panel" aria-label={t(locale, "common.search")}>
          <ProductionDataSourceBadge source={dataSource} locale={locale} />
          <ProductionLifecycleRegion
            className="surface-notices"
            phase={refresh.phase}
            hasSavedData={refresh.hasSavedData}
            locale={locale}
            lastSuccessAgeMs={lastSuccessAgeMs}
            nextAction={refreshFailed && canRetry ? t(locale, "common.retry") : null}
            retry={refreshFailed && canRetry ? { onRetry: retry } : null}
          />
          <ProductionLiveAnnouncement
            message={t(locale, filtering ? "home.matchCount" : "home.loadedCount", { count: formatNumber(results.length, locale) })}
            {...(announcementScheduler ? { scheduler: announcementScheduler } : {})}
          />
          <header className="home-results-header">
            <div className="home-kind-filter" role="group" aria-label={t(locale, "common.search")}>
              {(["all", "conversation", "memory"] as const).map((value) => <button type="button" key={value} aria-pressed={kind === value} onClick={() => setKind(value)}>
                {value === "all" ? t(locale, "conversations.all") : value === "memory" ? t(locale, "nav.memories") : t(locale, "nav.conversations")}
              </button>)}
              <button type="button" aria-disabled="true" disabled>{t(locale, "nav.rewind")}</button>
            </div>
            <span className="home-result-count">{t(locale, filtering ? "home.matchCount" : "home.loadedCount", { count: formatNumber(results.length, locale) })}</span>
          </header>
          {presentation.showsSavedRows ? (
            <div className="home-result-spine">
              {results.map((row) => {
                const date = formatDate(row.timestamp, locale, { dateStyle: "medium" });
                if (row.kind === "memory") return <article className="home-result-row" data-actionable="false" key={`memory:${row.value.id}`}>
                  <span className="home-result-icon is-memory"><ProductionIcon name="library" size={18} /></span>
                  <div className="home-result-copy"><p>{presentMemoryContent(row.value.content).body}</p><small>{[t(locale, "nav.memories"), date].join(" · ")}</small></div>
                </article>;
                if (row.kind === "conversation") return <a className="home-result-row" href={conversationHref(row.value.id)} key={`conversation:${row.value.id}`}>
                  <span className="home-result-icon is-conversation"><ProductionIcon name="conversations" size={18} /></span>
                  <div className="home-result-copy"><p>{row.value.title || t(locale, "conversations.untitled")}</p><small>{[t(locale, "nav.conversations"), date, row.value.overview].filter(Boolean).join(" · ")}</small></div>
                </a>;
              })}
            </div>
          ) : presentation.emptyKind === "filtered-out" ? (
            <div className="home-no-results" data-empty-kind="filtered-out">
              <p>{t(locale, "common.noResults")}</p>
              {needle && <button type="button" onClick={() => { setQuery(""); searchRef.current?.focus(); }}>{t(locale, "common.clearSearch")}</button>}
            </div>
          ) : presentation.emptyKind === "empty-projection" ? (
            <div className="home-no-results" data-empty-kind="empty-projection">
              <p>{t(locale, "home.startTyping")}</p>
            </div>
          ) : null}
        </section>
      </div>
      <ProductionChrome locale={locale} active="home" placement="bottom" />
    </main>
  );
}
