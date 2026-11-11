// Fresh-machine sign-in simulation against a REAL Node subprocess (no mocking of
// child_process). Points CLAUDE_CONFIG_DIR at an empty temp dir so the bundled
// bridge behavior is reproduced faithfully: the ACP handshake + session open
// succeed, but the first prompt fails with the canonical -32000 auth-required
// error — which the adapter must surface as an AcpError(-32000) the classifier
// recognizes, NOT swallow as a generic -32601. After we write a credentials
// file, a restart picks it up and the same prompt echoes normally.

import { join } from 'node:path'
import { mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { afterEach, describe, expect, it } from 'vitest'
import { ClaudeCodeRuntimeAdapter } from './claudeCode'
import { AcpError, isRecoverableAcpAuthError } from './acp'
import { writeClaudeCredentials, claudeAuthStatus } from './claudeOAuth'
import type { AdapterStreamEvent } from './interface'

const FIXTURE = join(__dirname, 'fixtures', 'fakeAcpAuthSubprocess.mjs')

describe('fresh-machine Claude sign-in against a real subprocess', () => {
  let priorConfigDir: string | undefined
  let tempDir: string | null = null

  afterEach(() => {
    if (priorConfigDir === undefined) delete process.env.CLAUDE_CONFIG_DIR
    else process.env.CLAUDE_CONFIG_DIR = priorConfigDir
    if (tempDir) rmSync(tempDir, { recursive: true, force: true })
    tempDir = null
  })

  it('surfaces -32000 when signed out, then works after credentials are written + restart', async () => {
    priorConfigDir = process.env.CLAUDE_CONFIG_DIR
    tempDir = mkdtempSync(join(tmpdir(), 'omi-freshauth-'))
    // Empty config dir — no .credentials.json. Must be set BEFORE the adapter
    // spawns (start() snapshots process.env).
    process.env.CLAUDE_CONFIG_DIR = tempDir
    const env = { CLAUDE_CONFIG_DIR: tempDir } as NodeJS.ProcessEnv

    expect(claudeAuthStatus(env).connected).toBe(false)

    const adapter = new ClaudeCodeRuntimeAdapter({ acpEntry: FIXTURE })
    try {
      // Handshake + session open succeed without credentials.
      const binding = await adapter.openBinding({ sessionId: 'omi-session', cwd: process.cwd() })
      expect(binding.adapterNativeSessionId).toBe('fake-native-session')

      // The prompt fails with the auth-required error.
      let caught: unknown
      try {
        await adapter.executeAttempt(
          {
            sessionId: 'omi-session',
            runId: 'run-1',
            attemptId: 'attempt-1',
            binding,
            prompt: [{ type: 'text', text: 'ping' }],
            mode: 'act'
          },
          () => {},
          new AbortController().signal
        )
        throw new Error('expected the signed-out prompt to reject')
      } catch (error) {
        caught = error
      }
      expect(caught).toBeInstanceOf(AcpError)
      expect((caught as AcpError).code).toBe(-32000)
      // The whole point: recognized as recoverable auth, not a terminal error.
      expect(isRecoverableAcpAuthError(caught)).toBe(true)

      // Sign in: write a credentials file to the same config dir.
      writeClaudeCredentials(
        { accessToken: 'AT', refreshToken: 'RT', expiresAt: Date.now() + 3_600_000, scopes: ['user:inference'] },
        env
      )
      expect(claudeAuthStatus(env).connected).toBe(true)

      // Restart the subprocess so it re-reads credentials, then the prompt works.
      await adapter.restart()
      const binding2 = await adapter.openBinding({ sessionId: 'omi-session-2', cwd: process.cwd() })
      const events: AdapterStreamEvent[] = []
      const result = await adapter.executeAttempt(
        {
          sessionId: 'omi-session-2',
          runId: 'run-2',
          attemptId: 'attempt-2',
          binding: binding2,
          prompt: [{ type: 'text', text: 'after signin' }],
          mode: 'act'
        },
        (e) => events.push(e),
        new AbortController().signal
      )
      expect(result.terminalStatus).toBe('succeeded')
      expect(result.text).toBe('echo: after signin')
      expect(events).toContainEqual({ type: 'text_delta', text: 'echo: after signin' })
    } finally {
      await adapter.stop()
    }
  }, 20_000)
})
