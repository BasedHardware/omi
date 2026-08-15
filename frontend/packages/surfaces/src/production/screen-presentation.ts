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
