function localDayKey(ts: number): string {
  const d = new Date(ts)
  return `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`
}

// True when `now` falls on a different local calendar day than `prevLastUsed`
// (or when there is no previous timestamp). Drives the distinct_days counter.
export function isNewLocalDay(prevLastUsed: number | null, now: number): boolean {
  if (prevLastUsed == null) return true
  return localDayKey(prevLastUsed) !== localDayKey(now)
}
