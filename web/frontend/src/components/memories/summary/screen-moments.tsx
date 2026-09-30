'use client';

import * as Dialog from '@radix-ui/react-dialog';
import { ChevronLeft, ChevronRight, Maximize2, Minimize2, X } from 'lucide-react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { KeyboardEvent as ReactKeyboardEvent } from 'react';
import getSharedScreenshots from '@/src/actions/memories/get-shared-screenshots';
import {
  captureOffsetLabel,
  createRefreshGate,
  fitSize,
  groundGradient,
  msUntilRefresh,
  screenshotTiles,
  stepIndex,
} from '@/src/lib/shared-screenshots.mjs';
import type { SharedScreenFrame, SharedScreenFrameSet } from '@/src/types/memory.types';

interface ScreenMomentsProps {
  conversationId: string;
  initialSet: SharedScreenFrameSet | null;
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
  initialSet,
  startedAt,
}: ScreenMomentsProps) {
  const [frameSet, setFrameSet] = useState(initialSet);
  const tiles = useMemo(
    () => screenshotTiles(frameSet) as SharedScreenFrame[],
    [frameSet],
  );
  const [openIndex, setOpenIndex] = useState<number | null>(null);
  const [zoomed, setZoomed] = useState(false);
  const [portalEl, setPortalEl] = useState<HTMLElement | null>(null);
  const sectionRef = useRef<HTMLElement | null>(null);
  const tileRefs = useRef<Array<HTMLButtonElement | null>>([]);
  // The tile to refocus on close: the frame last shown, not the one opened.
  const shownIndex = useRef(0);
  const viewport = useViewport();

  // One gate per conversation: serialises refetches and defers any request
  // made during the post-renewal cooldown to its end (never drops it).
  // Created in an effect (not memoised) so StrictMode's mount/unmount/mount
  // cycle cannot leave a disposed gate in use.
  const gateRef = useRef<ReturnType<typeof createRefreshGate> | null>(null);
  useEffect(() => {
    const gate = createRefreshGate({
      run: async () => {
        try {
          setFrameSet(await getSharedScreenshots(conversationId));
        } catch {
          setFrameSet(null);
        }
      },
    });
    gateRef.current = gate;
    return () => gate.dispose();
  }, [conversationId]);
  const refresh = useCallback(() => gateRef.current?.request(), []);

  useEffect(() => {
    if (tiles.length === 0) return;
    // The gate enforces the cooldown; this only waits for the expiry margin.
    const delay = msUntilRefresh(tiles, Date.now());
    const timer = window.setTimeout(refresh, delay);
    // Timers stall in background tabs and bfcache; check again on return.
    const onVisible = () => {
      if (
        document.visibilityState === 'visible' &&
        msUntilRefresh(tiles, Date.now()) === 0
      ) {
        refresh();
      }
    };
    document.addEventListener('visibilitychange', onVisible);
    window.addEventListener('pageshow', onVisible);
    return () => {
      window.clearTimeout(timer);
      document.removeEventListener('visibilitychange', onVisible);
      window.removeEventListener('pageshow', onVisible);
    };
  }, [tiles, refresh]);

  useEffect(() => {
    setPortalEl(sectionRef.current?.closest<HTMLElement>('.share-note') ?? null);
  }, [tiles.length]);

  // A refresh can shrink or empty the set while the lightbox is open.
  useEffect(() => {
    if (openIndex === null) return;
    if (tiles.length === 0) setOpenIndex(null);
    else if (openIndex >= tiles.length) setOpenIndex(tiles.length - 1);
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
            <li key={frame.id} className="sn-shot">
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
                  src={frame.thumbnail_url}
                  alt=""
                  width={frame.width}
                  height={frame.height}
                  loading="lazy"
                  decoding="async"
                  onError={refresh}
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
              tileRefs.current[shownIndex.current]?.focus();
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
                  }`}
                >
                  {/* eslint-disable-next-line @next/next/no-img-element -- signed, expiring GCS URLs */}
                  <img
                    key={current.id}
                    src={current.content_url}
                    alt={current.caption || 'Screenshot'}
                    width={showZoomed ? current.width : fit.width}
                    height={showZoomed ? current.height : fit.height}
                    style={{ backgroundImage: groundGradient(current) }}
                    onError={refresh}
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
