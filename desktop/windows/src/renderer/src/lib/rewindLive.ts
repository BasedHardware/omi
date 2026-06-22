import type { RewindFrame } from '../../../shared/types'

/**
 * Merge newly-captured frames into the existing list: dedupe by id and keep the
 * result sorted by timestamp ascending. Used by the Rewind timeline's live poll
 * so it can extend the view without reloading (and without resetting the cursor).
 */
export function mergeFrames(prev: RewindFrame[], incoming: RewindFrame[]): RewindFrame[] {
  if (incoming.length === 0) return prev
  // ts is the timeline's identity (the cursor and nearestFrameIndex key on it),
  // and unlike the DB id it's always present, so it's the natural dedupe key.
  const byTs = new Map<number, RewindFrame>()
  for (const fr of prev) byTs.set(fr.ts, fr)
  for (const fr of incoming) byTs.set(fr.ts, fr)
  return [...byTs.values()].sort((a, b) => a.ts - b.ts)
}

/**
 * Whether the viewer is "following live" — i.e. parked at (or past) the newest
 * frame. When true, new frames should advance the cursor to the latest; when
 * false, the user has scrubbed back and we must leave their position alone.
 */
export function isFollowingLive(cursorTs: number, frames: RewindFrame[]): boolean {
  if (frames.length === 0) return true
  return cursorTs >= frames[frames.length - 1].ts
}
