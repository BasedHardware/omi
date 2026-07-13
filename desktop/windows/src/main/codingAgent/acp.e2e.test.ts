/**
 * Live end-to-end harness for the coding-agent (ACP) system — the real Claude
 * Code subprocess path production code takes. Constructs `AcpRuntimeAdapter`
 * (./acp.ts) DIRECTLY rather than `ClaudeCodeRuntimeAdapter` (./claudeCode.ts):
 * the latter's `?asset` import needs electron-vite's build step or vitest's
 * asset-suffix plugin to resolve, and this harness deliberately doesn't lean
 * on either — it points `acpEntry` straight at the on-disk
 * claude-acp-entry.mjs and exercises the exact same runtime code
 * (ClaudeCodeRuntimeAdapter is a thin subclass that only supplies that path).
 *
 * Flow exercised end to end: process spawn (node running claude-acp-entry.mjs,
 * which dynamically imports @agentclientprotocol/claude-agent-acp) ->
 * session/new -> session/set_mode (permission pinning) -> session/prompt ->
 * a real Write tool call -> permission auto-approve (resolveAcpPermission) ->
 * agent_message_chunk streaming -> terminal result -> stop() / process exit.
 * The task is the simplest thing that proves all of that: create a file with
 * known content in a scratch temp directory.
 *
 * COSTS REAL MONEY (~$0.50/run) and takes roughly 20-60s. Requires the machine
 * running this to already be signed in to Claude Code — the adapter strips
 * ANTHROPIC_API_KEY and rides the ~/.claude session, same as production; there
 * is no API-key env var this test can substitute.
 *
 * GATED on OMI_E2E=1 (process env only — never .env), so it can never run as
 * part of `pnpm test` / CI. Only the explicit script sets that flag:
 *
 *   pnpm test:e2e:agent
 */
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import type { ChildProcess } from 'node:child_process'
import { describe, it, expect } from 'vitest'
import { AcpRuntimeAdapter } from './acp'
import { assertAdapterBindingContract, type AdapterStreamEvent } from './interface'

const HERE = path.dirname(fileURLToPath(import.meta.url))
const ACP_ENTRY = path.resolve(HERE, 'claude-acp-entry.mjs')

const OPTED_IN = process.env.OMI_E2E === '1'

describe.skipIf(!OPTED_IN)('coding agent (ACP / Claude Code) e2e — live subprocess', () => {
  it('opens a session, creates a file via the real Claude Code bridge, and tears down cleanly', async () => {
    const scratchDir = fs.mkdtempSync(path.join(os.tmpdir(), 'omi-agent-e2e-'))
    const MARKER_FILE = 'e2e-marker.txt'
    const MARKER_CONTENT = 'OMI_AGENT_E2E_OK'

    const logs: string[] = []
    const adapter = new AcpRuntimeAdapter({
      adapterId: 'acp',
      acpEntry: ACP_ENTRY,
      log: (message) => logs.push(message)
    })

    const t0 = Date.now()
    try {
      const binding = await adapter.openBinding({
        sessionId: 'omi-agent-e2e-session',
        cwd: scratchDir
      })
      assertAdapterBindingContract(binding, 'openBinding')

      // Grab the pid now — the process is spawned during openBinding() (via
      // start()) and this class exposes it only as a TS-private field.
      const pid = (adapter as unknown as { process: ChildProcess | null }).process?.pid

      const events: AdapterStreamEvent[] = []
      const result = await adapter.executeAttempt(
        {
          sessionId: 'omi-agent-e2e-session',
          runId: 'e2e-run-1',
          attemptId: 'e2e-attempt-1',
          binding,
          prompt: [
            {
              type: 'text',
              text:
                `Create a file named "${MARKER_FILE}" in the current directory. ` +
                `Its ENTIRE contents must be exactly this one line, with no other ` +
                `text, no quotes, and no markdown formatting: ${MARKER_CONTENT}`
            }
          ],
          mode: 'act'
        },
        (event) => events.push(event),
        new AbortController().signal
      )
      const elapsedMs = Date.now() - t0

      expect(result.terminalStatus).toBe('succeeded')
      expect(result.adapterSessionId).toBe(binding.adapterNativeSessionId)

      const filePath = path.join(scratchDir, MARKER_FILE)
      expect(
        fs.existsSync(filePath),
        `expected ${filePath} to exist; agent text: ${JSON.stringify(result.text)}; logs: ${logs.join(' | ')}`
      ).toBe(true)
      // Tolerate a single trailing newline — a normal artifact of how file-write
      // tools terminate text files; the content itself must match exactly.
      const content = fs.readFileSync(filePath, 'utf8').replace(/\n$/, '')
      expect(content).toBe(MARKER_CONTENT)

      const toolActivity = events.filter((event) => event.type === 'tool_activity')
      console.log(
        `[agent-e2e] terminalStatus=${result.terminalStatus} elapsedMs=${elapsedMs} ` +
          `costUsd=${result.costUsd} tokens(in=${result.inputTokens},out=${result.outputTokens}) ` +
          `toolCalls=${toolActivity.length}`
      )

      await adapter.stop()

      // No orphaned child process: stop() awaits the subprocess's 'exit' event,
      // so once it resolves the pid must no longer be alive. On Windows,
      // process.kill(pid, 0) is a liveness probe (throws if the pid is gone).
      if (pid) {
        let stillAlive = true
        try {
          process.kill(pid, 0)
        } catch {
          stillAlive = false
        }
        expect(stillAlive, `pid ${pid} still alive after adapter.stop()`).toBe(false)
      }
    } finally {
      await adapter.stop().catch(() => {})
      // Best-effort: Windows can hold a lock on the scratch dir for several
      // seconds after the process exits (observed: Defender/indexer scanning
      // the file the agent just wrote — verified via Get-CimInstance
      // Win32_Process that no child of this run survives stop(), and that a
      // plain delayed delete outside the test succeeds). This is OS-level temp
      // dir GC flakiness, not something the test is verifying — don't fail an
      // otherwise-passing live-agent run over it.
      try {
        fs.rmSync(scratchDir, { recursive: true, force: true, maxRetries: 15, retryDelay: 500 })
      } catch (err) {
        console.warn(`[agent-e2e] could not remove scratch dir ${scratchDir}: ${String(err)}`)
      }
    }
  }, 120_000)
})
