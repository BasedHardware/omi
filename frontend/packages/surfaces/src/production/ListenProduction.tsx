import { useCallback, useEffect, useRef, useState } from "react";
import { formatDuration, t } from "@omi-core/i18n";
import type { ListenEntitlementSnapshot, TranscriptSegment } from "@omi-core/wire-listen";
import type { ProductionListenStore } from "./ProductionListenStore.js";
import type { CaptureState } from "./capture-state.js";
import { backlogHours, describeCapture } from "./capture-state.js";
import { ProductionChrome } from "./ProductionChrome.js";
import { ProductionDataSourceBadge, ProductionLifecycleRegion, ProductionLiveAnnouncement, type ProductionAnnouncementScheduler } from "./ProductionPrimitives.js";
import { boundedRenderedTranscript } from "./consumer-observation.js";
import "./listen.css";

type Locale = string;
type RunOperation = (operation: () => Promise<void>) => Promise<boolean>;

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

function transcriptAnnouncement(segments: readonly TranscriptSegment[]): string | null {
  if (segments.length === 0) return null;
  const text = segments.slice(-3).map((segment) => segment.text.trim()).filter(Boolean).join(" ");
  if (!text) return null;
  const bounded = Array.from(text).slice(0, 240).join("");
  return bounded === text ? bounded : `${bounded}…`;
}

export function ListenProduction({ store, locale = "en", onReady, announcementScheduler }: {
  store: ProductionListenStore;
  locale?: Locale;
  onReady?: () => void;
  announcementScheduler?: ProductionAnnouncementScheduler;
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
  const listenAnnouncement = [
    t(locale, description.titleKey),
    segments.length > 0 ? t(locale, "lifecycle.resultsCount", { count: segments.length }) : null,
    transcriptAnnouncement(segments),
  ].filter(Boolean).join(" · ");

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
        </header>
        <ProductionDataSourceBadge source={{ kind: "live", origin: "bridge" }} locale={locale} />
        <ProductionLifecycleRegion
          className="surface-notices"
          phase={status.refresh.phase}
          hasSavedData={status.refresh.hasSavedData}
          locale={locale}
          queue={status.queue}
          operationError={operationError}
          nextAction={status.refresh.phase !== "ready" && canRetryRefresh ? t(locale, "common.retry") : null}
          retry={status.refresh.phase !== "ready" && canRetryRefresh ? { onRetry: async () => { await run(() => store.refresh()); } } : null}
        />
        <section
          className={`listen-state-panel${description.loud ? " is-loud" : ""}${description.capturing ? " is-capturing" : ""}`}
          aria-label={t(locale, "listen.stateLabel")}
          data-loud={description.loud ? "true" : "false"}
          data-capturing={description.capturing ? "true" : "false"}
          data-presentation={presentedCapture.kind}
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
        <ProductionLiveAnnouncement message={listenAnnouncement} {...(announcementScheduler ? { scheduler: announcementScheduler } : {})} />
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
        <div className="listen-controls" role="group" aria-label={t(locale, "listen.stateLabel")}>
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
