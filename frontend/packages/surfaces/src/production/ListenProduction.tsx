import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { formatDuration, t, type MessageKey } from "@omi-core/i18n";
import type { PlatformListenPreflightSnapshot } from "@omi-core/adapters-platform";
import type { ListenEntitlementSnapshot, TranscriptSegment } from "@omi-core/wire-listen";
import type { ProductionListenStore } from "./ProductionListenStore.js";
import type { CaptureState } from "./capture-state.js";
import { backlogHours, describeCapture } from "./capture-state.js";
import { ProductionChrome } from "./ProductionChrome.js";
import { ProductionDataSourceBadge, ProductionLifecycleRegion, ProductionLiveAnnouncement, ProductionPageHeader, type ProductionAnnouncementScheduler } from "./ProductionPrimitives.js";
import { boundedRenderedTranscript } from "./consumer-observation.js";
import "./listen.css";

type Locale = string;
type RunOperation = (operation: () => Promise<void>) => Promise<boolean>;

const LISTEN_LIVE_EDGE_PX = 24;
const LEGACY_PREFLIGHT: PlatformListenPreflightSnapshot = {
  permission: "granted",
  device: { state: "available", label: null },
  recovery: null,
};

function preflightPermissionLabel(locale: Locale, state: PlatformListenPreflightSnapshot["permission"]): string {
  const key = `listen.permission.${state}` as MessageKey;
  return t(locale, key, {} as never);
}

function preflightDeviceLabel(locale: Locale, state: PlatformListenPreflightSnapshot["device"]["state"]): string {
  const key = `listen.device.${state}` as MessageKey;
  return t(locale, key, {} as never);
}

function listenScrollTarget(transcript: HTMLElement): HTMLElement {
  if (transcript.ownerDocument.documentElement.dataset["platform"] === "mobile") {
    return transcript.ownerDocument.scrollingElement as HTMLElement | null ?? transcript;
  }
  return transcript;
}

function isAtListenLiveEdge(target: HTMLElement): boolean {
  return target.scrollHeight - target.scrollTop - target.clientHeight <= LISTEN_LIVE_EDGE_PX;
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
  const [showLatest, setShowLatest] = useState(false);
  const [announceTranscript, setAnnounceTranscript] = useState(true);
  const [listenAnnouncement, setListenAnnouncement] = useState<string | null>(null);
  const [preflight, setPreflight] = useState<PlatformListenPreflightSnapshot>(() => store.preflight?.() ?? LEGACY_PREFLIGHT);
  const readyRef = useRef(false);
  const onReadyRef = useRef(onReady);
  const transcriptRef = useRef<HTMLElement>(null);
  const followingLatestRef = useRef(true);
  const touchYRef = useRef<number | null>(null);
  const announcedCaptureKindRef = useRef<CaptureState["kind"] | null>(null);
  const announcedSegmentsRef = useRef(new Map<string, string>());
  useEffect(() => { onReadyRef.current = onReady; }, [onReady]);

  const reload = useCallback(async (): Promise<void> => {
    try {
      setCapture(store.captureState());
      setSegments(store.transcriptSegments());
      setEntitlement(store.entitlementState());
      setPreflight(store.preflight?.() ?? LEGACY_PREFLIGHT);
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

  const jumpToLatest = useCallback((): void => {
    const transcript = transcriptRef.current;
    if (!transcript) return;
    const target = listenScrollTarget(transcript);
    target.scrollTop = target.scrollHeight;
    followingLatestRef.current = true;
    setShowLatest(false);
  }, []);

  const leaveLiveEdge = useCallback((): void => {
    followingLatestRef.current = false;
    setShowLatest(true);
  }, []);

  const updateFollowing = useCallback((target: HTMLElement): void => {
    const atEdge = isAtListenLiveEdge(target);
    followingLatestRef.current = atEdge;
    setShowLatest(!atEdge);
  }, []);

  useLayoutEffect(() => {
    if (segments.length === 0 || !followingLatestRef.current) return;
    jumpToLatest();
  }, [jumpToLatest, segments]);

  useEffect(() => {
    const transcript = transcriptRef.current;
    const ResizeObserverConstructor = transcript?.ownerDocument.defaultView?.ResizeObserver;
    if (!transcript || !ResizeObserverConstructor) return;
    const observer = new ResizeObserverConstructor(() => {
      if (followingLatestRef.current) jumpToLatest();
    });
    observer.observe(transcript);
    for (const row of transcript.children) observer.observe(row);
    return () => observer.disconnect();
  }, [jumpToLatest, segments.length]);

  useEffect(() => {
    const transcript = transcriptRef.current;
    if (!transcript) return;
    const target = listenScrollTarget(transcript);
    const update = (): void => updateFollowing(target);
    target.addEventListener("scroll", update, { passive: true });
    return () => target.removeEventListener("scroll", update);
  }, [segments.length, updateFollowing]);

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
  const entitlementAllowsCapture = entitlement === null || entitlement.captureContinuing;
  const captureReady = preflight.permission === "granted"
    && preflight.device.state === "available"
    && entitlementAllowsCapture;
  const canRetryRefresh = !(
    presentedCapture.kind === "stopped-at-ceiling"
    || (presentedCapture.kind === "error" && !presentedCapture.retryable)
  );
  useEffect(() => {
    const nextSegmentMap = new Map<string, string>();
    const changedSegments: TranscriptSegment[] = [];
    for (const [index, segment] of segments.entries()) {
      const key = transcriptKey(segment, index);
      nextSegmentMap.set(key, segment.text);
      if (announcedSegmentsRef.current.get(key) !== segment.text) changedSegments.push(segment);
    }
    announcedSegmentsRef.current = nextSegmentMap;
    const stateChanged = announcedCaptureKindRef.current !== presentedCapture.kind;
    announcedCaptureKindRef.current = presentedCapture.kind;
    const parts = [
      stateChanged && !description.loud ? t(locale, description.titleKey) : null,
      announceTranscript ? transcriptAnnouncement(changedSegments) : null,
    ].filter((part): part is string => Boolean(part));
    if (parts.length > 0) setListenAnnouncement(parts.join(" · "));
  }, [announceTranscript, description.loud, description.titleKey, locale, presentedCapture.kind, segments]);

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
        <ProductionPageHeader className="production-header listen-header" eyebrow={t(locale, "listen.title")} title={t(locale, "listen.title")} description={t(locale, "listen.subtitle")} />
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
          {description.backlogSeconds > 0 && (
            <div className="listen-backlog" aria-label={t(locale, "listen.backlogLabel")}>
              <span className="listen-backlog-label">{t(locale, "listen.backlogLabel")}</span>
              <span className="listen-backlog-value">{t(locale, "listen.backlogHours", { hours })}</span>
            </div>
          )}
        </section>
        <section className="listen-preflight" aria-labelledby="listen-preflight-title">
          <h2 id="listen-preflight-title">{t(locale, "listen.preflightTitle")}</h2>
          <dl>
            <div>
              <dt>{t(locale, "listen.permissionLabel")}</dt>
              <dd data-permission-state={preflight.permission}>{preflightPermissionLabel(locale, preflight.permission)}</dd>
            </div>
            <div>
              <dt>{t(locale, "listen.deviceLabel")}</dt>
              <dd data-device-state={preflight.device.state}>
                {preflight.device.label ?? preflightDeviceLabel(locale, preflight.device.state)}
              </dd>
            </div>
            <div>
              <dt>{t(locale, "listen.entitlementLabel")}</dt>
              <dd data-entitlement-state={entitlement ? "checked" : "pending"}>
                {entitlement === null
                  ? t(locale, "listen.entitlementPending")
                  : entitlement.captureContinuing
                    ? t(locale, "listen.entitlementAvailable")
                    : t(locale, "listen.entitlementLimited")}
              </dd>
            </div>
          </dl>
          {preflight.recovery === "request-permission" && store.requestPermission && (
            <button type="button" className="listen-recovery-control" onClick={() => void run(store.requestPermission!)}>
              {t(locale, "listen.requestPermission")}
            </button>
          )}
          {preflight.recovery === "open-settings" && store.openSettings && (
            <button type="button" className="listen-recovery-control" onClick={() => void run(store.openSettings!)}>
              {t(locale, "listen.openSettings")}
            </button>
          )}
        </section>
        {description.loud && (
          <p className="visually-hidden" role="alert">{t(locale, description.titleKey)}</p>
        )}
        <ProductionLiveAnnouncement message={listenAnnouncement} {...(announcementScheduler ? { scheduler: announcementScheduler } : {})} />
        {presentedCapture.kind === "capturing" && segments.length === 0 && (
          <p className="listen-transcript-waiting">{t(locale, "listen.transcriptWaiting")}</p>
        )}
        {segments.length > 0 && (
          <section
            ref={transcriptRef}
            className="listen-transcript"
            aria-label={t(locale, "listen.title")}
            data-transcript-count={segments.length}
            tabIndex={0}
            onScroll={(event) => updateFollowing(event.currentTarget)}
            onWheel={(event) => { if (event.deltaY < 0) leaveLiveEdge(); }}
            onTouchStart={(event) => { touchYRef.current = event.touches[0]?.clientY ?? null; }}
            onTouchMove={(event) => {
              const nextY = event.touches[0]?.clientY ?? null;
              if (nextY !== null && touchYRef.current !== null && nextY > touchYRef.current) leaveLiveEdge();
              touchYRef.current = nextY;
            }}
            onTouchEnd={() => { touchYRef.current = null; }}
            onKeyDown={(event) => {
              if (["ArrowUp", "PageUp", "Home"].includes(event.key)) leaveLiveEdge();
            }}
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
        {showLatest && segments.length > 0 && (
          <button type="button" className="listen-jump-latest" onClick={jumpToLatest}>
            {t(locale, "chat.latest")}
          </button>
        )}
        <p className="listen-privacy-note" data-capture-indicator={description.capturing ? "active" : "idle"}>
          {t(locale, description.capturing ? "listen.privacyActive" : "listen.privacyControl")}
        </p>
        <div className="listen-controls" role="group" aria-label={t(locale, "listen.stateLabel")}>
          {description.canStart && (
            <button
              type="button"
              className="listen-primary-control"
              data-consumer-action="start-listen"
              aria-label={t(locale, "listen.start")}
              disabled={!captureReady}
              aria-disabled={!captureReady}
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
          <button
            type="button"
            className="listen-announcement-control"
            aria-pressed={announceTranscript}
            onClick={() => setAnnounceTranscript((current) => !current)}
          >
            {t(locale, announceTranscript ? "listen.transcriptAnnouncementsOn" : "listen.transcriptAnnouncementsOff")}
          </button>
        </div>
      </section>
      <ProductionChrome locale={locale} active="listen" placement="bottom" />
    </main>
  );
}
