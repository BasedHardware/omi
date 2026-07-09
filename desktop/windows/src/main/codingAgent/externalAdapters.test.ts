import { spawn, execFile } from 'child_process'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { OpenClawRuntimeAdapter } from './openclaw'
import { HermesRuntimeAdapter } from './hermes'
import { CodexRuntimeAdapter } from './codex'
import { createMockProcess, stubPlatform } from './acp.testkit'

vi.mock('child_process', async () => {
  const actual = await vi.importActual<typeof import('child_process')>('child_process')
  return {
    ...actual,
    spawn: vi.fn(),
    execFile: vi.fn()
  }
})

const ADAPTER_ENV_VARS = [
  'OMI_OPENCLAW_ADAPTER_COMMAND',
  'OMI_HERMES_ADAPTER_COMMAND',
  'OMI_CODEX_ADAPTER_COMMAND'
] as const

describe('external adapter subprocesses (OpenClaw / Hermes / Codex)', () => {
  beforeEach(() => {
    vi.mocked(spawn).mockReset()
    vi.mocked(execFile).mockReset()
    // stop() must terminate on whichever platform the suite runs on:
    //  - win32 path calls execFile('taskkill', …, cb) — fail the callback so the
    //    proc.kill() fallback (which emits 'exit' on the mock) runs;
    //  - POSIX path calls process.kill(-pid) — throw so the same fallback runs
    //    (and so the test can never signal a REAL process group by accident).
    vi.mocked(execFile).mockImplementation(((...args: unknown[]) => {
      const callback = args.find((arg) => typeof arg === 'function') as
        | ((error: Error | null) => void)
        | undefined
      callback?.(new Error('taskkill unavailable in tests'))
      return undefined as never
    }) as never)
    vi.spyOn(process, 'kill').mockImplementation(() => {
      throw new Error('ESRCH')
    })
    for (const key of ADAPTER_ENV_VARS) delete process.env[key]
  })

  afterEach(() => {
    vi.restoreAllMocks()
    for (const key of ADAPTER_ENV_VARS) delete process.env[key]
    delete process.env.FAKE_SECRET_TOKEN
    delete process.env.OMI_AUTH_TOKEN
    delete process.env.HERMES_HOME
    delete process.env.OPENAI_API_KEY
    delete process.env.HTTPS_PROXY
  })

  it('refuses to start without a configured command, activates from the env var', async () => {
    const adapter = new OpenClawRuntimeAdapter()
    await expect(adapter.start()).rejects.toThrow(
      'openclaw adapter requires OMI_OPENCLAW_ADAPTER_COMMAND'
    )

    const proc = createMockProcess()
    vi.mocked(spawn).mockReturnValue(proc as never)
    process.env.OMI_OPENCLAW_ADAPTER_COMMAND = 'openclaw acp'

    await adapter.start()
    expect(spawn).toHaveBeenCalledWith(
      'openclaw acp',
      expect.objectContaining({
        shell: true,
        stdio: ['pipe', 'pipe', 'pipe'],
        windowsHide: true,
        env: expect.objectContaining({ OMI_ADAPTER_ID: 'openclaw' })
      })
    )
    await adapter.stop()
  })

  it('never leaks host secrets into the external env, but forwards adapter-specific vars', async () => {
    process.env.FAKE_SECRET_TOKEN = 'super-secret'
    process.env.OMI_AUTH_TOKEN = 'firebase-token'
    process.env.HERMES_HOME = 'C:/hermes-home'
    process.env.OPENAI_API_KEY = 'sk-test-openai-key-123456'
    process.env.HTTPS_PROXY = 'http://alice:s3cr3t@proxy:3128'

    const hermesProc = createMockProcess()
    vi.mocked(spawn).mockReturnValue(hermesProc as never)
    const hermes = new HermesRuntimeAdapter({ command: 'hermes acp' })
    await hermes.start()
    const hermesEnv = (vi.mocked(spawn).mock.calls[0][1] as unknown as { env: NodeJS.ProcessEnv })
      .env
    expect(hermesEnv.FAKE_SECRET_TOKEN).toBeUndefined()
    expect(hermesEnv.OMI_AUTH_TOKEN).toBeUndefined()
    // Hermes-specific passthrough
    expect(hermesEnv.HERMES_HOME).toBe('C:/hermes-home')
    // Not Hermes's to receive
    expect(hermesEnv.OPENAI_API_KEY).toBeUndefined()
    // Proxy credentials are stripped before forwarding
    expect(hermesEnv.HTTPS_PROXY).toBe('http://proxy:3128/')
    await hermes.stop()

    vi.mocked(spawn).mockReset()
    const codexProc = createMockProcess()
    vi.mocked(spawn).mockReturnValue(codexProc as never)
    const codex = new CodexRuntimeAdapter({ command: 'npx @agentclientprotocol/codex-acp' })
    await codex.start()
    const codexEnv = (vi.mocked(spawn).mock.calls[0][1] as unknown as { env: NodeJS.ProcessEnv })
      .env
    // Codex-specific passthrough: the bridge needs the OpenAI/Codex key to auth.
    expect(codexEnv.OPENAI_API_KEY).toBe('sk-test-openai-key-123456')
    expect(codexEnv.HERMES_HOME).toBeUndefined()
    expect(codexEnv.FAKE_SECRET_TOKEN).toBeUndefined()
    await codex.stop()
  })

  it('kills the whole process tree with taskkill on Windows', async () => {
    const restorePlatform = stubPlatform('win32')
    try {
      const proc = createMockProcess()
      vi.mocked(spawn).mockReturnValue(proc as never)
      vi.mocked(execFile).mockImplementation(((
        _cmd: string,
        _args: string[],
        callback?: (error: Error | null) => void
      ) => {
        // taskkill terminates the tree → the child exits.
        proc.emit('exit', 0)
        callback?.(null)
        return proc as never
      }) as never)

      const adapter = new OpenClawRuntimeAdapter({ command: 'openclaw acp' })
      await adapter.start()
      await adapter.stop()

      expect(execFile).toHaveBeenCalledWith(
        'taskkill',
        ['/pid', String(proc.pid), '/t', '/f'],
        expect.any(Function)
      )
    } finally {
      restorePlatform()
    }
  })

  it('kills the detached process group on POSIX platforms', async () => {
    const restorePlatform = stubPlatform('linux')
    const killSpy = vi.spyOn(process, 'kill').mockImplementation(() => true)
    try {
      const proc = createMockProcess()
      vi.mocked(spawn).mockReturnValue(proc as never)

      const adapter = new HermesRuntimeAdapter({ command: 'hermes acp' })
      await adapter.start()
      // Group kill signal delivery is external to the mock — emit exit manually.
      setImmediate(() => proc.emit('exit', 0))
      await adapter.stop()

      expect(killSpy).toHaveBeenCalledWith(-proc.pid, 'SIGTERM')
      expect(vi.mocked(spawn).mock.calls[0][1]).toMatchObject({ detached: true })
    } finally {
      restorePlatform()
    }
  })

  it('applies OpenClaw session semantics: empty MCP servers and no set_model', () => {
    const adapter = new OpenClawRuntimeAdapter({ command: 'openclaw acp' })
    expect(adapter.adapterId).toBe('openclaw')
    expect(adapter.capabilities.supportsModelSwitching).toBe(false)
    expect(adapter.capabilities.supportsNativeResume).toBe(true)
  })

  it('treats Codex sessions as process-local until verified', () => {
    const adapter = new CodexRuntimeAdapter({ command: 'codex-acp' })
    expect(adapter.adapterId).toBe('codex')
    expect(adapter.capabilities.supportsNativeResume).toBe(false)
    expect(adapter.capabilities.requiresPinnedWorker).toBe(true)
  })
})
