// Shared task field vocabulary for the Tasks surface: the priority model and the
// quick due-date chips. The local row's `priority` is a free string column
// ('high' | 'medium' | 'low' per the store contract, Windows-local-only — the
// backend has no priority field), so normalize defensively at the edge.

export type TaskPriority = 'high' | 'medium' | 'low'

/** Detail-panel chip order — mac's prioritySection declares low → medium → high. */
export const PRIORITY_ORDER: readonly TaskPriority[] = ['low', 'medium', 'high']

export function normalizePriority(raw: string | null | undefined): TaskPriority | null {
  const v = (raw ?? '').trim().toLowerCase()
  return v === 'high' || v === 'medium' || v === 'low' ? v : null
}

export const PRIORITY_LABEL: Record<TaskPriority, string> = {
  high: 'High',
  medium: 'Medium',
  low: 'Low'
}

/** Tailwind text tint per priority for badges/flags. No purple (brand rule). */
export const PRIORITY_TINT: Record<TaskPriority, string> = {
  high: 'text-rose-300/90',
  medium: 'text-amber-300/90',
  low: 'text-sky-300/80'
}

// --- Quick due chips -------------------------------------------------------

// The store speaks epoch ms. Quick chips pin the time to LOCAL NOON, matching the
// page's date-input bridge (dateInputToMs uses T12:00:00), so a task due "today"
// never slips a day across time zones or DST edges.

function atLocalNoon(d: Date): number {
  const noon = new Date(d)
  noon.setHours(12, 0, 0, 0)
  return noon.getTime()
}

/** The composer's one-click "Today" due date: end of the current local day.
 *  Mirrors mac's `todayDueAt` exactly (23:59:00 local, TasksPage.swift), so a
 *  task created "for today" stays in the Today bucket all day rather than
 *  flipping overdue at noon. */
export function todayDueAtMs(now: number = Date.now()): number {
  const d = new Date(now)
  d.setHours(23, 59, 0, 0)
  return d.getTime()
}

export function dueTodayMs(now: number = Date.now()): number {
  return atLocalNoon(new Date(now))
}

export function dueTomorrowMs(now: number = Date.now()): number {
  const d = new Date(now)
  // setDate handles DST and month/year boundaries; a fixed +86_400_000 is
  // 23h/25h wrong on the two DST-transition days each year.
  d.setDate(d.getDate() + 1)
  return atLocalNoon(d)
}

export function dueNextWeekMs(now: number = Date.now()): number {
  const d = new Date(now)
  d.setDate(d.getDate() + 7)
  return atLocalNoon(d)
}

export type QuickDueChip = { key: 'today' | 'tomorrow' | 'nextWeek'; label: string; ms: number }

export function quickDueChips(now: number = Date.now()): QuickDueChip[] {
  return [
    { key: 'today', label: 'Today', ms: dueTodayMs(now) },
    { key: 'tomorrow', label: 'Tomorrow', ms: dueTomorrowMs(now) },
    { key: 'nextWeek', label: 'Next week', ms: dueNextWeekMs(now) }
  ]
}
