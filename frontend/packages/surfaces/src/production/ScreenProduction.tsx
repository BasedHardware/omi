import { useCallback, useEffect, useId, useRef, useState } from "react";
import { formatDate, t } from "@omi-core/i18n";
import type { ScreenOcrBlock, ScreenTextSearchHit } from "@omi-core/adapters-platform";
import type { ProductionScreenStore, ScreenFrameImageState } from "./ProductionScreenStore.js";
import {
  highlightRectsFor,
  screenActivityBlocks,
  screenAdjacentAppIndex,
  screenAppColor,
  screenAppMonogram,
  screenDaySpanKind,
  screenNearestFrameIndex,
  snippetParts,
  SCREEN_PLAYBACK_RATES,
  SCREEN_TRACK_ASSUMED_WIDTH,
  screenPausedMessageKey,
  screenTrackBadges,
  screenTrackRange,
  screenTrackTickFormat,
  screenTrackTickStepMs,
  screenTrackTicks,
  type ScreenEmptyKind,
  type ScreenPlaybackRate,
} from "./screen-presentation.js";
import type { ScreenTimelineFrame } from "@omi-core/adapters-platform";
import { ProductionChrome } from "./ProductionChrome.js";
import { ProductionIcon } from "./ProductionIcon.js";
import {
  ProductionDataSourceBadge,
  ProductionDisabledControl,
  ProductionEmptyState,
  ProductionLifecycleRegion,
  ProductionLiveAnnouncement,
  ProductionPageHeader,
  ProductionSearchField,
  type SurfaceDataSource,
} from "./ProductionPrimitives.js";
import "./screen.css";

type Locale = string;
type RunOperation = (operation: () => Promise<void>) => Promise<boolean>;
const SCREEN_EMPTY_ICON = "screen" as const;

function frameTimestamp(iso: string, locale: Locale): string {
  const ms = Date.parse(iso);
  if (!Number.isFinite(ms)) return iso;
  return formatDate(ms, locale, { dateStyle: "medium", timeStyle: "short" });
}

function emptyCopy(kind: ScreenEmptyKind, locale: Locale): { title: string; detail: string } {
  switch (kind) {
    case "never-enabled":
      return { title: t(locale, "screen.emptyNeverEnabledTitle"), detail: t(locale, "screen.emptyNeverEnabledBody") };
    case "permission-denied":
      return { title: t(locale, "screen.emptyPermissionDeniedTitle"), detail: t(locale, "screen.emptyPermissionDeniedBody") };
    case "day-empty":
      return { title: t(locale, "screen.emptyDayTitle"), detail: t(locale, "screen.emptyDayBody") };
    case "search-miss":
      return { title: t(locale, "screen.emptySearchTitle"), detail: t(locale, "screen.emptySearchBody") };
  }
}

function frameImageSrc(image: ScreenFrameImageState): string | null {
  if (image.kind !== "ready") return null;
  return `data:image/png;base64,${image.image.pngBase64}`;
}

function HighlightedSnippet({ snippet }: { snippet: string }): React.JSX.Element {
  return (
    <>
      {snippetParts(snippet).map((part, index) => (
        part.matched
          ? <mark key={`${index}:${part.text}`}>{part.text}</mark>
          : <span key={`${index}:${part.text}`}>{part.text}</span>
      ))}
    </>
  );
}

function FrameHighlights({
  blocks,
  matchedIds,
}: {
  blocks: readonly ScreenOcrBlock[];
  matchedIds: readonly string[];
}): React.JSX.Element | null {
  const rects = highlightRectsFor(blocks, matchedIds);
  if (rects.length === 0) return null;
  return (
    <ul className="screen-highlights" aria-hidden="true">
      {rects.map((rect) => (
        <li
          key={rect.id}
          className="screen-highlight"
          data-block-id={rect.id}
          style={{
            left: `${rect.x * 100}%`,
            top: `${rect.y * 100}%`,
            width: `${rect.w * 100}%`,
            height: `${rect.h * 100}%`,
          }}
        />
      ))}
    </ul>
  );
}

/**
 * The time-linear track, ported from `RewindTrackNSView`.
 *
 * The substantive change is the axis, not the paint. The `input[type=range]`
 * this replaces mapped a pixel to an *array index*, so a three-hour gap between
 * two captures occupied exactly the width of a three-second one: a lunch break
 * was invisible, and "drag left to go back in time" was not true, because how
 * far a pixel travelled depended on how densely that stretch happened to be
 * captured. Here x is the capture's instant over the visible window.
 *
 * The range input survives underneath, transparent. It is what gives the track
 * a role, a name, a value, and arrow keys; the drawing above is a picture of the
 * same state. Pointer events are handled on the wrapper instead, because the
 * input's own click-to-position is index-linear and would disagree with what is
 * drawn.
 */
function ScreenTrack({
  frames,
  cursor,
  locale,
  label,
  valueText,
  onSelectFrame,
  onStepFrame,
}: {
  frames: readonly ScreenTimelineFrame[];
  cursor: number;
  locale: Locale;
  label: string;
  valueText: string | null;
  onSelectFrame: (index: number) => void;
  onStepFrame: (delta: number) => void;
}): React.JSX.Element {
  const trackRef = useRef<HTMLDivElement>(null);
  const [trackWidth, setTrackWidth] = useState(SCREEN_TRACK_ASSUMED_WIDTH);

  useEffect(() => {
    const node = trackRef.current;
    if (node === null || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver((entries) => {
      const width = entries[0]?.contentRect.width ?? 0;
      if (width > 0) setTrackWidth(width);
    });
    observer.observe(node);
    return () => { observer.disconnect(); };
  }, []);

  const range = screenTrackRange(frames);
  const blocks = screenActivityBlocks(frames);
  const span = range === null ? 0 : range.endedAt - range.startedAt;
  const fraction = (instant: number): number => (span > 0 ? (instant - range!.startedAt) / span : 0);
  const percent = (instant: number): string => `${fraction(instant) * 100}%`;

  const badges = range === null ? [] : screenTrackBadges(blocks, range, trackWidth);
  const ticks = range === null ? [] : screenTrackTicks(range.startedAt, range.endedAt);
  const tickFormat = screenTrackTickFormat(screenTrackTickStepMs(span));
  const selectedInstant = Date.parse(frames[cursor]?.captured_at ?? "");
  const hasPlayhead = range !== null && Number.isFinite(selectedInstant);

  /** Maps a pointer x onto an instant, then onto the capture nearest it. */
  const selectAtClientX = (clientX: number): void => {
    const node = trackRef.current;
    if (node === null || range === null) return;
    const rect = node.getBoundingClientRect();
    if (rect.width <= 0) return;
    const ratio = Math.min(1, Math.max(0, (clientX - rect.left) / rect.width));
    const index = screenNearestFrameIndex(frames, range.startedAt + ratio * span);
    if (index !== null) onSelectFrame(index);
  };

  return (
    <div
      className="screen-track"
      ref={trackRef}
      data-track="true"
      onPointerDown={(event) => {
        event.currentTarget.setPointerCapture(event.pointerId);
        selectAtClientX(event.clientX);
      }}
      onPointerMove={(event) => {
        if (event.buttons === 0) return;
        selectAtClientX(event.clientX);
      }}
      onWheel={(event) => {
        event.preventDefault();
        onStepFrame(event.deltaY > 0 ? 1 : -1);
      }}
    >
      <div className="screen-track-bar">
        {range !== null && blocks.map((block, index) => (
          <div
            className="screen-track-block"
            data-track-app={block.app}
            key={`${block.app}:${block.startedAt}:${index}`}
            style={{
              left: percent(block.startedAt),
              // A sub-pixel block still happened; Swift floors it at 2px so it
              // is a visible sliver rather than nothing.
              width: `max(2px, ${(fraction(block.endedAt) - fraction(block.startedAt)) * 100}%)`,
              background: screenAppColor(block.app).css,
            }}
          />
        ))}
      </div>
      <div className="screen-track-badges" aria-hidden="true">
        {badges.map((badge) => (
          <span
            className="screen-track-badge"
            data-track-badge={badge.app}
            key={`${badge.app}:${badge.blockIndex}`}
            style={{
              left: `${badge.centerFraction * 100}%`,
              background: screenAppColor(badge.app).css,
            }}
          >
            {screenAppMonogram(badge.app)}
          </span>
        ))}
      </div>
      <div className="screen-track-ticks" aria-hidden="true">
        {ticks.map((tick) => (
          <span className="screen-track-tick" key={tick} style={{ left: percent(tick) }}>
            <span className="screen-track-tick-label">{formatDate(tick, locale, tickFormat)}</span>
          </span>
        ))}
      </div>
      {hasPlayhead && (
        <div
          className="screen-track-playhead"
          data-track-playhead="true"
          style={{ left: percent(selectedInstant) }}
        />
      )}
      <input
        className="screen-track-input"
        type="range"
        min={0}
        max={Math.max(0, frames.length - 1)}
        value={cursor}
        aria-label={label}
        {...(valueText === null ? {} : { "aria-valuetext": valueText })}
        disabled={frames.length === 0}
        onChange={(event) => onSelectFrame(Number(event.target.value))}
      />
    </div>
  );
}

export function ScreenProduction({ store, locale = "en", onReady, source = { kind: "live", origin: "bridge" }, fixture }: {
  store: ProductionScreenStore;
  locale?: Locale;
  onReady?: () => void;
  source?: SurfaceDataSource;
  fixture?: string;
}): React.JSX.Element {
  const [status, setStatus] = useState(store.status());
  const [operationError, setOperationError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [dayOpen, setDayOpen] = useState(false);
  const [tick, setTick] = useState(0);
  const readyRef = useRef(false);
  const onReadyRef = useRef(onReady);
  const searchRef = useRef<HTMLInputElement>(null);
  const dayPopoverId = useId();
  useEffect(() => { onReadyRef.current = onReady; }, [onReady]);

  const reload = useCallback(async (): Promise<void> => {
    setStatus(store.status());
    setTick((value) => value + 1);
  }, [store]);

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
  }, [reload, store]);

  const emptyKind = store.emptyKind();
  const frames = store.timeline();
  const selected = store.selectedFrame();
  const image = store.frameImage();
  const groups = store.searchGroups();
  const query = store.searchQuery();
  const capture = store.captureStatus();
  const permission = capture?.permission ?? store.permission();
  const engine = capture?.state ?? store.engineState();
  const bridgeAvailable = store.bridgeAvailable();
  const ocr = store.ocrForSelectedFrame();
  const matched = store.matchedBlockIds();
  const playing = store.playing();
  const rate = store.playbackRate();
  const cursor = store.frameCursor();
  const selectedDay = store.selectedDay();
  const days = store.days();
  const tone = store.captureTone();
  const extracted = ocr?.full_text ?? "";
  void tick;

  const copyExtracted = async (): Promise<void> => {
    if (extracted === "") return;
    try {
      await navigator.clipboard.writeText(extracted);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  };

  const permissionDenied = permission === "denied";
  const permissionUndetermined = permission === "undetermined";
  const permissionNeedsAction = bridgeAvailable && (permissionDenied || permissionUndetermined);
  const engineError = engine === "error";
  const recovering = engine === "starting";
  const paused = engine === "paused";
  const showRebuild = bridgeAvailable && engineError;
  const counterTotal = frames.length;
  const counterCurrent = counterTotal === 0 ? 0 : cursor + 1;
  const empty = emptyKind !== null ? emptyCopy(emptyKind, locale) : null;
  const selectedStamp = selected === null ? null : frameTimestamp(selected.captured_at, locale);
  const previousAppIndex = screenAdjacentAppIndex(frames, cursor, "previous");
  const nextAppIndex = screenAdjacentAppIndex(frames, cursor, "next");
  const daySpanKind = screenDaySpanKind({
    phase: status.refresh.phase,
    oldestCapturedAt: days.oldest_captured_at,
    newestCapturedAt: days.newest_captured_at,
  });

  return (
    <main
      className="production-shell screen-production-shell"
      aria-label={t(locale, "nav.rewind")}
      data-production-shell="true"
      data-route="screen"
      data-surface-state={status.refresh.phase}
      data-qa-fixture={fixture ?? "none"}
      data-empty-kind={emptyKind ?? "none"}
      data-capture-tone={tone}
      data-permission={permission ?? "undetermined"}
      data-engine-state={engine ?? "idle"}
      data-bridge={bridgeAvailable ? "present" : "absent"}
      data-playback-rate={String(rate)}
      data-frame-index={String(counterCurrent)}
      data-frame-total={String(counterTotal)}
      data-frame-image={image.kind}
      data-consumer-semantic={`screen:frames:${frames.length}:hits:${store.searchHits().length}:image:${image.kind}`}
    >
      <ProductionChrome
        locale={locale}
        active="rewind"
        placement="top"
        commandHandlers={{
          "rewind-frame-prev": () => store.stepFrame(-1),
          "rewind-frame-next": () => store.stepFrame(1),
          "rewind-group-prev": () => { void store.stepSearchGroup(-1); },
          "rewind-group-next": () => { void store.stepSearchGroup(1); },
          "unwind-rewind": () => {
            if (dayOpen) {
              setDayOpen(false);
              return;
            }
            store.unwind();
          },
        }}
        commandEnabled={{
          "unwind-rewind": dayOpen || playing || query !== "",
        }}
      />
      <section className="desktop-page-panel">
        <ProductionPageHeader
          className="production-header screen-header"
          eyebrow={t(locale, "nav.rewind")}
          title={t(locale, "nav.rewind")}
          description={t(locale, "screen.subtitle")}
        />
        <ProductionDataSourceBadge source={source} locale={locale} />
        <ProductionLifecycleRegion
          className="surface-notices"
          phase={status.refresh.phase}
          hasSavedData={status.refresh.hasSavedData}
          locale={locale}
          queue={status.queue}
          operationError={operationError}
          nextAction={status.refresh.phase !== "ready" ? t(locale, "common.retry") : null}
          retry={status.refresh.phase !== "ready" ? { onRetry: async () => { await run(() => store.refresh()); } } : null}
        />
        <div className="screen-toolbar">
          <ProductionSearchField
            className="screen-search"
            label={t(locale, "screen.searchPlaceholder")}
            placeholder={t(locale, "screen.searchPlaceholder")}
            value={query}
            onValueChange={(value) => store.setSearchQuery(value)}
            inputRef={searchRef}
          />
          <div className="screen-day-control">
            <button
              type="button"
              className="screen-day-toggle"
              aria-expanded={dayOpen}
              aria-controls={dayPopoverId}
              onClick={() => setDayOpen((open) => !open)}
            >
              {selectedDay ?? t(locale, "screen.dayPopover")}
            </button>
            {dayOpen && (
              <div id={dayPopoverId} className="screen-day-popover" role="dialog" aria-label={t(locale, "screen.dayPopover")}>
                <p className="screen-day-span" data-day-span="true">
                  {daySpanKind === "range" && days.oldest_captured_at && days.newest_captured_at
                    ? `${frameTimestamp(days.oldest_captured_at, locale)} – ${frameTimestamp(days.newest_captured_at, locale)}`
                    : daySpanKind === "day-empty"
                      ? t(locale, "screen.emptyDayTitle")
                      : null}
                </p>
                <div className="screen-day-jumps">
                  <button type="button" onClick={() => void run(() => store.jumpDay("older"))}>{t(locale, "screen.older")}</button>
                  <button type="button" onClick={() => void run(() => store.jumpDay("newer"))}>{t(locale, "screen.newer")}</button>
                  <button type="button" onClick={() => void run(() => store.jumpDay("oldest"))}>{t(locale, "screen.oldestCapture")}</button>
                </div>
                <ul className="screen-day-list">
                  {days.days.map((day) => (
                    <li key={day}>
                      <button type="button" aria-current={day === selectedDay ? "true" : undefined} onClick={() => void run(async () => { await store.selectDay(day); setDayOpen(false); })}>
                        {day}
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
          {bridgeAvailable ? (
            <div className="screen-capture-controls" data-capture-tone={tone}>
              <button
                type="button"
                className={`screen-capture-toggle is-${tone} ${engine === "recording" || engine === "paused" || engine === "starting" ? "control-danger" : "control-primary"}`}
                aria-pressed={engine === "recording" || engine === "paused" || engine === "starting"}
                aria-label={t(locale, "screen.captureToggle")}
                onClick={() => void run(() => (engine === "recording" || engine === "paused" || engine === "starting" ? store.stopCapture() : store.startCapture()))}
              >
                {engine === "recording" || engine === "paused" || engine === "starting" ? t(locale, "screen.stop") : t(locale, "screen.start")}
              </button>
              {paused && (
                <span
                  className="screen-capture-badge is-paused"
                  data-capture-reason={capture?.reason ?? "paused"}
                >
                  {t(locale, screenPausedMessageKey(capture?.reason ?? null))}
                </span>
              )}
              {recovering && <span className="screen-capture-badge is-recovering">{t(locale, "screen.recovering")}</span>}
              {permissionNeedsAction && (
                <button type="button" className="screen-permission-action" onClick={() => void run(() => store.requestPermission())}>
                  {t(locale, "screen.requestPermission")}
                </button>
              )}
              {showRebuild && (
                <button type="button" className="screen-rebuild" onClick={() => void run(async () => { await store.rebuildIndex(); })}>
                  {t(locale, "screen.rebuildIndex")}
                </button>
              )}
            </div>
          ) : (
            <ProductionDisabledControl
              label={t(locale, "screen.captureToggle")}
              explanation={t(locale, "screen.captureUnavailable")}
              className="screen-capture-unavailable"
              focusable={true}
            />
          )}
        </div>
        {permissionDenied && (
          <p className="screen-permission-note" data-permission-badge="denied">{t(locale, "screen.emptyPermissionDeniedTitle")}</p>
        )}
        {permissionUndetermined && bridgeAvailable && (
          <p className="screen-permission-note" data-permission-badge="undetermined">{t(locale, "screen.requestPermission")}</p>
        )}
        {engineError && permission !== "denied" && (
          <p className="screen-engine-error" data-engine-error="true">{t(locale, "lifecycle.error")}</p>
        )}
        <ProductionLiveAnnouncement message={copied ? t(locale, "screen.copied") : null} />
        {empty ? (
          <div data-empty-kind={emptyKind}>
            <ProductionEmptyState
              icon={SCREEN_EMPTY_ICON}
              title={empty.title}
              detail={empty.detail}
              action={permissionNeedsAction && (emptyKind === "permission-denied" || emptyKind === "never-enabled") ? (
                <button type="button" className="control-primary" onClick={() => void run(() => store.requestPermission())}>{t(locale, "screen.requestPermission")}</button>
              ) : emptyKind === "never-enabled" && bridgeAvailable ? (
                <button type="button" className="control-primary" onClick={() => void run(() => store.startCapture())}>{t(locale, "screen.start")}</button>
              ) : undefined}
            />
          </div>
        ) : (
          <div className="screen-workspace">
            {query.trim() !== "" && groups.length > 0 && (
              <section className="screen-results" aria-label={t(locale, "screen.results")}>
                {groups.map((group, index) => (
                  <article
                    key={group.key}
                    className={`screen-result-group${index === store.selectedGroupIndex() ? " is-selected" : ""}`}
                    data-group-index={index}
                  >
                    <button type="button" className="screen-result-group-header" onClick={() => void store.selectSearchGroup(index)}>
                      <span className="screen-app-badge">{group.appName}</span>
                      <span className="screen-window-title">{group.windowTitle}</span>
                    </button>
                    <ul>
                      {group.hits.map((hit: ScreenTextSearchHit) => (
                        <li key={hit.frame_id}>
                          <button type="button" className="screen-result-hit" onClick={() => void store.openFrame(hit.frame_id)}>
                            <HighlightedSnippet snippet={hit.snippet} />
                          </button>
                        </li>
                      ))}
                    </ul>
                  </article>
                ))}
              </section>
            )}
            <section className="screen-stage" aria-label={t(locale, "screen.currentFrame")}>
              {selected && (
                <header className="screen-stage-meta">
                  <span className="screen-app-badge" data-app-badge="true">
                    <span
                      className="screen-app-swatch"
                      aria-hidden="true"
                      style={{ background: screenAppColor(selected.app_name).css }}
                    />
                    {selected.app_name}
                  </span>
                  <span className="screen-window-title" data-window-title="true">{selected.window_title}</span>
                </header>
              )}
              <div className="screen-frame-stage">
                {image.kind === "ready" ? (
                  <div className="screen-frame-image-wrap">
                    <img
                      className="screen-frame-image"
                      alt={selected?.window_title ?? t(locale, "screen.currentFrame")}
                      src={frameImageSrc(image) ?? ""}
                      width={image.image.width}
                      height={image.image.height}
                    />
                    {ocr && <FrameHighlights blocks={ocr.blocks} matchedIds={matched} />}
                    {/*
                      Chrome that sits *on* the picture, as `RewindStageChrome`
                      draws it: the app chevrons on the frame's edges and the
                      moment it was taken at bottom-left.

                      It hangs off the image wrapper rather than the stage
                      because the wrapper *is* the picture's rectangle — the
                      stage is `place-items: center` around a `object-fit:
                      contain` image, so a capture narrower than the stage
                      leaves a band of empty ground down each side. Anchored to
                      the stage, the chevrons floated out in that band, yards
                      from the frame they step through, which is the same defect
                      `RewindStageFit` exists to fix on the macOS side. CSS
                      layout answers it here, so no geometry is computed.

                      Absent, not disabled, at the ends of the day: a disabled
                      control still advertises a step that does not exist. Named
                      by `aria-label` plus tooltip, following the glyph
                      precedent the composer's attach button set.
                    */}
                    <div className="screen-stage-chrome">
                      {previousAppIndex !== null && (
                        <button
                          type="button"
                          className="screen-stage-chevron is-previous"
                          aria-label={t(locale, "screen.previousApp")}
                          title={t(locale, "screen.previousApp")}
                          onClick={() => store.selectFrame(previousAppIndex)}
                        >
                          <ProductionIcon name="back" />
                        </button>
                      )}
                      {nextAppIndex !== null && (
                        <button
                          type="button"
                          className="screen-stage-chevron is-next"
                          aria-label={t(locale, "screen.nextApp")}
                          title={t(locale, "screen.nextApp")}
                          onClick={() => store.selectFrame(nextAppIndex)}
                        >
                          <ProductionIcon name="forward" />
                        </button>
                      )}
                      <span className="screen-timestamp-pill" data-timestamp-pill="true">
                        {selectedStamp}
                      </span>
                    </div>
                  </div>
                ) : image.kind === "loading" ? (
                  <div className="screen-frame-loading">
                    <ProductionEmptyState icon="loading" title={t(locale, "common.loading")} />
                  </div>
                ) : !bridgeAvailable ? (
                  <div className="screen-frame-host-unavailable">
                    <ProductionEmptyState icon="screen" title={t(locale, "screen.frameImageHostUnavailable")} />
                  </div>
                ) : image.kind === "unavailable" ? (
                  <div className="screen-frame-unavailable">
                    <ProductionEmptyState icon="screen" title={t(locale, "screen.frameImageUnavailable")} />
                  </div>
                ) : null}
              </div>
              {extracted !== "" && (
                <section className="screen-extracted" aria-label={t(locale, "screen.extractedText")}>
                  <header>
                    <h2>{t(locale, "screen.extractedText")}</h2>
                    <button type="button" className="control-tertiary" onClick={() => void copyExtracted()}>{t(locale, "screen.copy")}</button>
                  </header>
                  <pre className="screen-extracted-text">{extracted}</pre>
                </section>
              )}
            </section>
            <section className="screen-timeline" aria-label={t(locale, "screen.timeline")}>
              <ScreenTrack
                frames={frames}
                cursor={cursor}
                locale={locale}
                label={t(locale, "screen.timeline")}
                valueText={selectedStamp}
                onSelectFrame={(index) => store.selectFrame(index)}
                onStepFrame={(delta) => store.stepFrame(delta)}
              />
              <div className="screen-track-footer">
                <span className="screen-track-footer-hint">{t(locale, "screen.trackHint")}</span>
                <span className="screen-frame-counter" data-frame-counter="true">
                  {t(locale, "screen.frameCounter", { current: counterCurrent, total: counterTotal })}
                </span>
              </div>
              <div className="screen-playback">
                <button type="button" className="control-primary screen-play-control" onClick={() => playing ? store.pause() : store.play()}>
                  {playing ? t(locale, "screen.pause") : t(locale, "screen.play")}
                </button>
                <div className="control-segment-group" role="group">
                  {SCREEN_PLAYBACK_RATES.map((value: ScreenPlaybackRate) => (
                    <button
                      key={value}
                      type="button"
                      className="control-segment"
                      aria-pressed={rate === value}
                      onClick={() => store.setPlaybackRate(value)}
                    >
                      {t(locale, "screen.playbackRate", { rate: value })}
                    </button>
                  ))}
                </div>
              </div>
            </section>
          </div>
        )}
        {!bridgeAvailable && (
          <p className="screen-bridge-note">{t(locale, "screen.captureUnavailable")}</p>
        )}
      </section>
      <ProductionChrome locale={locale} active="rewind" placement="bottom" />
    </main>
  );
}
