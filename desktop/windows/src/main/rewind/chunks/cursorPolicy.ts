/**
 * The decision half of a chunk read cursor.
 *
 * A chunk is inter-frame compressed, so there is no random access to frame *n*:
 * reaching it means decoding everything before it. Opening a fresh decoder per
 * request therefore makes a scrub quadratic in the chunk's length — the user
 * pays for frame 0 again on every step. macOS measured exactly this on a real
 * 18-frame chunk: 728 ms to scrub it (40.5 ms/frame) reopening each time,
 * against 59 ms (3.3 ms/frame) keeping the reader alive, 12.3x faster and
 * pixel-identical at every offset (`RewindVideoFrameCursor.swift`).
 *
 * Keeping a decoder alive between requests is the whole trick, and deciding
 * *when* it can be kept is the only part of it that needs no codec. That part
 * is here, as a pure state machine, so the rule can be tested directly instead
 * of inferred from timings. The decoding itself is WebCodecs and lives in the
 * renderer (`renderer/src/rewind/chunkDecoder.ts`).
 *
 * The tape is one-way: a cursor can serve any offset at or after the one it is
 * parked on. A backward step, or a step into a different chunk, reopens —
 * there is nothing cheaper available for either.
 */

export type CursorAction =
  /** Advance the live decoder by `advanceBy` frames to reach the request. */
  | { kind: 'advance'; advanceBy: number }
  /** Discard any live decoder, open `chunkPath` at 0, then advance. */
  | { kind: 'reopen'; chunkPath: string; advanceBy: number }

export type CursorState = {
  /** Chunk the live decoder is reading, or null when there is none. */
  chunkPath: string | null
  /** Offset the next decoded frame will be. */
  nextOffset: number
  /** Set once the decoder has run past the end; the tape cannot be reused. */
  finished: boolean
}

export function newCursor(): CursorState {
  return { chunkPath: null, nextOffset: 0, finished: false }
}

/**
 * Whether `state` can reach `frameOffset` of `chunkPath` without reopening.
 *
 * This is macOS's `canServe` unchanged, including the detail that an offset
 * *equal* to `nextOffset` is servable: the tape is parked before that frame,
 * not after it.
 */
export function canServe(state: CursorState, chunkPath: string, frameOffset: number): boolean {
  return !state.finished && state.chunkPath === chunkPath && frameOffset >= state.nextOffset
}

/**
 * What to do to serve `frameOffset` of `chunkPath`.
 *
 * Note the asymmetry with `canServe`: a reopen always starts at offset 0, so
 * the advance for a reopen is the offset itself.
 */
export function planRead(state: CursorState, chunkPath: string, frameOffset: number): CursorAction {
  if (!Number.isInteger(frameOffset) || frameOffset < 0) {
    throw new Error(`frame offset must be a non-negative integer, got ${frameOffset}`)
  }
  if (canServe(state, chunkPath, frameOffset)) {
    return { kind: 'advance', advanceBy: frameOffset - state.nextOffset }
  }
  return { kind: 'reopen', chunkPath, advanceBy: frameOffset }
}

/**
 * Record that a read succeeded, parking the tape after the frame just served.
 *
 * Takes the action that was performed rather than re-deriving it, so a caller
 * that reopened for its own reasons cannot leave the state claiming to still be
 * on the old chunk.
 */
export function afterRead(
  state: CursorState,
  action: CursorAction,
  frameOffset: number
): CursorState {
  return {
    chunkPath: action.kind === 'reopen' ? action.chunkPath : state.chunkPath,
    nextOffset: frameOffset + 1,
    finished: false
  }
}

/**
 * Record that a read ran off the end of the chunk.
 *
 * On macOS this is a normal outcome, because the chunk being read can be the
 * one still being written. Here it never is: a chunk is registered in the
 * database only after it has been written whole and read back, so running off
 * the end means the row's offset disagrees with the file. The cursor is retired
 * either way — the difference is that the caller should treat it as a broken
 * frame rather than "not yet".
 */
export function afterExhausted(state: CursorState): CursorState {
  return { ...state, finished: true }
}
