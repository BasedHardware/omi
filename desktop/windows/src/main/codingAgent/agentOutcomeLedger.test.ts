import { describe, it, expect, beforeEach, afterAll, vi } from 'vitest'
import { mkdtempSync, rmSync, writeFileSync } from 'fs'
import { tmpdir } from 'os'
import { join } from 'path'

// Same isolation approach as appSettings.test.ts: point the store at a
// throwaway userData dir so the round-trip touches a real file without
// hitting the developer's actual profile, or racing any other suite that
// also happens to import a userData-backed store.
const dir = mkdtempSync(join(tmpdir(), 'omi-agent-outcome-ledger-'))
vi.mock('electron', () => ({
  app: { getPath: (): string => dir }
}))

import { readOutcomeLedger, recordAgentOutcome, _resetForTests } from './agentOutcomeLedger'

afterAll(() => rmSync(dir, { recursive: true, force: true }))

describe('agentOutcomeLedger', () => {
  beforeEach(() => {
    _resetForTests()
    try {
      rmSync(join(dir, 'agent-outcome-ledger.json'), { force: true })
    } catch {
      /* ignore */
    }
  })

  it('starts empty when no file exists yet', () => {
    expect(readOutcomeLedger()).toEqual([])
  })

  it('records an outcome and stamps it with the current time', () => {
    const before = Date.now()
    recordAgentOutcome({ adapterId: 'codex', tag: 'general', outcome: 'success' })
    const [entry] = readOutcomeLedger()
    expect(entry).toMatchObject({ adapterId: 'codex', tag: 'general', outcome: 'success' })
    expect(entry.ts).toBeGreaterThanOrEqual(before)
  })

  it('persists across a dropped cache (proves it actually hit disk)', () => {
    recordAgentOutcome({ adapterId: 'hermes', tag: 'bulk_refactor', outcome: 'failure' })
    _resetForTests()
    expect(readOutcomeLedger()).toHaveLength(1)
    expect(readOutcomeLedger()[0]).toMatchObject({ adapterId: 'hermes', outcome: 'failure' })
  })

  it('keeps entries in append order', () => {
    recordAgentOutcome({ adapterId: 'acp', tag: 'general', outcome: 'success' })
    recordAgentOutcome({ adapterId: 'acp', tag: 'general', outcome: 'failure' })
    recordAgentOutcome({ adapterId: 'acp', tag: 'general', outcome: 'success' })
    expect(readOutcomeLedger().map((e) => e.outcome)).toEqual(['success', 'failure', 'success'])
  })

  it('caps the file so unbounded use cannot grow it forever', () => {
    for (let i = 0; i < 520; i++) {
      recordAgentOutcome({ adapterId: 'codex', tag: 'general', outcome: 'success' })
    }
    expect(readOutcomeLedger().length).toBeLessThanOrEqual(500)
  })

  it('degrades to empty instead of throwing on a corrupt file', () => {
    recordAgentOutcome({ adapterId: 'codex', tag: 'general', outcome: 'success' })
    _resetForTests()
    // Overwrite with garbage the same way a half-written disk flush might.
    writeFileSync(join(dir, 'agent-outcome-ledger.json'), '{not json', 'utf-8')
    _resetForTests()
    expect(readOutcomeLedger()).toEqual([])
  })

  it('drops a malformed entry instead of the whole file', () => {
    writeFileSync(
      join(dir, 'agent-outcome-ledger.json'),
      JSON.stringify({
        entries: [
          { adapterId: 'codex', tag: 'general', outcome: 'success', ts: 1 },
          { adapterId: 'not-a-real-agent', tag: 'general', outcome: 'success', ts: 2 },
          { adapterId: 'hermes', tag: 'not-a-real-tag', outcome: 'success', ts: 3 },
          { adapterId: 'hermes', tag: 'general', outcome: 'sideways', ts: 4 },
          { adapterId: 'hermes', tag: 'general', outcome: 'success', ts: 'not-a-number' }
        ]
      }),
      'utf-8'
    )
    _resetForTests()
    expect(readOutcomeLedger()).toEqual([
      { adapterId: 'codex', tag: 'general', outcome: 'success', ts: 1 }
    ])
  })
})
