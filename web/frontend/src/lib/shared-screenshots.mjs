/**
 * Pure helpers for the "What was on screen" strip on the public share page.
 * The frame set comes from the unauthenticated
 * `GET /v1/conversations/{id}/shared/screenshots` (backend/models/screen_frame.py
 * `ConversationScreenFrameSet`). Kept as plain JS so node:test can assert
 * without a TS loader.
 */

/** Refetch this long before the earliest signed URL expires (they last 60 min). */
export const URL_REFRESH_MARGIN_MS = 2 * 60 * 1000;

/**
 * Never refetch more often than this. A viewer whose clock runs an hour fast
 * would otherwise see every fresh set as already expired and refetch in a loop.
 */
export const MIN_REFRESH_INTERVAL_MS = 30 * 1000;

function isFrame(value) {
  return (
    value != null &&
    typeof value === 'object' &&
    typeof value.id === 'string' &&
    typeof value.content_url === 'string' &&
    typeof value.thumbnail_url === 'string' &&
    Number.isFinite(value.width) &&
    Number.isFinite(value.height) &&
    value.width > 0 &&
    value.height > 0 &&
    Number.isFinite(Date.parse(value.url_expires_at))
  );
}

/**
 * The tiles in display order: the banner first, then the strip in rank order.
 * A frame that is both banner and strip (same id) appears once. Malformed
 * entries are dropped rather than rendered broken.
 */
export function screenshotTiles(set) {
  if (!set || typeof set !== 'object') return [];
  const strip = Array.isArray(set.strip) ? set.strip.filter(isFrame) : [];
  strip.sort((a, b) => (a.rank ?? 0) - (b.rank ?? 0));
  const ordered = isFrame(set.banner) ? [set.banner, ...strip] : strip;
  const seen = new Set();
  return ordered.filter((frame) => {
    if (seen.has(frame.id)) return false;
    seen.add(frame.id);
    return true;
  });
}

/** Earliest `url_expires_at` across the tiles, in epoch ms, or null. */
export function earliestExpiryMs(tiles) {
  let earliest = null;
  for (const frame of tiles ?? []) {
    const ms = Date.parse(frame?.url_expires_at);
    if (Number.isFinite(ms) && (earliest === null || ms < earliest)) earliest = ms;
  }
  return earliest;
}

/**
 * Milliseconds until the set should be refetched (0 = now). A set without a
 * parseable expiry is treated as already due, so a malformed response never
 * serves images past their signature.
 */
export function msUntilRefresh(tiles, nowMs, marginMs = URL_REFRESH_MARGIN_MS) {
  const earliest = earliestExpiryMs(tiles);
  if (earliest === null) return 0;
  return Math.max(0, earliest - marginMs - nowMs);
}

/** Wrap-around step through the tiles; 0 for an empty list. */
export function stepIndex(current, length, delta) {
  if (!Number.isFinite(length) || length <= 0) return 0;
  return (((current + delta) % length) + length) % length;
}

/**
 * Where in the call a frame was captured, as "m:ss" or "h:mm:ss" from the
 * conversation's start. Empty when either time is missing or the frame
 * predates the start.
 */
export function captureOffsetLabel(capturedAt, startedAt) {
  const captured = Date.parse(capturedAt);
  const started = Date.parse(startedAt);
  if (!Number.isFinite(captured) || !Number.isFinite(started)) return '';
  const totalSeconds = Math.floor((captured - started) / 1000);
  if (totalSeconds < 0) return '';
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  const ss = String(seconds).padStart(2, '0');
  if (hours > 0) return `${hours}:${String(minutes).padStart(2, '0')}:${ss}`;
  return `${minutes}:${ss}`;
}

/**
 * Zoom-to-fit: the largest size that keeps the frame's natural aspect ratio,
 * never upscales past its natural pixels, and fits the available box.
 */
export function fitSize(width, height, maxWidth, maxHeight) {
  if (!(width > 0 && height > 0 && maxWidth > 0 && maxHeight > 0)) {
    return { width: 0, height: 0, scale: 0 };
  }
  const scale = Math.min(1, maxWidth / width, maxHeight / height);
  return {
    width: Math.round(width * scale),
    height: Math.round(height * scale),
    scale,
  };
}

/** Two-stop background for a tile while its image loads (server-derived). */
export function groundGradient(frame) {
  const stops = frame?.ground?.stops;
  const valid =
    Array.isArray(stops) &&
    stops.length >= 2 &&
    stops.every((stop) => typeof stop === 'string' && /^#[0-9a-f]{6}$/i.test(stop));
  if (!valid) return undefined;
  return `linear-gradient(135deg, ${stops[0]}, ${stops[1]})`;
}

/**
 * Serialises refetches of the signed-URL set. A request made during the
 * post-refetch cooldown is deferred to the cooldown's end, not dropped: an
 * image that fails right after a renewal would otherwise stay broken until
 * the next expiry timer, about an hour later. Requests during a run are
 * absorbed by that run; several cooldown requests coalesce into one.
 */
export function createRefreshGate({
  run,
  minIntervalMs = MIN_REFRESH_INTERVAL_MS,
  now = () => Date.now(),
  setTimer = (fn, ms) => setTimeout(fn, ms),
  clearTimer = (timer) => clearTimeout(timer),
}) {
  let lastRunAt = -Infinity;
  let inFlight = false;
  let deferred = null;
  let disposed = false;

  const start = () => {
    deferred = null;
    if (disposed || inFlight) return;
    inFlight = true;
    lastRunAt = now();
    let pending;
    try {
      pending = run();
    } catch {
      pending = undefined;
    }
    Promise.resolve(pending)
      .catch(() => {})
      .finally(() => {
        inFlight = false;
      });
  };

  return {
    request() {
      if (disposed || inFlight || deferred) return;
      const wait = lastRunAt + minIntervalMs - now();
      if (wait <= 0) start();
      else deferred = setTimer(start, wait);
    },
    /** Epoch ms of the last run start, for scheduling the next expiry refetch. */
    lastRunAt: () => lastRunAt,
    dispose() {
      disposed = true;
      if (deferred) clearTimer(deferred);
      deferred = null;
    },
  };
}
