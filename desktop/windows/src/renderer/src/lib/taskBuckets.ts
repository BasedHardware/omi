// Task due-date bucketing and the due-badge label for the Tasks page. Extracted
// from pages/Tasks.tsx so the rules are unit-testable against the shared
// contracts/parity fixtures (see contracts/parity/README.md).

export function startOfDay(ms: number): number {
  const d = new Date(ms)
  d.setHours(0, 0, 0, 0)
  return d.getTime()
}

/** Start of the local day a whole number of calendar days away from the day
 *  containing `ms`. Date.setDate handles DST shifts and month/year boundaries;
 *  a fixed `± 86_400_000` offset is 23h/25h wrong on the two DST-transition
 *  days each year, which mis-labels the neighbor day. */
export function startOfDayOffset(ms: number, days: number): number {
  const d = new Date(startOfDay(ms))
  d.setDate(d.getDate() + days)
  d.setHours(0, 0, 0, 0)
  return d.getTime()
}

export type Bucket = 'today' | 'tomorrow' | 'later' | 'nodate'

// Four due-date buckets, matching Mac's TaskCategory (Today · Tomorrow · Later ·
// No Deadline). Overdue tasks fold into Today — there is no separate Overdue
// section — mirroring Mac's `categoryFor` (`dueAt < startOfTomorrow → .today`,
// TasksPage.swift). The Flutter app uses a different model (a fifth Overdue
// bucket plus a 7-day aging rule for dateless tasks); both models are pinned in
// contracts/parity/task_due_buckets.json until the platforms converge.
export function bucketOf(t: { dueAt: number | null }, now: number = Date.now()): Bucket {
  if (t.dueAt == null) return 'nodate'
  const due = startOfDay(t.dueAt)
  const today = startOfDay(now)
  if (due <= today) return 'today' // overdue + today
  if (due === startOfDayOffset(now, 1)) return 'tomorrow'
  return 'later'
}

export function formatDue(ms: number, now: number = Date.now()): string {
  const d = new Date(ms)
  if (Number.isNaN(d.getTime())) return ''
  const due = startOfDay(d.getTime())
  if (due === startOfDay(now)) return 'Today'
  if (due === startOfDayOffset(now, 1)) return 'Tomorrow'
  if (due === startOfDayOffset(now, -1)) return 'Yesterday'
  const sameYear = d.getFullYear() === new Date(now).getFullYear()
  return d.toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
    ...(sameYear ? {} : { year: 'numeric' })
  })
}
