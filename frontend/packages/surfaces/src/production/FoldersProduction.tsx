import { useCallback, useEffect, useRef, useState } from "react";
import { t } from "@omi-core/i18n";
import type { Folder } from "@omi-core/contracts";
import type { ProductionFolderStore } from "./ProductionStores.js";
import { ProductionChrome } from "./ProductionChrome.js";

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
  return (
    <main
      className="production-shell"
      data-production-shell="true"
      data-route="folders"
      data-surface-state={status.refresh.phase}
      data-qa-fixture="none"
      data-consumer-semantic={`folders:visible:${visible.length}:total:${folders.length}`}
    >
      <ProductionChrome locale={locale} active="folders" placement="top" />
      <section className="desktop-page-panel">
        <header className="production-header">
          <div>
            <p className="eyebrow">{t(locale, "conversations.folder")}</p>
            <h1>{t(locale, "conversations.folder")}</h1>
          </div>
        </header>
        {failed && <p className="empty-state">{t(locale, "lifecycle.unavailable")}</p>}
        {!failed && status.refresh.phase === "ready" && visible.length === 0 && (
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
