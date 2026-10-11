import { describe, expect, it } from 'vitest'
import {
  parseJitLedgerMirrorPage,
  parseJitRolloutDecision,
} from './jitAuthorityClient'

describe('Windows JIT authority wire parsing', () => {
  it('maps the authenticated snake_case rollout envelope', () => {
    expect(
      parseJitRolloutDecision({
        rollout: 'enabled',
        kill_switch: 'disabled',
        effective: 'enabled',
        reason: 'evaluated',
        error_class: 'none'
      })
    ).toEqual({
      rollout: 'enabled',
      killSwitch: 'disabled',
      effective: 'enabled',
      reason: 'evaluated',
      errorClass: 'none'
    })
  })

  it('maps the fenced ledger mirror page without accepting content-free malformed rows', () => {
    const parsed = parseJitLedgerMirrorPage({
      schema_version: 'knowledge_ledger_mirror.v1',
      owner_id: 'u',
      account_generation: 2,
      source_generation: 3,
      writer_epoch: 4,
      head_commit_id: 'h',
      commit_sequence: 5,
      epoch_id: 'epoch',
      page_revision: 'page',
      chain_revision: 'chain',
      scanned_count: 1,
      projected_count: 1,
      terminal_count: 0,
      rows: [
        {
          memory_id: 'fact-1',
          item_revision: 2,
          status: 'active',
          source_state: 'attested',
          canonical_memory_id: null,
          content_purged: false,
          memory: { kind: 'fact', content: 'redacted from test output' }
        }
      ],
      aliases: [],
      next_cursor: null,
      final_page: true,
      failure_reason: null
    })
    expect(parsed.rows[0].memoryId).toBe('fact-1')
    expect(parsed.finalPage).toBe(true)
    expect(() => parseJitLedgerMirrorPage({ ...parsed })).toThrow('malformed')
  })

  it('keeps compatibility with the current mirror envelope when terminal_count is absent', () => {
    const parsed = parseJitLedgerMirrorPage({
      schema_version: 'knowledge_ledger_mirror.v1',
      owner_id: 'u',
      account_generation: 2,
      source_generation: 3,
      writer_epoch: 4,
      head_commit_id: 'h',
      commit_sequence: 5,
      epoch_id: 'epoch',
      page_revision: 'page',
      chain_revision: 'chain',
      scanned_count: 2,
      projected_count: 2,
      rows: [
        {
          memory_id: 'old-1',
          item_revision: 2,
          status: 'superseded',
          source_state: 'active',
          canonical_memory_id: 'fact-1',
          content_purged: false,
          memory: { kind: 'fact' }
        },
        {
          memory_id: 'fact-1',
          item_revision: 3,
          status: 'active',
          source_state: 'active',
          canonical_memory_id: null,
          content_purged: false,
          memory: { kind: 'fact' }
        }
      ],
      aliases: [],
      next_cursor: null,
      final_page: true,
      failure_reason: null
    })
    expect(parsed.terminalCount).toBe(1)
    expect(parsed.terminalCountFromServer).toBe(false)
  })

})
