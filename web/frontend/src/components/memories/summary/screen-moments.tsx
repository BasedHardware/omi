'use client';

import * as Dialog from '@radix-ui/react-dialog';
import { ChevronLeft, ChevronRight, Maximize2, Minimize2, X } from 'lucide-react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { KeyboardEvent as ReactKeyboardEvent } from 'react';
import getSharedScreenshots from '@/src/actions/memories/get-shared-screenshots';
import {
  captureOffsetLabel,
  clampOpenIndex,
  createRefreshGate,
  fitSize,
  groundGradient,
  initialFrameState,
  msUntilRefresh,
  nextFrameSet,
  recoveryListenersMode,
  withFailedAsset,
  screenshotTiles,
  stepIndex,
} from '@/src/lib/shared-screenshots.mjs';
import type {
  SharedScreenFrame,
  SharedScreenFrameSet,
  SharedScreenshotsResult,
} from '@/src/types/memory.types';

interface ScreenMomentsProps {
  conversationId: string;
  /** The server render's fetch result; a failure is retried client-side. */
  initial: SharedScreenshotsResult | null;
  startedAt?: Date | string | null;
}

// Room the lightbox keeps around the image for the close/zoom row and caption.
const LIGHTBOX_GUTTER_X = 32;
const LIGHTBOX_CHROME_Y = 148;

function useViewport() {
  const [viewport, setViewport] = useState({ width: 0, height: 0 });
  useEffect(() => {
    const update = () =>
      setViewport({ width: window.innerWidth, height: window.innerHeight });
    update();
    window.addEventListener('resize', update);
    return () => window.removeEventListener('resize', update);
  }, []);
  return viewport;
}

/**
 * "What was on screen": the approved meeting screenshots (banner first, then
 * the strip), each opening an accessible lightbox. Renders nothing for an
 * empty set or a failed fetch. The signed URLs expire after 60 minutes, so
 * the set is refetched shortly before expiry, when a hidden tab returns, and
 * when an image fails to load.
 */
export default function ScreenMoments({
  conversationId,
  initial,
  startedAt,
}: ScreenMomentsProps) {
  // Read once: a failed server-side fetch starts empty and is retried below.
  const [{ set: initialSet, retry: retryInitial }] = useState(() =>
    initialFrameState(initial),
  );
  const [frameSet, setFrameSet] = useState<SharedScreenFrameSet | null>(initialSet);
  // True from a failed server-side fetch until a client refetch succeeds.
  const [awaitingFirstSuccess, setAwaitingFirstSuccess] = useState(retryInitial);
  const tiles = useMemo(
    () => screenshotTiles(frameSet) as SharedScreenFrame[],
    [frameSet],
  );
  // Image URLs (thumbnail or full-size, tracked separately) that failed to
  // load. Only those images are hidden (a tile keeps its gradient) while a
  // refetch renews the URLs; a failed thumbnail never hides the full image.
  const [failedUrls, setFailedUrls] = useState<ReadonlySet<string>>(() => new Set());
  // Bumped by every successful refetch and used in the image keys, so images
  // remount and retry even when the backend returns the identical signed URL
  // (an <img> whose src does not change never reloads after an error).
  const [setVersion, setSetVersion] = useState(0);
  useEffect(() => {
    setFailedUrls(new Set());
  }, [setVersion]);
  const [openIndex, setOpenIndex] = useState<number | null>(null);
  const [zoomed, setZoomed] = useState(false);
  const [portalEl, setPortalEl] = useState<HTMLElement | null>(null);
  const sectionRef = useRef<HTMLElement | null>(null);
  const tileRefs = useRef<Array<HTMLButtonElement | null>>([]);
  // The tile to refocus on close: the frame last shown, not the one opened.
  const shownIndex = useRef(0);
  const viewport = useViewport();

  // One gate per conversation: serialises refetches, defers any request made
  // during the post-renewal cooldown to its end (never drops it), and retries
  // failed refetches with bounded backoff. A failure keeps the last set; only
  // a successful (possibly empty) response replaces it. Created in an effect
  // (not memoised) so StrictMode's mount/unmount/mount cycle cannot leave a
  // disposed gate in use; `active` drops a response that lands after unmount.
  const gateRef = useRef<ReturnType<typeof createRefreshGate> | null>(null);
  useEffect(() => {
    let active = true;
    const gate = createRefreshGate({
      run: async () => {
        const result = await getSharedScreenshots(conversationId);
        if (!active) return;
        setFrameSet((previous) => nextFrameSet(previous, result));
        if (result.ok) {
          setSetVersion((v) => v + 1);
          setAwaitingFirstSuccess(false);
        } else {
          throw new Error('screenshot refetch failed');
        }
      },
    });
    gateRef.current = gate;
    // The server render's fetch failed: retry from the client through the
    // gate (backoff, capped). A successful empty set is never polled.
    if (retryInitial) gate.request();
    return () => {
      active = false;
      gate.dispose();
    };
  }, [conversationId, retryInitial]);
  const refresh = useCallback(() => gateRef.current?.request(), []);
  const markFailed = useCallback(
    (url: string) => {
      setFailedUrls((previous) => withFailedAsset(previous, url) as ReadonlySet<string>);
      refresh();
    },
    [refresh],
  );

  useEffect(() => {
    const mode = recoveryListenersMode({
      tileCount: tiles.length,
      awaitingFirstSuccess,
    });
    if (mode === 'none') return;
    // 'renew': the gate enforces the cooldown; this waits for the expiry
    // margin. 'recover': no timer (the gate's own retries have a cap), but a
    // return to the tab always tries again.
    const timer =
      mode === 'renew'
        ? window.setTimeout(refresh, msUntilRefresh(tiles, Date.now()))
        : undefined;
    // Timers stall in background tabs and bfcache; check again on return.
    const onVisible = () => {
      if (document.visibilityState !== 'visible') return;
      if (mode === 'recover' || msUntilRefresh(tiles, Date.now()) === 0) refresh();
    };
    document.addEventListener('visibilitychange', onVisible);
    window.addEventListener('pageshow', onVisible);
    return () => {
      if (timer !== undefined) window.clearTimeout(timer);
      document.removeEventListener('visibilitychange', onVisible);
      window.removeEventListener('pageshow', onVisible);
    };
  }, [tiles, awaitingFirstSuccess, refresh]);

  useEffect(() => {
    setPortalEl(sectionRef.current?.closest<HTMLElement>('.share-note') ?? null);
  }, [tiles.length]);

  // A refresh can shrink or empty the set while the lightbox is open. Clamp
  // (or close), keeping the refocus target in step with what is shown.
  useEffect(() => {
    const clamped = clampOpenIndex(openIndex, tiles.length);
    if (clamped === openIndex) return;
    if (clamped !== null) shownIndex.current = clamped;
    setOpenIndex(clamped);
  }, [tiles.length, openIndex]);

  if (tiles.length === 0) return null;

  const open = (index: number) => {
    setZoomed(false);
    shownIndex.current = index;
    setOpenIndex(index);
    if (msUntilRefresh(tiles, Date.now()) === 0) refresh();
  };

  const go = (delta: 1 | -1) => {
    setZoomed(false);
    const next = stepIndex(openIndex ?? 0, tiles.length, delta);
    shownIndex.current = next;
    setOpenIndex(next);
  };

  const onLightboxKeyDown = (event: ReactKeyboardEvent) => {
    if (tiles.length < 2) return;
    if (event.key === 'ArrowLeft') {
      event.preventDefault();
      go(-1);
    } else if (event.key === 'ArrowRight') {
      event.preventDefault();
      go(1);
    }
  };

  const current: SharedScreenFrame | null =
    openIndex === null ? null : tiles[openIndex] ?? null;
  const fit = current
    ? fitSize(
        current.width,
        current.height,
        Math.max(viewport.width - LIGHTBOX_GUTTER_X, 1),
        Math.max(viewport.height - LIGHTBOX_CHROME_Y, 1),
      )
    : null;
  const canZoom = Boolean(fit && fit.scale > 0 && fit.scale < 1);
  const showZoomed = zoomed && canZoom;

  return (
    <section
      ref={sectionRef}
      className="sn-block sn-shots"
      aria-labelledby="sn-shots-title"
    >
      <h2 id="sn-shots-title" className="sn-h3">
        What was on screen
      </h2>
      <ul className="sn-shots-row">
        {tiles.map((frame, index) => {
          const offset = captureOffsetLabel(frame.captured_at, startedAt);
          const label = frame.caption?.trim() || 'Screenshot';
          return (
            <li
              key={frame.id}
              className={`sn-shot${
                failedUrls.has(frame.thumbnail_url) ? ' sn-shot-failed' : ''
              }`}
            >
              <button
                ref={(el) => {
                  tileRefs.current[index] = el;
                }}
                type="button"
                className="sn-shot-button"
                onClick={() => open(index)}
                aria-label={`Open screenshot ${index + 1} of ${tiles.length}${
                  offset ? ` at ${offset}` : ''
                }: ${label}`}
                style={{
                  aspectRatio: `${frame.width} / ${frame.height}`,
                  backgroundImage: groundGradient(frame),
                }}
              >
                {/* eslint-disable-next-line @next/next/no-img-element -- signed, expiring GCS URLs; see get-shared-screenshots */}
                <img
                  key={`${frame.id}:${setVersion}`}
                  src={frame.thumbnail_url}
                  alt=""
                  width={frame.width}
                  height={frame.height}
                  loading="lazy"
                  decoding="async"
                  onError={() => markFailed(frame.thumbnail_url)}
                />
                {offset ? (
                  <span className="sn-shot-time" aria-hidden="true">
                    {offset}
                  </span>
                ) : null}
              </button>
            </li>
          );
        })}
      </ul>

      <Dialog.Root
        open={current !== null}
        onOpenChange={(next) => {
          if (!next) setOpenIndex(null);
        }}
      >
        <Dialog.Portal container={portalEl ?? undefined}>
          <Dialog.Overlay className="sn-lightbox-scrim" />
          <Dialog.Content
            className="sn-lightbox"
            onKeyDown={onLightboxKeyDown}
            onCloseAutoFocus={(event) => {
              event.preventDefault();
              const tile = tileRefs.current[shownIndex.current];
              if (tile?.isConnected) {
                tile.focus();
              } else {
                // The set emptied (the strip is gone): land on the active tab.
                portalEl
                  ?.querySelector<HTMLElement>('[role="tab"][aria-selected="true"]')
                  ?.focus();
              }
            }}
          >
            {current && fit ? (
              <>
                <div className="sn-lightbox-bar">
                  <span className="sn-lightbox-count" aria-hidden="true">
                    {(openIndex ?? 0) + 1} / {tiles.length}
                  </span>
                  <div className="sn-lightbox-actions">
                    {canZoom ? (
                      <button
                        type="button"
                        className="sn-lightbox-icon"
                        onClick={() => setZoomed((z) => !z)}
                        aria-pressed={showZoomed}
                        aria-label={showZoomed ? 'Fit to screen' : 'Actual size'}
                      >
                        {showZoomed ? <Minimize2 size={18} /> : <Maximize2 size={18} />}
                      </button>
                    ) : null}
                    <Dialog.Close className="sn-lightbox-icon" aria-label="Close">
                      <X size={18} />
                    </Dialog.Close>
                  </div>
                </div>
                <div
                  className={`sn-lightbox-stage${
                    showZoomed ? ' sn-lightbox-zoomed' : ''
                  }${failedUrls.has(current.content_url) ? ' sn-shot-failed' : ''}`}
                >
                  {/* eslint-disable-next-line @next/next/no-img-element -- signed, expiring GCS URLs */}
                  <img
                    key={`${current.id}:${setVersion}`}
                    src={current.content_url}
                    alt={current.caption || 'Screenshot'}
                    width={showZoomed ? current.width : fit.width}
                    height={showZoomed ? current.height : fit.height}
                    style={{ backgroundImage: groundGradient(current) }}
                    onError={() => markFailed(current.content_url)}
                  />
                </div>
                <div className="sn-lightbox-caption">
                  <Dialog.Title className="sn-lightbox-title">
                    {current.caption || 'Screenshot'}
                  </Dialog.Title>
                  <Dialog.Description className="sn-sr">
                    Screenshot {(openIndex ?? 0) + 1} of {tiles.length}.
                    {tiles.length > 1
                      ? ' Use the left and right arrow keys to move between screenshots.'
                      : ''}
                  </Dialog.Description>
                  {captureOffsetLabel(current.captured_at, startedAt) ? (
                    <span className="sn-lightbox-time">
                      {captureOffsetLabel(current.captured_at, startedAt)} into the call
                    </span>
                  ) : null}
                </div>
                {tiles.length > 1 ? (
                  <>
                    <button
                      type="button"
                      className="sn-lightbox-nav sn-lightbox-prev"
                      onClick={() => go(-1)}
                      aria-label="Previous screenshot"
                    >
                      <ChevronLeft size={22} />
                    </button>
                    <button
                      type="button"
                      className="sn-lightbox-nav sn-lightbox-next"
                      onClick={() => go(1)}
                      aria-label="Next screenshot"
                    >
                      <ChevronRight size={22} />
                    </button>
                  </>
                ) : null}
              </>
            ) : null}
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </section>
  );
}
