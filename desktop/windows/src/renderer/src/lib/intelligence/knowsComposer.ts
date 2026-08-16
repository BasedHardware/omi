// The Home "knows" list composer (mac parity: HomeKnowsComposer.swift, ported
// rule-for-rule). Pure: the page owns the rotation counter and dismissed-id
// set; this module just composes at most four diverse rows from the sources.
//
// Slot rules, verbatim from mac:
//   1. the first fresh (non-dismissed) task;
//   2. the first insight, else the action tip as a question row;
//   3. the second fresh task, only when there are at least two and taking it
//      still leaves room for the ask;
//   4. the ask (first rotated question that is not the tip), when room remains.
// Each source rotates independently by k = ((rotation % n) + n) % n, so one
// shared counter advances all three without ever going out of range.

export type KnowsRowKind = 'task' | 'insight' | 'question'

export type KnowsRow = {
  /** 'task-<id>' | 'insight-<id>' | 'question-<text>' — question rows dedupe by
   *  exact trimmed text because the text IS the id, mirroring mac. */
  id: string
  kind: KnowsRowKind
  text: string
}

export type KnowsSources = {
  tasks: { id: string; text: string }[]
  insights: { id: string; text: string }[]
  tip: string
  questions: string[]
  dismissedTaskIds: ReadonlySet<string>
  rotation: number
}

export const MAX_KNOWS_ROWS = 4

function rotated<T>(items: T[], rotation: number): T[] {
  const n = items.length
  if (n === 0) return items
  const k = ((rotation % n) + n) % n
  return [...items.slice(k), ...items.slice(0, k)]
}

export function composeKnowsRows(sources: KnowsSources): KnowsRow[] {
  const freshTasks = rotated(
    sources.tasks.filter((t) => !sources.dismissedTaskIds.has(t.id)),
    sources.rotation
  )
  const insights = rotated(sources.insights, sources.rotation)

  const seenQuestions = new Set<string>()
  const questions: string[] = []
  for (const q of rotated(sources.questions, sources.rotation)) {
    const trimmed = q.trim()
    if (!trimmed || seenQuestions.has(trimmed)) continue
    seenQuestions.add(trimmed)
    questions.push(trimmed)
  }
  const ask = questions.find((q) => q !== sources.tip) ?? null

  const rows: KnowsRow[] = []
  if (freshTasks.length > 0) {
    rows.push({ id: `task-${freshTasks[0].id}`, kind: 'task', text: freshTasks[0].text })
  }
  if (insights.length > 0) {
    rows.push({ id: `insight-${insights[0].id}`, kind: 'insight', text: insights[0].text })
  } else if (sources.tip) {
    rows.push({ id: `question-${sources.tip}`, kind: 'question', text: sources.tip })
  }
  if (freshTasks.length > 1 && (ask === null || rows.length < MAX_KNOWS_ROWS - 1)) {
    rows.push({ id: `task-${freshTasks[1].id}`, kind: 'task', text: freshTasks[1].text })
  }
  if (ask !== null && rows.length < MAX_KNOWS_ROWS) {
    rows.push({ id: `question-${ask}`, kind: 'question', text: ask })
  }
  return rows
}

/** Rotation only helps when some source has an alternative to show. */
export function canRotateKnows(
  taskCount: number,
  insightCount: number,
  questionCount: number
): boolean {
  return taskCount > 2 || insightCount > 1 || questionCount > 1
}

/** The action tip (mac: homeActionTip): pushy when the open-task pile is deep,
 *  reflective otherwise. */
export function knowsActionTip(openTaskCount: number): string {
  return openTaskCount >= 5
    ? 'Sort my open tasks — which 3 actually matter today?'
    : 'Recap what I got done today'
}
