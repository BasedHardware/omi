import type {
  ScreenOcrBlock,
  ScreenRetentionDays,
  ScreenTextSearchHit,
  ScreenTimelineFrame,
} from "@omi-core/adapters-platform";
import { SCREEN_SEARCH_GROUP_WINDOW_MS } from "@omi-core/adapters-platform";

/**
 * Four empty kinds the Rewind surface must never collapse. A day with no
 * captures is not a search miss; never-enabled is not permission-denied.
 */
export type ScreenEmptyKind =
  | "never-enabled"
  | "permission-denied"
  | "day-empty"
  | "search-miss";

export type ScreenSearchGroup = {
  readonly key: string;
  readonly appBundleId: string;
  readonly appName: string;
  readonly windowTitle: string;
  readonly startedAt: string;
  readonly hits: readonly ScreenTextSearchHit[];
};

export type ScreenHighlightRect = {
  readonly id: string;
  readonly x: number;
  readonly y: number;
  readonly w: number;
  readonly h: number;
};

export type ScreenSnippetPart = {
  readonly text: string;
  readonly matched: boolean;
};

export type ScreenPlaybackRate = 0.5 | 1 | 2 | 4 | 8;

export const SCREEN_PLAYBACK_RATES: readonly ScreenPlaybackRate[] = [0.5, 1, 2, 4, 8];
export const SCREEN_PLAYBACK_TICK_MS = 200;

export type ScreenDaySpanKind = "range" | "day-empty" | null;

/**
 * Copy for the day-picker span. A missing oldest/newest timestamp is not
 * "no captures for this day" until refresh has finished — that claim is
 * `day-empty`, and only `ready` may make it.
 */
export function screenDaySpanKind(input: {
  readonly phase: "initial-loading" | "refreshing" | "ready" | "saved-but-refresh-failed" | "unavailable";
  readonly oldestCapturedAt: string | null;
  readonly newestCapturedAt: string | null;
}): ScreenDaySpanKind {
  if (input.oldestCapturedAt && input.newestCapturedAt) return "range";
  if (input.phase !== "ready") return null;
  return "day-empty";
}

export function screenEmptyKind(input: {
  readonly phase: "initial-loading" | "refreshing" | "ready" | "saved-but-refresh-failed" | "unavailable";
  readonly permission: "granted" | "denied" | "undetermined";
  readonly captureEverEnabled: boolean;
  readonly historyFrameCount: number;
  readonly dayFrameCount: number;
  readonly searchQuery: string;
  readonly searchHitCount: number;
}): ScreenEmptyKind | null {
  if (input.phase !== "ready") return null;
  const searching = input.searchQuery.trim().length > 0;
  if (input.permission === "denied" && input.historyFrameCount === 0 && !searching) {
    return "permission-denied";
  }
  if (!input.captureEverEnabled && input.historyFrameCount === 0 && !searching) {
    return "never-enabled";
  }
  if (searching && input.searchHitCount === 0) return "search-miss";
  if (!searching && input.dayFrameCount === 0) return "day-empty";
  return null;
}

export function groupScreenSearchHits(
  hits: readonly ScreenTextSearchHit[],
  windowMs = SCREEN_SEARCH_GROUP_WINDOW_MS,
): readonly ScreenSearchGroup[] {
  const ordered = [...hits].sort((left, right) => {
    const byTime = Date.parse(left.captured_at) - Date.parse(right.captured_at);
    if (byTime !== 0) return byTime;
    return left.frame_id.localeCompare(right.frame_id);
  });
  const clusters = new Map<string, ScreenTextSearchHit[]>();
  for (const hit of ordered) {
    const key = `${hit.app_bundle_id}\u0000${hit.window_title}`;
    const list = clusters.get(key);
    if (list === undefined) clusters.set(key, [hit]);
    else list.push(hit);
  }
  const groups: ScreenSearchGroup[] = [];
  for (const list of clusters.values()) {
    let current: ScreenTextSearchHit[] = [];
    let startedAt = "";
    const flush = (): void => {
      const first = current[0];
      if (first === undefined) return;
      groups.push({
        key: `${first.app_bundle_id}:${first.window_title}:${first.captured_at}:${first.frame_id}`,
        appBundleId: first.app_bundle_id,
        appName: first.app_name,
        windowTitle: first.window_title,
        startedAt: first.captured_at,
        hits: current,
      });
      current = [];
      startedAt = "";
    };
    for (const hit of list) {
      const hitAt = Date.parse(hit.captured_at);
      if (current.length === 0) {
        current = [hit];
        startedAt = hit.captured_at;
        continue;
      }
      if (Number.isFinite(hitAt) && hitAt - Date.parse(startedAt) <= windowMs) {
        current.push(hit);
        continue;
      }
      flush();
      current = [hit];
      startedAt = hit.captured_at;
    }
    flush();
  }
  return groups.sort((left, right) => Date.parse(left.startedAt) - Date.parse(right.startedAt));
}

export function highlightRectsFor(
  blocks: readonly ScreenOcrBlock[],
  matchedBlockIds: readonly string[],
): readonly ScreenHighlightRect[] {
  const matched = new Set(matchedBlockIds);
  const rects: ScreenHighlightRect[] = [];
  for (const block of blocks) {
    if (!matched.has(block.id)) continue;
    rects.push({ id: block.id, x: block.x, y: block.y, w: block.w, h: block.h });
  }
  return rects;
}

export function snippetParts(snippet: string): readonly ScreenSnippetPart[] {
  const parts: ScreenSnippetPart[] = [];
  const pattern = /<<([^<>]*)>>/g;
  let cursor = 0;
  for (const match of snippet.matchAll(pattern)) {
    const index = match.index ?? 0;
    if (index > cursor) parts.push({ text: snippet.slice(cursor, index), matched: false });
    parts.push({ text: match[1] ?? "", matched: true });
    cursor = index + match[0].length;
  }
  if (cursor < snippet.length) parts.push({ text: snippet.slice(cursor), matched: false });
  return parts;
}

export function adjacentCaptureDay(
  days: readonly string[],
  selected: string,
  direction: "older" | "newer" | "oldest",
): string | null {
  if (days.length === 0) return null;
  if (direction === "oldest") return days[0] ?? null;
  const unique = [...days];
  let index = unique.indexOf(selected);
  if (index < 0) {
    index = unique.findIndex((day) => day > selected);
    if (direction === "older") {
      if (index === -1) return unique.at(-1) ?? null;
      return index === 0 ? null : unique[index - 1] ?? null;
    }
    return index === -1 ? null : unique[index] ?? null;
  }
  if (direction === "older") return unique[index - 1] ?? null;
  return unique[index + 1] ?? null;
}

export function calendarDayFromInstant(iso: string): string | null {
  const ms = Date.parse(iso);
  if (!Number.isFinite(ms)) return null;
  return iso.slice(0, 10);
}

export function playbackTickMs(rate: ScreenPlaybackRate): number {
  return Math.max(25, Math.round(SCREEN_PLAYBACK_TICK_MS / rate));
}

export function formatScreenByteSize(bytes: number): string {
  const gb = bytes / 1_000_000_000;
  if (bytes > 0 && gb < 0.01) return "< 0.01 GB";
  const rounded = Math.round(gb * 100) / 100;
  return `${rounded} GB`;
}

export function storageSummaryLabel(input: {
  readonly frames: number;
  readonly bytesOnDisk: number | null;
}): { readonly frames: number; readonly size: string | null } {
  return {
    frames: input.frames,
    size: input.bytesOnDisk === null ? null : formatScreenByteSize(input.bytesOnDisk),
  };
}

export function retentionLabelDays(days: ScreenRetentionDays): ScreenRetentionDays {
  return days;
}

export function frameAtCursor(
  frames: readonly ScreenTimelineFrame[],
  cursor: number,
): ScreenTimelineFrame | null {
  if (frames.length === 0) return null;
  const index = Math.min(Math.max(0, cursor), frames.length - 1);
  return frames[index] ?? null;
}

/** Stay on a historical day unless the user was already on the newest day. */
export function followNewestCaptureDay(input: {
  readonly previousDays: readonly string[];
  readonly selectedDay: string | null;
  readonly nextDays: readonly string[];
}): string | null {
  const nextNewest = input.nextDays.at(-1) ?? input.nextDays[0] ?? null;
  if (input.selectedDay === null) return nextNewest;
  const previousNewest = input.previousDays.at(-1) ?? null;
  if (input.selectedDay === previousNewest) return nextNewest;
  if (input.nextDays.includes(input.selectedDay)) return input.selectedDay;
  return nextNewest;
}

/**
 * Hue bands the app-colour hash may land in, ported from `RewindPalette` in
 * the macOS shell. Two properties matter and are asserted in the tests:
 *
 * 1. Every band ends below hue 220 — the brand blue's own hue — so a generated
 *    app colour can never be mistaken for an Omi accent (INV-UI-1).
 * 2. Bands skip 40°–88° (mustard/olive) and 172°–186°, which read as dirty at
 *    this saturation, and per-band brightness compensates for the eye's
 *    uneven luminance response so a green badge is not brighter than a blue.
 */
const SCREEN_APP_HUE_BANDS: readonly {
  readonly start: number;
  readonly end: number;
  readonly brightness: number;
}[] = [
  { start: 2, end: 16, brightness: 1.0 },
  { start: 26, end: 36, brightness: 0.68 },
  { start: 90, end: 104, brightness: 0.65 },
  { start: 126, end: 142, brightness: 0.5 },
  { start: 156, end: 170, brightness: 0.65 },
  { start: 188, end: 200, brightness: 0.65 },
  { start: 206, end: 218, brightness: 0.99 },
];
/** No generated hue may reach this — it is the brand accent's hue. */
export const SCREEN_APP_HUE_CEILING = 220;
const SCREEN_APP_SATURATION = 0.92;
/** Prime, so adjacent bundle-id hashes do not alias onto one hue. */
const SCREEN_APP_HUE_BUCKETS = 2503n;
const FNV_OFFSET_BASIS = 0xcbf29ce484222325n;
const FNV_PRIME = 0x100000001b3n;
const U64_MASK = 0xffffffffffffffffn;

/**
 * FNV-1a over the UTF-8 bytes of an app's identity. The hash — not a counter
 * over the order apps happen to appear — is what keeps Slack the same colour
 * across launches, days, and machines.
 */
export function screenAppColorHash(identity: string): bigint {
  let hash = FNV_OFFSET_BASIS;
  for (const byte of new TextEncoder().encode(identity)) {
    hash = ((hash ^ BigInt(byte)) * FNV_PRIME) & U64_MASK;
  }
  return hash;
}

export type ScreenAppColor = {
  readonly hue: number;
  readonly saturation: number;
  readonly brightness: number;
  readonly css: string;
};

function hsbToCss(hue: number, saturation: number, brightness: number): string {
  const sector = (hue % 360) / 60;
  const index = Math.floor(sector);
  const fraction = sector - index;
  const p = brightness * (1 - saturation);
  const q = brightness * (1 - saturation * fraction);
  const t = brightness * (1 - saturation * (1 - fraction));
  const [red, green, blue] = ((): readonly [number, number, number] => {
    switch (index % 6) {
      case 0: return [brightness, t, p];
      case 1: return [q, brightness, p];
      case 2: return [p, brightness, t];
      case 3: return [p, q, brightness];
      case 4: return [t, p, brightness];
      default: return [brightness, p, q];
    }
  })();
  const channel = (value: number): number => Math.round(Math.min(1, Math.max(0, value)) * 255);
  return `rgb(${channel(red)}, ${channel(green)}, ${channel(blue)})`;
}

/** Every bucket this palette can emit — the whole output domain, so a guard can enumerate it. */
export const SCREEN_APP_BUCKET_COUNT = Number(SCREEN_APP_HUE_BUCKETS);

/**
 * Where one bucket lands. Buckets spread across the *bands* rather than across
 * the degrees they cover, so each family gets an equal share of apps — width
 * weighting would hand the 14°-wide red band two-fifths more apps than the
 * 10°-wide orange one for no reason anyone looking at the track could name.
 */
export function screenAppColorForBucket(bucket: number): ScreenAppColor {
  const bands = SCREEN_APP_HUE_BANDS;
  const position = ((bucket % SCREEN_APP_BUCKET_COUNT) / SCREEN_APP_BUCKET_COUNT) * bands.length;
  const index = Math.min(bands.length - 1, Math.floor(position));
  const band = bands[index] as { start: number; end: number; brightness: number };
  const hue = band.start + (position - index) * (band.end - band.start);
  return {
    hue,
    saturation: SCREEN_APP_SATURATION,
    brightness: band.brightness,
    css: hsbToCss(hue, SCREEN_APP_SATURATION, band.brightness),
  };
}

/**
 * A stable colour for an app on the Rewind track, ported from
 * `RewindPalette.swatch(forApp:)`. Same name, same colour, forever — the track
 * only reads as a shape if yesterday's blue stretch is the same app as today's.
 *
 * The key is folded before hashing because "Google Chrome" and "google chrome "
 * are one app on a timeline, and two colours would split one stretch of a day
 * in half.
 */
export function screenAppColor(appName: string): ScreenAppColor {
  const key = appName.trim().toLowerCase();
  const bucket = Number(screenAppColorHash(key) % SCREEN_APP_HUE_BUCKETS);
  return screenAppColorForBucket(bucket);
}

export type ScreenActivityBlock = {
  readonly app: string;
  readonly appBundleId: string;
  /** Epoch milliseconds, inclusive. */
  readonly startedAt: number;
  /** Epoch milliseconds, exclusive; the block is drawn up to but not at it. */
  readonly endedAt: number;
  readonly startIndex: number;
  readonly endIndex: number;
};

/** Swift's `RewindTrackWindow.medianInterval`: measured, not assumed — capture rate is a user setting. */
function medianIntervalMs(instants: readonly number[]): number {
  if (instants.length < 2) return 60_000;
  const gaps: number[] = [];
  for (let index = 1; index < instants.length; index += 1) {
    const gap = (instants[index] as number) - (instants[index - 1] as number);
    if (gap > 0) gaps.push(gap);
  }
  if (gaps.length === 0) return 60_000;
  gaps.sort((left, right) => left - right);
  return gaps[Math.floor(gaps.length / 2)] as number;
}

/** `RewindTrackWindow.minimumSpan`: a minute across the bar is already finer than any capture interval. */
const SCREEN_TRACK_MINIMUM_SPAN_MS = 60_000;

/**
 * Contiguous runs of one app, the shape the Rewind track draws
 * (`RewindTrackWindow.blocks`). A run ends where the next app's first frame
 * begins, so the blocks tile the day without gaps; the final run is extended
 * by one median sampling interval, since its last frame represents a span of
 * time and not an instant.
 */
export function screenActivityBlocks(
  frames: readonly ScreenTimelineFrame[],
): readonly ScreenActivityBlock[] {
  if (frames.length === 0) return [];
  const instants = frames.map((frame) => Date.parse(frame.captured_at));
  if (instants.some((instant) => !Number.isFinite(instant))) return [];
  const tail = medianIntervalMs(instants);
  const blocks: ScreenActivityBlock[] = [];
  let startIndex = 0;
  for (let index = 1; index <= frames.length; index += 1) {
    const ended = index === frames.length;
    const start = frames[startIndex] as ScreenTimelineFrame;
    if (!ended && (frames[index] as ScreenTimelineFrame).app_name === start.app_name) continue;
    blocks.push({
      app: start.app_name,
      appBundleId: start.app_bundle_id,
      startedAt: instants[startIndex] as number,
      endedAt: ended
        ? (instants[frames.length - 1] as number) + tail
        : (instants[index] as number),
      startIndex,
      endIndex: index - 1,
    });
    startIndex = index;
  }
  return blocks;
}

/** Inclusive span the track draws, padded so end blocks clear the rounded corners. */
export function screenTrackRange(
  frames: readonly ScreenTimelineFrame[],
): { readonly startedAt: number; readonly endedAt: number } | null {
  if (frames.length === 0) return null;
  const instants = frames.map((frame) => Date.parse(frame.captured_at));
  if (instants.some((instant) => !Number.isFinite(instant))) return null;
  const pad = Math.max(medianIntervalMs(instants), 30_000);
  const startedAt = (instants[0] as number) - pad;
  const endedAt = Math.max((instants.at(-1) as number) + pad, startedAt + SCREEN_TRACK_MINIMUM_SPAN_MS);
  return { startedAt, endedAt };
}

const SCREEN_TICK_STEPS_MS: readonly number[] = [
  60_000, 300_000, 600_000, 900_000, 1_800_000,
  3_600_000, 7_200_000, 10_800_000, 21_600_000, 43_200_000,
];
const SCREEN_TICK_MAX = 12;

/** Coarsest step that keeps the track under `SCREEN_TICK_MAX` labels. */
export function screenTrackTickStepMs(spanMs: number): number {
  for (const step of SCREEN_TICK_STEPS_MS) {
    if (spanMs / step <= SCREEN_TICK_MAX) return step;
  }
  return 86_400_000;
}

/** Tick instants on wall-clock boundaries, so labels read `2 PM` and not `2:07 PM`. */
export function screenTrackTicks(startedAt: number, endedAt: number): readonly number[] {
  const span = endedAt - startedAt;
  if (!(span > 0)) return [];
  const step = screenTrackTickStepMs(span);
  const ticks: number[] = [];
  let instant = Math.ceil(startedAt / step) * step;
  while (instant <= endedAt && ticks.length <= SCREEN_TICK_MAX + 2) {
    ticks.push(instant);
    instant += step;
  }
  return ticks;
}

/** Track geometry, in logical pixels, ported from `RewindTrackNSView`. */
export const SCREEN_TRACK_HEIGHT = 56;
export const SCREEN_TRACK_BAR_HEIGHT = 26;
export const SCREEN_TRACK_BADGE_SIZE = 18;
/**
 * Width the track assumes before it has been measured. A badge row that only
 * appears after a resize observation flashes in on first paint; placing at the
 * nominal panel width and refining on measurement does not.
 */
export const SCREEN_TRACK_ASSUMED_WIDTH = 960;
const SCREEN_TRACK_BADGE_SPACING = SCREEN_TRACK_BADGE_SIZE + 5;
/**
 * Narrowest visible block that may still carry a badge — deliberately smaller
 * than the badge itself, which is allowed to overhang. Requiring a block to be
 * wider than its own badge reduces a whole day at day zoom to one badge.
 */
const SCREEN_TRACK_MIN_BADGE_WIDTH = 4;

export type ScreenTrackBadge = {
  readonly app: string;
  readonly appBundleId: string;
  readonly blockIndex: number;
  /** Centre as a 0–1 fraction of the track's width. */
  readonly centerFraction: number;
};

/**
 * Which blocks earn an app badge, and where, ported from
 * `RewindTrackNSView.badgePlacements`.
 *
 * Longest-first with overlap rejection, not "every block wide enough to hold
 * one". At a full day's zoom even a twenty-minute stretch is about 16px wide,
 * so the naive rule either badges everything into an unreadable smear or
 * badges nothing. The stretches worth recognising at a glance are the long
 * ones; a block is drawn either way, badge or no badge.
 */
export function screenTrackBadges(
  blocks: readonly ScreenActivityBlock[],
  range: { readonly startedAt: number; readonly endedAt: number },
  trackWidth: number,
): readonly ScreenTrackBadge[] {
  const span = range.endedAt - range.startedAt;
  const width = trackWidth > 0 ? trackWidth : SCREEN_TRACK_ASSUMED_WIDTH;
  if (!(span > 0) || blocks.length === 0) return [];
  const x = (instant: number): number => ((instant - range.startedAt) / span) * width;
  const ordered = blocks
    .map((block, index) => ({ block, index }))
    .sort((left, right) => {
      const leftSpan = left.block.endedAt - left.block.startedAt;
      const rightSpan = right.block.endedAt - right.block.startedAt;
      if (leftSpan !== rightSpan) return rightSpan - leftSpan;
      return left.index - right.index;
    });
  const placed: ScreenTrackBadge[] = [];
  for (const { block, index } of ordered) {
    const left = x(block.startedAt);
    const right = x(block.endedAt);
    if (right < 0 || left > width) continue;
    const visibleLeft = Math.max(0, left);
    const visibleRight = Math.min(width, right);
    if (visibleRight - visibleLeft < SCREEN_TRACK_MIN_BADGE_WIDTH) continue;
    const centre = Math.min(
      Math.max((visibleLeft + visibleRight) / 2, SCREEN_TRACK_BADGE_SIZE / 2 + 1),
      width - SCREEN_TRACK_BADGE_SIZE / 2 - 1,
    );
    if (placed.some((badge) => Math.abs(badge.centerFraction * width - centre) < SCREEN_TRACK_BADGE_SPACING)) {
      continue;
    }
    placed.push({
      app: block.app,
      appBundleId: block.appBundleId,
      blockIndex: index,
      centerFraction: centre / width,
    });
  }
  return placed.sort((left, right) => left.centerFraction - right.centerFraction);
}

/** How a tick is labelled, which depends on how far apart the ticks are. */
export function screenTrackTickFormat(stepMs: number): Intl.DateTimeFormatOptions {
  if (stepMs >= 86_400_000) return { month: "short", day: "numeric" };
  if (stepMs >= 3_600_000) return { hour: "numeric" };
  return { hour: "numeric", minute: "2-digit" };
}

/**
 * The capture nearest an instant, by binary search
 * (`RewindTrackNSView.nearestIndex`). A time-linear track has to answer "which
 * frame is under the pointer" on every pointer sample of a scrub, and a linear
 * scan over a day of frames puts that on the frame budget.
 */
export function screenNearestFrameIndex(
  frames: readonly ScreenTimelineFrame[],
  instant: number,
): number | null {
  if (frames.length === 0) return null;
  const at = (index: number): number => Date.parse((frames[index] as ScreenTimelineFrame).captured_at);
  let low = 0;
  let high = frames.length - 1;
  if (instant <= at(low)) return low;
  if (instant >= at(high)) return high;
  while (low + 1 < high) {
    const mid = Math.floor((low + high) / 2);
    if (at(mid) <= instant) low = mid;
    else high = mid;
  }
  return instant - at(low) <= at(high) - instant ? low : high;
}

/** The monogram a badge falls back to when no app icon is available. */
export function screenAppMonogram(appName: string): string {
  const first = Array.from(appName.trim())[0];
  return first === undefined ? "?" : first.toLocaleUpperCase();
}

/**
 * The first frame of the previous or next app run, for the chevrons welded to
 * the frame. Ported from `RewindStageChrome.adjacentSegmentIndex`.
 *
 * Stepping back from mid-run skips over the run you are in and lands on the
 * *start of the one before it* — "previous app" means another app, not an
 * earlier moment in this one. `null` at either end, and the caller hides the
 * chevron rather than disabling it: a disabled control still advertises a step
 * that does not exist.
 */
export function screenAdjacentAppIndex(
  frames: readonly ScreenTimelineFrame[],
  index: number,
  direction: "previous" | "next",
): number | null {
  if (frames.length === 0) return null;
  const cursor = Math.min(Math.max(0, index), frames.length - 1);
  const appAt = (at: number): string => (frames[at] as ScreenTimelineFrame).app_name;
  if (direction === "next") {
    for (let probe = cursor + 1; probe < frames.length; probe += 1) {
      if (appAt(probe) !== appAt(cursor)) return probe;
    }
    return null;
  }
  let runStart = cursor;
  while (runStart > 0 && appAt(runStart - 1) === appAt(cursor)) runStart -= 1;
  if (runStart === 0) return null;
  const previousApp = appAt(runStart - 1);
  let previousStart = runStart - 1;
  while (previousStart > 0 && appAt(previousStart - 1) === previousApp) previousStart -= 1;
  return previousStart;
}

export function screenPausedMessageKey(
  reason: string | null,
): "screen.capturePausedExcluded" | "screen.capturePausedIdle" | "screen.capturePaused" {
  if (reason === "excluded") return "screen.capturePausedExcluded";
  if (reason === "idle") return "screen.capturePausedIdle";
  return "screen.capturePaused";
}
