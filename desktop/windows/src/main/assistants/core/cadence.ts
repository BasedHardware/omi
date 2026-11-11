/** Has the fixed extraction interval elapsed since the last analysis? */
export function intervalElapsed(timeSinceLastMs: number, intervalMs: number): boolean {
  return timeSinceLastMs >= intervalMs
}
