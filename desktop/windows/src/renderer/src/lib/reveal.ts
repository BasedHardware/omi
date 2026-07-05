// Pure core of the smooth text reveal (ref. upstash.com/blog/smooth-streaming):
// decouples the network cadence from the reading cadence. The chat hook
// accumulates the full text as SSE deltas arrive; here we decide how many
// characters to reveal each frame so the text "types" evenly instead of
// landing in bulky jumps.

// Base pace: ~5ms per character (~200 cps).
const MS_PER_CHAR = 5
// Backlog cap: with a large backlog, accelerate to drain it within at most
// this many frames, so the visible text never trails the stream by more than
// a few frames (fast models would otherwise fall seconds behind).
const CATCH_UP_FRAMES = 8

// How many characters to reveal on this frame.
// - remaining: characters not yet shown (full length - already revealed).
// - elapsedMs: time since the previous frame.
export function revealStep(remaining: number, elapsedMs: number): number {
  if (remaining <= 0) return 0
  const base = elapsedMs / MS_PER_CHAR
  const catchUp = remaining / CATCH_UP_FRAMES
  const step = Math.ceil(Math.max(base, catchUp))
  return Math.min(remaining, Math.max(1, step))
}
