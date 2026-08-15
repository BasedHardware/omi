// Windows conformance suite for the shared action-item wire-decode contract
// (contracts/parity/wire_action_item.json): the sync engine's backend-item
// mapper must recover the same instant from every sanctioned due_at form and
// treat null / missing / empty / unparseable ones as no-due-date. The engine
// module needs the same import-time mocks as taskSyncEngine.test.ts (electron
// and the native-sqlite storage wrappers cannot load under plain-node vitest);
// the mapper itself is pure.
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { describe, expect, it, vi } from 'vitest'

vi.mock('electron', () => ({
  net: { fetch: vi.fn() },
  BrowserWindow: {
    getAllWindows: () => []
  }
}))

vi.mock('../ipc/db', () => ({
  getLocalActionItems: vi.fn(() => []),
  getFilteredActionItems: vi.fn(() => []),
  getUnsyncedActionItems: vi.fn(() => []),
  insertLocalActionItem: vi.fn(),
  updateCompletionStatus: vi.fn(),
  updateActionItemFields: vi.fn(),
  deleteActionItemByBackendId: vi.fn(() => []),
  markSyncedActionItem: vi.fn(() => ({ merged: false, keptId: 0 })),
  syncTaskActionItems: vi.fn(() => ({ skipped: 0, adopted: 0, inserted: 0, updated: 0 })),
  hardDeleteAbsentTasks: vi.fn(() => []),
  hardDeleteAbsentCompletedTasks: vi.fn(() => []),
  getAppMeta: vi.fn(() => '1'),
  setAppMeta: vi.fn()
}))

vi.mock('../assistants/tasks/create', () => ({ promoteIfNeeded: vi.fn(async () => {}) }))

vi.mock('../observability/backendDegraded', () => ({
  isBackendDegraded: vi.fn(() => false),
  noteBackendStatus: vi.fn()
}))

import { mapBackendItem } from './taskSyncEngine'

type WireCase = {
  name: string
  payload: Record<string, unknown>
  expected: { parses: boolean; description: string; completed: boolean; due_utc: string | null }
}

// Fixed sync timestamp: the mapper fills a missing created_at with sync time
// (a documented Windows-only divergence, see contracts/parity/README.md), so the
// wire expectations only pin description / completed / due instant.
const SYNC_NOW = Date.parse('2026-08-15T00:00:00Z')

describe('action item wire decode (parity contract)', () => {
  const path = fileURLToPath(new URL('../../../../../contracts/parity/wire_action_item.json', import.meta.url))
  const { cases } = JSON.parse(readFileSync(path, 'utf8')) as { cases: WireCase[] }
  it.each(cases)('$name', (c) => {
    const mapped = mapBackendItem(c.payload as never, SYNC_NOW)
    expect(c.expected.parses).toBe(true)
    expect(mapped.description).toBe(c.expected.description)
    expect(mapped.completed).toBe(c.expected.completed)
    expect(mapped.dueAt).toBe(c.expected.due_utc === null ? null : Date.parse(c.expected.due_utc))
  })
})
