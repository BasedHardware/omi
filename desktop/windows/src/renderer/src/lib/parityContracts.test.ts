// Windows conformance suite for the shared cross-platform parity contracts
// (contracts/parity/README.md). Runs the repo-root fixture vectors through the
// REAL production rules: task due-date bucketing (taskBuckets.bucketOf, the
// fold_overdue model shared with macOS), local-day conversation grouping
// (filtering.startOfLocalDay / groupConversationsByDate), and relative day
// labels (formatDue badge + conversation section headers), including the DST
// transition-day cases that only execute on runners whose zone observes the
// transition (counted skips elsewhere; the non-DST cases always run).
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import { bucketOf, formatDue, type Bucket } from './taskBuckets'
import { groupConversationsByDate, startOfLocalDay } from './conversations/filtering'
import type { ConversationRow } from './pageCache'

function fixture<T>(name: string): T {
  const path = fileURLToPath(new URL(`../../../../../../contracts/parity/${name}`, import.meta.url))
  return JSON.parse(readFileSync(path, 'utf8')) as T
}

/** Fixture local-time components [year, month, day, hour?, minute?] → epoch ms
 *  in the runner's zone (the contracts are calendar rules, zone-independent). */
type Components = [number, number, number, number?, number?]
const localMs = (c: Components): number => new Date(c[0], c[1] - 1, c[2], c[3] ?? 0, c[4] ?? 0).getTime()

const RELATIVE_LABELS = ['Today', 'Tomorrow', 'Yesterday']

describe('task due buckets (fold_overdue model)', () => {
  type BucketCase = {
    name: string
    now: Components
    due: Components | null
    created: Components | null
    expected: { fold_overdue: string; separate_overdue: string }
  }
  // Fixture bucket names → this platform's Bucket vocabulary. fold_overdue never
  // expects 'overdue'; an unmapped name fails loudly rather than passing vacuously.
  const BUCKET_MAP: Record<string, Bucket> = {
    today: 'today',
    tomorrow: 'tomorrow',
    later: 'later',
    no_deadline: 'nodate'
  }
  const { cases } = fixture<{ cases: BucketCase[] }>('task_due_buckets.json')
  it.each(cases)('$name', (c) => {
    const now = localMs(c.now)
    const dueAt = c.due === null ? null : localMs(c.due)
    expect(bucketOf({ dueAt }, now)).toBe(BUCKET_MAP[c.expected.fold_overdue])
  })
})

describe('local day keys', () => {
  type DayKeyCase = { name: string; utc: string; expected_by_offset: Record<string, string> }
  const pad = (n: number): string => String(n).padStart(2, '0')
  const { cases } = fixture<{ cases: DayKeyCase[] }>('day_keys.json')
  for (const c of cases) {
    const instant = Date.parse(c.utc)
    const offsetEast = -new Date(instant).getTimezoneOffset()
    const expected = c.expected_by_offset[String(offsetEast)]
    // Only cases whose fixture covers this runner's zone offset execute; offset 0
    // is always present so UTC CI runs every case.
    it.runIf(expected !== undefined)(`${c.name} (offset ${offsetEast})`, () => {
      const d = new Date(startOfLocalDay(instant))
      expect(`${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`).toBe(expected)
    })
  }
})

describe('relative day labels', () => {
  type LabelCase = {
    name: string
    now: Components
    target_day: Components
    requires_dst_transition_between?: [Components, Components]
    labels: { conversation_section: string | null; due_badge: string | null }
  }
  const transitionObserved = (c: LabelCase): boolean => {
    if (!c.requires_dst_transition_between) return true
    const [a, b] = c.requires_dst_transition_between
    return (
      new Date(a[0], a[1] - 1, a[2]).getTimezoneOffset() !== new Date(b[0], b[1] - 1, b[2]).getTimezoneOffset()
    )
  }
  const { cases } = fixture<{ cases: LabelCase[] }>('section_labels.json')
  for (const c of cases) {
    it.runIf(transitionObserved(c))(c.name, () => {
      const now = localMs(c.now)
      const targetNoon = localMs([c.target_day[0], c.target_day[1], c.target_day[2], 12, 0])

      const badge = formatDue(targetNoon, now)
      if (c.labels.due_badge === null) {
        expect(badge).toBeTruthy()
        expect(RELATIVE_LABELS).not.toContain(badge)
      } else {
        expect(badge).toBe(c.labels.due_badge)
      }

      const row = {
        id: 'parity-row',
        title: 'row',
        subtitle: '',
        preview: '',
        source: 'cloud',
        sortAt: targetNoon
      } as unknown as ConversationRow
      const sections = groupConversationsByDate([row], now)
      expect(sections).toHaveLength(1)
      const label = sections[0].label
      if (c.labels.conversation_section === null) {
        expect(label).toBeTruthy()
        expect(RELATIVE_LABELS).not.toContain(label)
      } else {
        expect(label).toBe(c.labels.conversation_section)
      }
    })
  }
})
