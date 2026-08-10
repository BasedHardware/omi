import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { formatDuration, t } from "@omi-core/i18n";
import type { StoreStatus } from "@omi-core/domain";
import type { ListenEntitlementSnapshot, TranscriptSegment } from "@omi-core/wire-listen";
import type { ProductionListenStore } from "./ProductionListenStore.js";
import type { CaptureState } from "./capture-state.js";
import { backlogHours, describeCapture } from "./capture-state.js";
import { refreshPhaseNoticeKey } from "./lifecycle-presentation.js";
import { ProductionChrome } from "./ProductionChrome.js";
import { boundedRenderedTranscript } from "./consumer-observation.js";
import "./listen.css";

type Locale = string;
type RunOperation = (operation: () => Promise<void>) => Promise<boolean>;

function phaseLabel(status: StoreStatus, locale: Locale): string | null {
  const key = refreshPhaseNoticeKey(status.refresh.phase);
  return key === null ? null : t(locale, key);
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

function bufferedSeconds(state: CaptureState): number | null {
  return state.kind === "offline-buffering" ? state.bufferedSeconds : null;
}

function entitlementUsageLabel(
  entitlement: ListenEntitlementSnapshot | null,
  locale: Locale,
): string | null {
  if (entitlement?.usage === null || entitlement?.usage === undefined) return null;
  const used = formatDuration(entitlement.usage.amount, locale);
  switch (entitlement.limit.kind) {
    case "metered":
      return t(locale, "settings.usageOf", {
        used,
        limit: formatDuration(entitlement.limit.amount, locale),
      });
    case "unmetered":
      return t(locale, "settings.usageUnmetered", { used });
    case "unknown":
      return t(locale, "listen.usageUnknownLimit", { used });
    default: {
      const _exhaustive: never = entitlement.limit;
      throw new Error(`unhandled entitlement limit: ${JSON.stringify(_exhaustive)}`);
    }
  }
}

function transcriptKey(segment: TranscriptSegment, index: number): string {
  return segment.id && segment.id !== ""
    ? segment.id
    : `anonymous-${segment.start}-${segment.end}-${index}`;
}

export function ListenProduction({ store, locale = "en", onReady }: {
  store: ProductionListenStore;
  locale?: Locale;
  onReady?: () => void;
}): React.JSX.Element {
  const [capture, setCapture] = useState<CaptureState>(() => store.captureState());
  const [segments, setSegments] = useState<readonly TranscriptSegment[]>(() => store.transcriptSegments());
  const [entitlement, setEntitlement] = useState<ListenEntitlementSnapshot | null>(() => store.entitlementState());
  const [status, setStatus] = useState(store.status());
  const [operationError, setOperationError] = useState<string | null>(null);
  const readyRef = useRef(false);
  const onReadyRef = useRef(onReady);
  useEffect(() => { onReadyRef.current = onReady; }, [onReady]);

  const reload = useCallback(async (): Promise<void> => {
    try {
      setCapture(store.captureState());
      setSegments(store.transcriptSegments());
      setEntitlement(store.entitlementState());
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

  const presentedCapture: CaptureState =
    (status.refresh.phase === "initial-loading" || status.refresh.phase === "refreshing")
    && capture.kind === "idle"
      ? { kind: "loading" }
      : capture;
  const description = describeCapture(presentedCapture);
  const elapsed = elapsedSeconds(presentedCapture);
  const buffered = bufferedSeconds(presentedCapture);
  const hours = backlogHours(description.backlogSeconds);
  const usageLabel = entitlementUsageLabel(entitlement, locale);
  const canRetryRefresh = !(
    presentedCapture.kind === "stopped-at-ceiling"
    || (presentedCapture.kind === "error" && !presentedCapture.retryable)
  );

  return (
    <main
      className="production-shell listen-production-shell"
      data-production-shell="true"
      data-route="listen"
      data-surface-state={status.refresh.phase}
      data-capture-kind={presentedCapture.kind}
      data-qa-fixture="none"
      data-consumer-semantic={`listen:capture:${presentedCapture.kind}:segments:${segments.length}`}
      data-consumer-transcript={segments.length > 0 ? boundedRenderedTranscript(segments) : undefined}
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
            {status.refresh.phase !== "ready" && canRetryRefresh && (
              <button type="button" onClick={() => void run(() => store.refresh())} aria-label={t(locale, "common.retry")}>
                {t(locale, "common.retry")}
              </button>
            )}
          </div>
        </header>
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
          data-presentation={presentedCapture.kind}
          role={description.loud ? "alert" : "status"}
        >
          <div className={`listen-state-glyph is-${presentedCapture.kind}`} aria-hidden="true">
            <span className="listen-state-glyph-core" />
            <span className="listen-state-glyph-ring" />
          </div>
          <div className="listen-state-copy">
            <h2 className="listen-state-title">{t(locale, description.titleKey)}</h2>
            <p className="listen-state-body">{t(locale, description.bodyKey)}</p>
            {elapsed !== null && (
              <p className="listen-elapsed">{t(locale, "listen.elapsed", { duration: formatDuration(elapsed, locale) })}</p>
            )}
            {buffered !== null && (
              <p className="listen-buffered">{t(locale, "listen.buffered", { duration: formatDuration(buffered, locale) })}</p>
            )}
            {usageLabel && <p className="listen-entitlement-usage">{usageLabel}</p>}
          </div>
          <div className="listen-backlog" aria-label={t(locale, "listen.backlogLabel")}>
            <span className="listen-backlog-label">{t(locale, "listen.backlogLabel")}</span>
            <span className="listen-backlog-value">
              {description.backlogSeconds > 0
                ? t(locale, "listen.backlogHours", { hours })
                : t(locale, "listen.backlogNone")}
            </span>
          </div>
        </section>
        {segments.length > 0 && (
          <section
            className="listen-transcript"
            aria-label={t(locale, "listen.title")}
            data-transcript-count={segments.length}
          >
            {segments.map((segment, index) => (
              <article
                className={`listen-transcript-row${segment.is_user ? " is-user" : ""}`}
                data-segment-id={segment.id ?? ""}
                key={transcriptKey(segment, index)}
              >
                {segment.speaker && <p className="listen-transcript-speaker">{segment.speaker}</p>}
                <p className="listen-transcript-text">{segment.text}</p>
              </article>
            ))}
          </section>
        )}
        <div className="listen-controls" aria-label={t(locale, "listen.stateLabel")}>
          {description.canStart && (
            <button
              type="button"
              className="listen-primary-control"
              data-consumer-action="start-listen"
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
