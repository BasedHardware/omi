// Regression for C7: the OCR/window-info helper subprocess must be killable so
// the will-quit handler can dispose it (without a dispose() call site it orphaned
// omi-*-ocr-helper.exe on every quit). We mock child_process.spawn so no real
// helper binary is needed, and assert dispose() kills the live child and that a
// later request re-spawns a fresh one.
import { EventEmitter } from 'node:events'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const spawnMock = vi.fn()

vi.mock('child_process', () => ({ spawn: (...args: unknown[]) => spawnMock(...args) }))
vi.mock('./resolveHelperPath', () => ({ resolveHelperPath: () => 'C:\\fake\\win-ocr-helper.exe' }))

type FakeChild = EventEmitter & {
  stdout: EventEmitter
  stderr: EventEmitter
  stdin: { write: ReturnType<typeof vi.fn> }
  kill: ReturnType<typeof vi.fn>
}

function makeFakeChild(): FakeChild {
  const child = new EventEmitter() as FakeChild
  child.stdout = new EventEmitter()
  child.stderr = new EventEmitter()
  child.stdin = { write: vi.fn() }
  child.kill = vi.fn()
  return child
}

describe('helperProcess.dispose (C7 — no orphaned OCR helper on quit)', () => {
  beforeEach(() => {
    spawnMock.mockReset()
    vi.resetModules()
  })
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('kills the live child on dispose()', async () => {
    const child = makeFakeChild()
    spawnMock.mockReturnValue(child)
    const { helperProcess } = await import('./helperProcess')

    // Fire a request to lazily spawn the child (we never resolve it — dispose
    // rejects it below).
    void helperProcess.windowInfo().catch(() => {})
    expect(spawnMock).toHaveBeenCalledTimes(1)
    const spawnOpts = spawnMock.mock.calls[0][2] as Record<string, unknown>
    if (process.platform === 'linux') {
      // Linux helper is a Node script run via Electron's bundled Node.
      expect(spawnOpts.env).toMatchObject({ ELECTRON_RUN_AS_NODE: '1' })
    } else {
      // The Windows helper is a console-subsystem exe; it must be spawned with
      // windowsHide so it never flashes a stray console window in the taskbar.
      expect(spawnOpts).toMatchObject({ windowsHide: true })
    }

    helperProcess.dispose()
    expect(child.kill).toHaveBeenCalledTimes(1)
  })

  it('rejects the in-flight request when disposed mid-flight', async () => {
    const child = makeFakeChild()
    spawnMock.mockReturnValue(child)
    const { helperProcess } = await import('./helperProcess')

    const pending = helperProcess.windowInfo()
    helperProcess.dispose()
    await expect(pending).rejects.toThrow(/helper exited/)
  })

  it('re-spawns a fresh child on the next request after dispose()', async () => {
    spawnMock.mockImplementation(() => makeFakeChild())
    const { helperProcess } = await import('./helperProcess')

    void helperProcess.windowInfo().catch(() => {})
    helperProcess.dispose()
    void helperProcess.windowInfo().catch(() => {})

    expect(spawnMock).toHaveBeenCalledTimes(2)
  })
})
