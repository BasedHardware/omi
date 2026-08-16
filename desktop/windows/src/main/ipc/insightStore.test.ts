// Proactive Insights history CRUD, proven against a REAL SQLite database via
// node:sqlite. Like dbTasks.test.ts, this imports the SAME symbols production
// runs — the DDL (INSIGHTS_SCHEMA, the exact string db.ts execs) and the exported
// *On(db, …) functions — so the schema and SQL can't drift from prod (the
// SQL-drift trap this program has hit before). db.ts itself still can't import
// here (better-sqlite3/electron), but its logic lives in insightStore.ts.
import { DatabaseSync } from 'node:sqlite'
import { beforeEach, describe, expect, it } from 'vitest'
import {
  INSIGHTS_SCHEMA,
  INSIGHT_HISTORY_CAP,
  insertInsightOn,
  recentInsightsOn,
  dismissInsightOn,
  dismissAllInsightsOn,
  clearInsightsOn,
  type InsightStoreDb
} from './insightStore'
import type { InsightPayload } from '../../shared/types'

function makeDb(): InsightStoreDb {
  const db = new DatabaseSync(':memory:')
  db.exec(INSIGHTS_SCHEMA)
  return db as unknown as InsightStoreDb
}

let db: InsightStoreDb
beforeEach(() => {
  db = makeDb()
})

function payload(overrides: Partial<InsightPayload> & { headline: string }): InsightPayload {
  return {
    advice: 'do the thing',
    reasoning: 'because it helps',
    category: 'productivity',
    sourceApp: 'Slack',
    confidence: 0.8,
    ...overrides
  }
}

describe('schema', () => {
  it('creates the insights table', () => {
    const names = (
      db.prepare("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name").all() as {
        name: string
      }[]
    ).map((r) => r.name)
    expect(names).toContain('insights')
  })
})

describe('insert + recent round-trip', () => {
  it('round-trips every mapped column with camelCase aliases', () => {
    const id = insertInsightOn(
      db,
      payload({
        headline: 'Take a break',
        advice: 'You have been heads-down 2h',
        reasoning: 'long focus block detected',
        category: 'health',
        sourceApp: 'VS Code',
        confidence: 0.95
      }),
      1000
    )
    expect(id).toBeGreaterThan(0)

    const list = recentInsightsOn(db, 100)
    expect(list).toHaveLength(1)
    const r = list[0]
    expect(r).toMatchObject({
      id,
      ts: 1000,
      headline: 'Take a break',
      advice: 'You have been heads-down 2h',
      reasoning: 'long focus block detected',
      category: 'health',
      sourceApp: 'VS Code',
      confidence: 0.95,
      dismissed: 0
    })
  })

  it('orders newest-first (ts DESC) and honors the limit', () => {
    insertInsightOn(db, payload({ headline: 'oldest' }), 1000)
    insertInsightOn(db, payload({ headline: 'newest' }), 3000)
    insertInsightOn(db, payload({ headline: 'middle' }), 2000)
    expect(recentInsightsOn(db, 100).map((r) => r.headline)).toEqual(['newest', 'middle', 'oldest'])
    expect(recentInsightsOn(db, 2).map((r) => r.headline)).toEqual(['newest', 'middle'])
  })

  it('caps history to the newest INSIGHT_HISTORY_CAP rows', () => {
    for (let i = 0; i < INSIGHT_HISTORY_CAP + 15; i++) {
      insertInsightOn(db, payload({ headline: `h${i}` }), 1000 + i)
    }
    const all = recentInsightsOn(db, 1000)
    expect(all).toHaveLength(INSIGHT_HISTORY_CAP)
    // The newest row survives; the very first (oldest) was pruned.
    expect(all[0].headline).toBe(`h${INSIGHT_HISTORY_CAP + 14}`)
    expect(all.some((r) => r.headline === 'h0')).toBe(false)
  })
})

describe('dismiss', () => {
  it('dismissInsight flags exactly one row and returns true; false when id is absent', () => {
    const keep = insertInsightOn(db, payload({ headline: 'keep' }), 1000)
    const target = insertInsightOn(db, payload({ headline: 'target' }), 2000)
    expect(dismissInsightOn(db, target)).toBe(true)
    expect(dismissInsightOn(db, 99999)).toBe(false)

    const byId = Object.fromEntries(recentInsightsOn(db, 100).map((r) => [r.id, r.dismissed]))
    expect(byId[target]).toBe(1)
    expect(byId[keep]).toBe(0)
  })

  it('dismissAll marks every unread row read and returns the count changed', () => {
    insertInsightOn(db, payload({ headline: 'a' }), 1000)
    insertInsightOn(db, payload({ headline: 'b' }), 2000)
    const first = dismissAllInsightsOn(db)
    expect(first).toBe(2)
    // Idempotent: a second call changes nothing (already all dismissed).
    expect(dismissAllInsightsOn(db)).toBe(0)
    expect(recentInsightsOn(db, 100).every((r) => r.dismissed === 1)).toBe(true)
  })
})

describe('clear', () => {
  it('clearInsights deletes all rows and returns the count', () => {
    insertInsightOn(db, payload({ headline: 'a' }), 1000)
    insertInsightOn(db, payload({ headline: 'b' }), 2000)
    expect(clearInsightsOn(db)).toBe(2)
    expect(recentInsightsOn(db, 100)).toEqual([])
    expect(clearInsightsOn(db)).toBe(0)
  })
})
