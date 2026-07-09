// Real-subprocess integration test: no child_process mocking. Spawns the
// fixture fake-ACP peer as an actual Node child process, exercising the
// adapter's real spawn / readline framing / kill machinery — the parts the
// mocked suites structurally cannot cover. Requires no coding-agent install.

import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import { ClaudeCodeRuntimeAdapter } from './claudeCode'
import { assertAdapterBindingContract, type AdapterStreamEvent } from './interface'

const FIXTURE = join(__dirname, 'fixtures', 'fakeAcpSubprocess.mjs')

describe('AcpRuntimeAdapter against a real subprocess', () => {
  it('runs the full open → prompt → stream → result → stop lifecycle', async () => {
    const adapter = new ClaudeCodeRuntimeAdapter({ acpEntry: FIXTURE })
    try {
      const binding = await adapter.openBinding({
        sessionId: 'omi-session',
        cwd: process.cwd()
      })
      assertAdapterBindingContract(binding, 'openBinding')
      expect(binding.adapterNativeSessionId).toBe('fake-native-session')

      const events: AdapterStreamEvent[] = []
      const result = await adapter.executeAttempt(
        {
          sessionId: 'omi-session',
          runId: 'run-1',
          attemptId: 'attempt-1',
          binding,
          prompt: [{ type: 'text', text: 'integration ping' }],
          mode: 'act'
        },
        (event) => events.push(event),
        new AbortController().signal
      )

      expect(events).toContainEqual({ type: 'text_delta', text: 'echo: integration ping' })
      expect(result.text).toBe('echo: integration ping')
      expect(result.terminalStatus).toBe('succeeded')
      expect(result.inputTokens).toBe(3)
      expect(result.costUsd).toBeCloseTo(0.001)
    } finally {
      await adapter.stop()
    }
  }, 15_000)
})
