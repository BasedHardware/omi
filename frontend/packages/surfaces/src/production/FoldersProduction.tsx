import { useCallback, useEffect, useRef, useState } from "react";
import { t } from "@omi-core/i18n";
import type { Folder } from "@omi-core/contracts";
import type { ProductionFolderStore } from "./ProductionStores.js";
import { ProductionChrome } from "./ProductionChrome.js";
import { ProductionDataSourceBadge, ProductionEmptyState, ProductionLifecycleRegion, ProductionLiveAnnouncement, ProductionNotice, ProductionPageHeader, type SurfaceDataSource } from "./ProductionPrimitives.js";
import { ProductionIcon } from "./ProductionIcon.js";
import "./folders.css";

const FOLDER_NOTICE_TONE = "info" as const;
const FOLDER_EMPTY_ICON = "library" as const;

export function foldersConversationHref(search: string, folderId?: Folder["id"]): string {
  const params = new URLSearchParams(search);
  params.delete("conversation");
  params.delete("qa");
  params.delete("state");
  params.delete("folder");
  params.set("route", "conversations");
  if (folderId) params.set("folder", folderId);
  return `?${params.toString()}`;
}

export function FoldersProduction({ store, locale = "en", onReady, source = { kind: "live", origin: "bridge" }, fixture }: {
  store: ProductionFolderStore;
  locale?: string;
  onReady?: () => void;
  source?: SurfaceDataSource;
  fixture?: string;
}): React.JSX.Element {
  const [folders, setFolders] = useState<Folder[]>([]);
  const [status, setStatus] = useState(store.status());
  const [failed, setFailed] = useState(false);
  const readyRef = useRef(false);
  const onReadyRef = useRef(onReady);
  useEffect(() => { onReadyRef.current = onReady; }, [onReady]);

  const reload = useCallback(async (): Promise<void> => {
    try {
      setFolders(await store.list());
      setFailed(false);
    } catch {
      setFailed(true);
    }
    setStatus(store.status());
  }, [store]);

  useEffect(() => {
    let active = true;
    const unsubscribe = store.subscribe(() => { if (active) void reload(); });
    void (async () => {
      await reload();
      try { await store.refresh(); } catch { setFailed(true); }
      await reload();
      if (active && !readyRef.current) {
        readyRef.current = true;
        onReadyRef.current?.();
      }
    })();
    return () => { active = false; unsubscribe(); };
  }, [reload, store]);

  const visible = folders.filter((folder) => !folder.isSystem);
  const hasSavedFolders = status.refresh.hasSavedData || folders.length > 0;
  // A transient list read failure must not erase a saved projection. Preserve
  // the rows and expose the stale-data phase while there is something truthful
  // to show; only an empty failed read is unavailable.
  const phase = failed
    ? hasSavedFolders ? "saved-but-refresh-failed" : "unavailable"
    : status.refresh.phase;
  const retry = async (): Promise<void> => {
    try { await store.refresh(); } catch { /* status() remains the truthful failure source */ }
    await reload();
  };
  return (
    <main
      className="production-shell"
      aria-label={t(locale, "nav.folders")}
      data-production-shell="true"
      data-route="folders"
      data-surface-state={phase}
      data-qa-fixture={fixture ?? "none"}
      data-consumer-semantic={`folders:visible:${visible.length}:total:${folders.length}`}
    >
      <ProductionChrome locale={locale} active="folders" placement="top" />
      <section className="desktop-page-panel">
        <ProductionPageHeader
          className="production-header"
          eyebrow={t(locale, "folders.eyebrow")}
          title={t(locale, "nav.folders")}
          description={t(locale, "folders.description")}
        />
        <ProductionDataSourceBadge source={source} locale={locale} />
        <ProductionLifecycleRegion
          className="surface-notices"
          phase={phase}
          hasSavedData={hasSavedFolders}
          locale={locale}
          nextAction={phase !== "ready" ? t(locale, "common.retry") : null}
          retry={phase !== "ready" ? { onRetry: retry } : null}
        />
        <ProductionLiveAnnouncement message={t(locale, "lifecycle.resultsCount", { count: visible.length })} />
        <ProductionNotice
          tone={FOLDER_NOTICE_TONE}
          title={t(locale, "folders.readOnlyTitle")}
          detail={t(locale, "folders.readOnlyDetail")}
        />
        {!failed && phase === "ready" && visible.length === 0 && (
          <ProductionEmptyState
            icon={FOLDER_EMPTY_ICON}
            title={t(locale, "folders.emptyTitle")}
            detail={t(locale, "folders.emptyDetail")}
            action={<a className="folders-all-link" href={foldersConversationHref(location.search)}>{t(locale, "folders.openConversations")}</a>}
          />
        )}
        {visible.length > 0 && (
          <ul className="folders-list" aria-label={t(locale, "nav.folders")}>
            {visible.map((folder) => (
              <li key={folder.id}>
                <a className="folder-row" href={foldersConversationHref(location.search, folder.id)}>
                  <span className="folder-row-icon"><ProductionIcon name="library" /></span>
                  <span className="folder-row-copy">
                    <strong>{folder.name}</strong>
                    <small>{folder.description?.trim() || t(locale, "folders.open")}</small>
                  </span>
                  <span className="folder-row-action">{t(locale, "folders.open")}</span>
                </a>
              </li>
            ))}
          </ul>
        )}
      </section>
      <ProductionChrome locale={locale} active="folders" placement="bottom" />
    </main>
  );
}
