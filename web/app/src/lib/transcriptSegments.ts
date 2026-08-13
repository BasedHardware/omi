/**
 * Bounded live-transcript segment store (#5399).
 *
 * Long Chrome recording sessions kept an unbounded `segments[]` in React and
 * re-rendered the full list (no virtualization) on every STT update. That
 * degrades continuously over ~1h. These helpers upsert by id and trim oldest
 * segments so the live UI stays bounded; server-side audio still holds the
 * full session for finalize-on-stop.
 */

type LiveTranscriptSegmentLike = {
  id: string;
  text: string;
  speaker: number;
  isUser: boolean;
  timestamp: number;
};

/** Keep recent segments for ~1–2h of typical speech without unbounded DOM growth. */
export const DEFAULT_MAX_LIVE_SEGMENTS = 400;

/**
 * Upsert by segment id (partial STT updates reuse the same id).
 * Returns the previous array reference when nothing changed.
 */
export function upsertTranscriptSegment<T extends LiveTranscriptSegmentLike>(
  segments: readonly T[],
  segment: T,
): T[] {
  const existingIndex = segments.findIndex((s) => s.id === segment.id);
  if (existingIndex >= 0) {
    const existing = segments[existingIndex];

    // STT updates are frequently partial. We still want to preserve object
    // identity (no rerender) when the meaningful fields match.
    if (
      existing.text === segment.text &&
      existing.speaker === segment.speaker &&
      existing.isUser === segment.isUser &&
      existing.timestamp === segment.timestamp
    ) {
      return segments as T[];
    }

    const updated = segments.slice() as T[];
    updated[existingIndex] = segment;
    return updated;
  }
  return [...segments, segment];
}

/**
 * Drop oldest segments when over budget. Always keeps [preserveId] if present
 * so an in-flight partial update is never trimmed away mid-edit.
 */
export function trimTranscriptSegments<T extends { id: string }>(
  segments: readonly T[],
  maxSegments: number,
  preserveId?: string,
): T[] {
  if (maxSegments <= 0) return [];
  if (segments.length <= maxSegments) return segments as T[];

  let trimmed = segments.slice(segments.length - maxSegments) as T[];
  if (preserveId && !trimmed.some((s) => s.id === preserveId)) {
    const preserved = segments.find((s) => s.id === preserveId);
    if (preserved) {
      trimmed = [preserved, ...trimmed.slice(1)];
    }
  }
  return trimmed;
}

/** Upsert then trim — the single seam `useRecording` should call. */
export function applyLiveTranscriptSegment<T extends LiveTranscriptSegmentLike>(
  segments: readonly T[],
  segment: T,
  maxSegments: number = DEFAULT_MAX_LIVE_SEGMENTS,
): T[] {
  return trimTranscriptSegments(
    upsertTranscriptSegment(segments, segment),
    maxSegments,
    segment.id,
  );
}
