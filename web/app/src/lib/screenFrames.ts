/**
 * Pure helpers for the meeting-note screenshot carousel/lightbox.
 *
 * Deliberately dumb: banner promotion (which surviving frame becomes the
 * banner after a delete) is a server-side decision — the client-facing
 * `ConversationScreenFrame` doesn't even carry the `banner_suitability` score
 * the server ranks on (contract §7.3), so this module never guesses a
 * promotion. Every mutation hook call returns a fresh, authoritative
 * `ConversationScreenFrameSet` from the server; these helpers only work out
 * how the *local UI* (lightbox index) should react to a strip that just
 * changed length.
 */

import type {
  ConversationScreenFrame,
  ConversationScreenFrameSet,
} from '@/types/conversation';

/**
 * Steps a lightbox index by one frame, wrapping around both ends of the strip.
 * Returns 0 for an empty strip (caller should not be showing a lightbox then).
 */
export function stepFrameIndex(
  currentIndex: number,
  length: number,
  delta: 1 | -1,
): number {
  if (length <= 0) return 0;
  return (currentIndex + delta + length) % length;
}

/**
 * After the strip shrinks (a frame was deleted), works out which index the
 * lightbox should now show. Returns null when the strip is now empty — the
 * caller should close the lightbox rather than show a blank one.
 *
 * Clamping (not re-finding a specific id) is intentional: the frame that
 * slid into the deleted position is the natural "next" thing to look at, and
 * if the deleted frame was last, this lands on the new last frame.
 */
export function resolveIndexAfterRemoval(
  currentIndex: number,
  newLength: number,
): number | null {
  if (newLength <= 0) return null;
  return Math.min(currentIndex, newLength - 1);
}

/** Locates a frame's index within the strip by id, or -1 if it's not there. */
export function findFrameIndex(
  strip: ConversationScreenFrame[],
  frameId: string,
): number {
  return strip.findIndex((frame) => frame.id === frameId);
}

/** The lightbox index the banner always occupies when present. */
export const BANNER_LIGHTBOX_INDEX = 0;

/**
 * The lightbox's fixed navigation order: the banner first (when present),
 * then the strip in rank order. The banner is the largest image on the page
 * and is clickable like any strip thumbnail, so it belongs in the same
 * step-through sequence rather than a disjoint one — deleting it goes
 * through the same server-decided-promotion path as deleting a strip frame
 * (contract §7.3), and the client only ever re-reads what the server
 * returns.
 */
export function buildLightboxFrames(
  set: ConversationScreenFrameSet | null | undefined,
): ConversationScreenFrame[] {
  if (!set) return [];
  // `strip` is optional in the generated schema (absent means empty).
  const strip = set.strip ?? [];
  return set.banner ? [set.banner, ...strip] : strip;
}

/**
 * Maps a strip-relative index (what `ConversationScreenFrameCarousel`
 * reports on click) to its index in the combined banner+strip lightbox
 * order — offset by one when a banner occupies slot 0.
 */
export function stripFrameLightboxIndex(
  set: ConversationScreenFrameSet | null | undefined,
  stripIndex: number,
): number {
  return (set?.banner ? 1 : 0) + stripIndex;
}

/**
 * True when there is nothing to render at all: no banner and an empty strip.
 * Both the banner and carousel must render nothing (no empty state) in this
 * case — see contract §9.
 */
export function isFrameSetEmpty(
  set: ConversationScreenFrameSet | null | undefined,
): boolean {
  return !set || (!set.banner && (set.strip ?? []).length === 0);
}
