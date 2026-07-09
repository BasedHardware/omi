import { spawn } from 'child_process'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ClaudeCodeRuntimeAdapter } from './claudeCode'
import { createMockProcess } from './acp.testkit'

vi.mock('child_process', async () => {
  const actual = await vi.importActual<typeof import('child_process')>('child_process')
  return {
    ...actual,
    spawn: vi.fn(),
    execFile: vi.fn()
  }
})

describe('ClaudeCodeRuntimeAdapter spawn contract', () => {
  beforeEach(() => {
    vi.mocked(spawn).mockReset()
  })

  it('spawns the bundled ACP entry with the app binary running as Node, no shell', async () => {
    const proc = createMockProcess()
    vi.mocked(spawn).mockReturnValue(proc as never)

    const adapter = new ClaudeCodeRuntimeAdapter()
    await adapter.start()

    expect(spawn).toHaveBeenCalledTimes(1)
    const [bin, args, options] = vi.mocked(spawn).mock.calls[0] as unknown as [
      string,
      string[],
      Record<string, unknown>
    ]
    expect(bin).toBe(process.execPath)
    expect(args).toHaveLength(1)
    expect(args[0]).toContain('patched-acp-entry.mjs')
    expect(options).toMatchObject({ shell: false, stdio: ['pipe', 'pipe', 'pipe'] })
    const env = options.env as NodeJS.ProcessEnv
    // Electron's binary must run as plain Node for the entry script to execute.
    expect(env.ELECTRON_RUN_AS_NODE).toBe('1')
    // Auth is delegated to the Claude Agent SDK's own stored credentials —
    // stray env keys must not silently redirect it.
    expect(env.ANTHROPIC_API_KEY).toBeUndefined()
    expect(env.CLAUDECODE).toBeUndefined()

    await adapter.stop()
  })

  it('is always activated: constructing without options resolves a bundled entry path', () => {
    const adapter = new ClaudeCodeRuntimeAdapter()
    expect(adapter.adapterId).toBe('acp')
    expect(adapter.capabilities.supportsModelSwitching).toBe(true)
  })
})
