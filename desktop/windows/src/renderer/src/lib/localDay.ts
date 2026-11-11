// Local-calendar-day helpers shared by the renderer's conversation date
// grouping and task bucketing. The local day is the product's grouping unit
// (pinned by contracts/parity/day_keys.json); keep the rule in one place.

/** Local-midnight epoch ms of the day containing `ms`. */
export function startOfLocalDay(ms: number): number {
  const d = new Date(ms)
  d.setHours(0, 0, 0, 0)
  return d.getTime()
}

/** Inclusive end-of-day (23:59:59.999 local) epoch ms — for date-range upper bounds. */
export function endOfLocalDay(ms: number): number {
  const d = new Date(ms)
  d.setHours(23, 59, 59, 999)
  return d.getTime()
}

/** Start of the local day a whole number of calendar days away from the day
 *  containing `ms`. Date.setDate handles DST shifts and month/year boundaries;
 *  a fixed `± 86_400_000` offset is 23h/25h wrong on the two DST-transition
 *  days each year, which mis-labels the neighbor day. */
export function startOfDayOffset(ms: number, days: number): number {
  const d = new Date(startOfLocalDay(ms))
  d.setDate(d.getDate() + days)
  d.setHours(0, 0, 0, 0)
  return d.getTime()
}
