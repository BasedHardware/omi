import { useCallback, useEffect, useRef, useState } from "react";
import { t } from "@omi-core/i18n";
import type { Folder } from "@omi-core/contracts";
import type { ProductionFolderStore } from "./ProductionStores.js";
import { ProductionChrome } from "./ProductionChrome.js";
import { ProductionDataSourceBadge, ProductionLifecycleRegion, ProductionLiveAnnouncement, ProductionPageHeader } from "./ProductionPrimitives.js";

export function FoldersProduction({ store, locale = "en", onReady }: {
  store: ProductionFolderStore;
  locale?: string;
  onReady?: () => void;
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
      data-production-shell="true"
      data-route="folders"
      data-surface-state={phase}
      data-qa-fixture="none"
      data-consumer-semantic={`folders:visible:${visible.length}:total:${folders.length}`}
    >
      <ProductionChrome locale={locale} active="folders" placement="top" />
      <section className="desktop-page-panel">
        <ProductionPageHeader className="production-header" eyebrow={t(locale, "conversations.folder")} title={t(locale, "conversations.folder")} />
        <ProductionDataSourceBadge source={{ kind: "live", origin: "bridge" }} locale={locale} />
        <ProductionLifecycleRegion
          className="surface-notices"
          phase={phase}
          hasSavedData={hasSavedFolders}
          locale={locale}
          nextAction={phase !== "ready" ? t(locale, "common.retry") : null}
          retry={phase !== "ready" ? { onRetry: retry } : null}
        />
        <ProductionLiveAnnouncement message={t(locale, "lifecycle.resultsCount", { count: visible.length })} />
        {!failed && phase === "ready" && visible.length === 0 && (
          <p className="empty-state">{t(locale, "lifecycle.empty")}</p>
        )}
        {visible.length > 0 && (
          <ul className="conversation-list" aria-label={t(locale, "conversations.folder")}>
            {visible.map((folder) => <li className="conversation-row" key={folder.id}>{folder.name}</li>)}
          </ul>
        )}
      </section>
      <ProductionChrome locale={locale} active="folders" placement="bottom" />
    </main>
  );
}
