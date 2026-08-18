/**
 * Which stored frames become which chunk.
 *
 * This is the whole policy of compaction as a pure function, separate from the
 * encoder that executes it, because every rule here is a judgement that has to
 * survive review and none of it needs a codec to test.
 *
 * macOS makes these decisions live, inside `VideoChunkEncoder`, as frames
 * arrive. Windows makes them after the fact over frames already on disk. That
 * difference is deliberate and is the reason the two files look nothing alike:
 * see ARCHITECTURE.md. What is ported is the shape of a chunk — a 60-second
 * window of one screen geometry — because that is what makes inter-frame
 * compression pay.
 */

export type CompactableFrame = {
  id: number
  tsMs: number
  width: number
  height: number
  imagePath: string
}

export type PlannedChunk = {
  /** Local day the chunk is filed under, `YYYY-MM-DD`, from its first frame. */
  day: string
  /** Frames in capture order. Index in this array is the frame's chunk offset. */
  frames: CompactableFrame[]
  width: number
  height: number
}

/**
 * A chunk covers at most this much wall-clock time, measured from its first
 * frame. macOS uses the same 60 seconds (`VideoChunkEncoder.chunkDuration`).
 *
 * It also does the work of a gap rule for free: frames either side of a lunch
 * break are more than a minute apart, so they land in different chunks, which
 * is what you want anyway — the second one shares no pixels with the first and
 * would encode as a key frame regardless.
 */
export const CHUNK_WINDOW_MS = 60_000

/**
 * Runs shorter than this are left as JPEGs.
 *
 * Measured on this codebase's own capture path (1280x720, quality 0.7, one
 * frame per second, H.264 at 400 kbps): a 60-frame run compacted 6.95 MB of
 * JPEGs into 136 KB, a 51x reduction. A 5-frame run only reached 2.4x, because
 * the opening key frame is most of the chunk and there is almost nothing for it
 * to amortise over. The floor sits where the win stops being worth replacing a
 * directly-readable JPEG with a decode.
 */
export const MIN_FRAMES_PER_CHUNK = 8

/**
 * Frames younger than this are never compacted.
 *
 * Two reasons, and the second is the load-bearing one. The Rewind page is most
 * likely to be scrubbing recent frames, which are cheaper to serve straight
 * from disk. More importantly the OCR backlog sweep reads `image_path` for
 * every `indexed = 0` frame, and when the file is missing it marks the frame
 * indexed with empty text (`ocrService.ts`) — so compacting a frame out from
 * under it does not fail loudly, it silently costs that frame its OCR text
 * forever. The `indexed = 1` requirement below is the real guard; this delay is
 * the belt to its braces.
 */
export const COMPACTION_MIN_AGE_MS = 30 * 60_000

/** Local `YYYY-MM-DD` for a timestamp, matching `paths.ts`'s day-directory rule. */
export function localDayKey(tsMs: number): string {
  const d = new Date(tsMs)
  const month = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${d.getFullYear()}-${month}-${day}`
}

/**
 * Group eligible frames into chunks.
 *
 * `frames` must already be filtered to compaction candidates (`indexed = 1`,
 * still JPEG-backed) — that filter is SQL and lives in `chunkStore.ts`. This
 * function owns only the grouping, and it re-sorts rather than trusting the
 * caller's order, because chunk offsets are positions in the array it returns
 * and an out-of-order frame would silently mis-address every frame after it.
 *
 * A chunk is broken by any of:
 *  - more than `CHUNK_WINDOW_MS` since the chunk's first frame;
 *  - a change of frame geometry (a video track has exactly one size);
 *  - crossing into a different local day, so a chunk never spans two day
 *    directories and day-scoped retention can delete whole files.
 *
 * Groups below `MIN_FRAMES_PER_CHUNK` are dropped, not merged: merging them
 * would mean joining runs that are far apart in time, which is precisely the
 * case where inter-frame compression has nothing to work with.
 */
export function planChunks(frames: CompactableFrame[], nowMs: number): PlannedChunk[] {
  const eligible = frames
    .filter((f) => nowMs - f.tsMs >= COMPACTION_MIN_AGE_MS)
    .slice()
    .sort((a, b) => (a.tsMs !== b.tsMs ? a.tsMs - b.tsMs : a.id - b.id))

  const planned: PlannedChunk[] = []
  let current: CompactableFrame[] = []

  const flush = (): void => {
    if (current.length >= MIN_FRAMES_PER_CHUNK) {
      planned.push({
        day: localDayKey(current[0].tsMs),
        frames: current,
        width: current[0].width,
        height: current[0].height
      })
    }
    current = []
  }

  for (const frame of eligible) {
    if (frame.width <= 0 || frame.height <= 0) {
      // A row that never recorded its geometry cannot be given a video track
      // size. Leave it as a JPEG rather than guessing one.
      flush()
      continue
    }
    if (current.length > 0) {
      const first = current[0]
      const sameShape = frame.width === first.width && frame.height === first.height
      const inWindow = frame.tsMs - first.tsMs <= CHUNK_WINDOW_MS
      const sameDay = localDayKey(frame.tsMs) === localDayKey(first.tsMs)
      if (!sameShape || !inWindow || !sameDay) flush()
    }
    current.push(frame)
  }
  flush()

  return planned
}

/**
 * Bytes a plan is expected to reclaim, given the size of each frame's JPEG.
 *
 * Reported rather than acted on: the compactor logs what it is about to do so a
 * user who wonders where their disk went can see the answer, and so a run that
 * reclaims nothing is visible instead of silent.
 */
export function plannedJpegBytes(
  plan: PlannedChunk[],
  sizeOf: (frame: CompactableFrame) => number
): number {
  let total = 0
  for (const chunk of plan) for (const frame of chunk.frames) total += sizeOf(frame)
  return total
}
