// Pure rail maths, split out of SpineHourRail.tsx so that file only exports a
// component (the fast-refresh rule) and so these rules can be tested directly.

/** Rendered top to bottom: 23, 22, ... 0 - the same direction as the
 *  newest-first list beside it. A rail running the other way would make the eye
 *  travel backwards through the day while the list travels forwards. */
export const RENDERED_HOURS: number[] = Array.from({ length: 24 }, (_v, i) => 23 - i)

/** An hour at or above this share of the day's peak reads as busy. */
export const HOT_THRESHOLD = 0.6

/** Hours that always carry a label; the current hour is added to these. */
export const LABELLED_HOURS = new Set([0, 6, 12, 18])

/**
 * Per-hour share of the day's own peak, in 0..1.
 *
 * Normalised against THAT DAY's busiest hour, never against the account:
 * normalising globally would flatten every ordinary day into a blank column
 * next to the one week someone left capture running overnight.
 *
 * All zeroes when the day has no capture, which renders as a flat column rather
 * than dividing by zero.
 */
export function hourDensity(hourCounts: number[]): number[] {
  const peak = hourCounts.reduce((max, n) => Math.max(max, n), 0)
  if (peak <= 0) return new Array<number>(24).fill(0)
  return hourCounts.map((n) => n / peak)
}

/** The headline number and the caption that has to agree with it. */
export function railHeadline(momentCount: number | null): { value: string; caption: string } {
  // null is "not read yet" and must never render as 0: a day still being
  // counted would otherwise claim the user captured nothing.
  if (momentCount === null) return { value: '—', caption: 'counting screen moments' }
  return {
    value: momentCount.toLocaleString(),
    caption: momentCount === 1 ? 'screen moment' : 'screen moments'
  }
}

/** "1 conversation" / "4 conversations", or null when there were none. */
export function railFooter(conversationCount: number): string | null {
  if (conversationCount <= 0) return null
  return conversationCount === 1
    ? '1 conversation'
    : `${conversationCount.toLocaleString()} conversations`
}
