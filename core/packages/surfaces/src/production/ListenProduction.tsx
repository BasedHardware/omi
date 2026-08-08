import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { formatDuration, t } from "@omi-core/i18n";
import type { StoreStatus } from "@omi-core/domain";
import type { ProductionListenStore } from "./ProductionListenStore.js";
import type { CaptureState } from "./capture-state.js";
import { backlogHours, describeCapture } from "./capture-state.js";
import { ProductionChrome } from "./ProductionChrome.js";
import { ProductionDataSourceBadge } from "./ProductionPrimitives.js";
import "./listen.css";

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

function elapsedSeconds(state: CaptureState): number | null {
  switch (state.kind) {
    case "capturing":
    case "paused-for-entitlement":
    case "offline-buffering":
      return state.elapsedSeconds;
    default:
      return null;
  }
}

export function ListenProduction({ store, fixture, locale = "en", onReady }: {
  store: ProductionListenStore;
  fixture?: string;
  locale?: Locale;
  onReady?: () => void;
}): React.JSX.Element {
  const [capture, setCapture] = useState<CaptureState>(() => store.captureState());
  const [status, setStatus] = useState(store.status());
  const [operationError, setOperationError] = useState<string | null>(null);
  const readyRef = useRef(false);
  const onReadyRef = useRef(onReady);
  useEffect(() => { onReadyRef.current = onReady; }, [onReady]);

  const reload = useCallback(async (): Promise<void> => {
    try {
      setCapture(store.captureState());
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

  const description = describeCapture(capture);
  const elapsed = elapsedSeconds(capture);
  const hours = backlogHours(description.backlogSeconds);

  return (
    <main
      className="production-shell listen-production-shell"
      data-production-shell="true"
      data-route="listen"
      data-surface-state={status.refresh.phase}
      data-qa-fixture={fixture ?? "none"}
      data-capture-kind={capture.kind}
    >
      <ProductionChrome locale={locale} active="listen" placement="top" />
      <section className="desktop-page-panel">
        <header className="production-header listen-header">
          <div>
            <p className="eyebrow">{t(locale, "listen.title")}</p>
            <h1>{t(locale, "listen.title")}</h1>
            <p>{t(locale, "listen.subtitle")}</p>
          </div>
          <div className="header-actions">
            {status.refresh.phase !== "ready" && (
              <button type="button" onClick={() => void run(() => store.refresh())} aria-label={t(locale, "common.retry")}>
                {t(locale, "common.retry")}
              </button>
            )}
          </div>
        </header>
        {fixture && <ProductionDataSourceBadge source={{ kind: "fixture", fixture }} locale={locale} />}
        <div className="surface-notices" aria-live="polite">
          {notice && <div className={`status-notice ${status.refresh.phase}`} role="status">{notice}</div>}
          {queueLabel && <div className={`queue-notice ${status.queue.phase}`} role="status">{queueLabel}</div>}
          {operationError && <div className="operation-error" role="alert">{operationError}</div>}
        </div>
        <section
          className={`listen-state-panel${description.loud ? " is-loud" : ""}${description.capturing ? " is-capturing" : ""}`}
          aria-label={t(locale, "listen.stateLabel")}
          data-loud={description.loud ? "true" : "false"}
          data-capturing={description.capturing ? "true" : "false"}
          role={description.loud ? "alert" : "status"}
        >
          <h2 className="listen-state-title">{t(locale, description.titleKey)}</h2>
          <p className="listen-state-body">{t(locale, description.bodyKey)}</p>
          {elapsed !== null && (
            <p className="listen-elapsed">{t(locale, "listen.elapsed", { duration: formatDuration(elapsed, locale) })}</p>
          )}
          <div className="listen-backlog" aria-label={t(locale, "listen.backlogLabel")}>
            <span className="listen-backlog-label">{t(locale, "listen.backlogLabel")}</span>
            <span className="listen-backlog-value">
              {description.backlogSeconds > 0
                ? t(locale, "listen.backlogHours", { hours })
                : t(locale, "listen.backlogNone")}
            </span>
          </div>
        </section>
        <div className="listen-controls" aria-label={t(locale, "listen.stateLabel")}>
          {description.canStart && (
            <button
              type="button"
              className="listen-primary-control"
              aria-label={t(locale, "listen.start")}
              onClick={() => void run(() => store.start())}
            >
              {t(locale, "listen.start")}
            </button>
          )}
          {description.canStop && (
            <button
              type="button"
              className="listen-primary-control listen-stop-control"
              aria-label={t(locale, "listen.stop")}
              onClick={() => void run(() => store.stop())}
            >
              {t(locale, "listen.stop")}
            </button>
          )}
        </div>
      </section>
      <ProductionChrome locale={locale} active="listen" placement="bottom" />
    </main>
  );
}
