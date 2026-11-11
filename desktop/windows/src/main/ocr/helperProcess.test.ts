// Regression for C7: the OCR/window-info helper subprocess must be killable so
// the will-quit handler can dispose it (without a dispose() call site it orphaned
// omi-*-ocr-helper.exe on every quit). We mock child_process.spawn so no real
// helper binary is needed, and assert dispose() kills the live child and that a
// later request does NOT re-spawn a new one — a post-dispose respawn (e.g. from
// ocrService's backfill timer firing after will-quit already ran) is exactly
// what orphaned a helper past app exit even with dispose() wired up.
import { EventEmitter } from 'node:events'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const spawnMock = vi.fn()

vi.mock('child_process', () => ({ spawn: (...args: unknown[]) => spawnMock(...args) }))
vi.mock('./resolveHelperPath', () => ({ resolveHelperPath: () => 'C:\\fake\\win-ocr-helper.exe' }))

type FakeChild = EventEmitter & {
  pid: number
  stdout: EventEmitter
  stderr: EventEmitter
  stdin: { write: ReturnType<typeof vi.fn> }
  kill: ReturnType<typeof vi.fn>
}

let nextFakePid = 1000
function makeFakeChild(): FakeChild {
  const child = new EventEmitter() as FakeChild
  child.pid = nextFakePid++
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
    // Every test in this suite exercises dispose()/recycle(), which on Linux
    // now calls the REAL process.kill(-pid, ...) unless mocked — with fake
    // pids that could collide with an unrelated real process group on the
    // test machine. Stub it everywhere, not just in the test that asserts on it.
    vi.spyOn(process, 'kill').mockImplementation(() => true)
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
      // detached so the helper leads its OWN process group (see recycle()'s
      // group-kill test below for why this matters).
      expect(spawnOpts).toMatchObject({ detached: true })
    } else {
      // The Windows helper is a console-subsystem exe; it must be spawned with
      // windowsHide so it never flashes a stray console window in the taskbar.
      expect(spawnOpts).toMatchObject({ windowsHide: true })
    }

    helperProcess.dispose()
    if (process.platform === 'linux') {
      // Linux kills the whole process group, not just the child PID — see the
      // dedicated group-kill test below.
      expect(vi.mocked(process.kill)).toHaveBeenCalledWith(-child.pid, 'SIGTERM')
      expect(child.kill).not.toHaveBeenCalled()
    } else {
      expect(child.kill).toHaveBeenCalledTimes(1)
    }
  })

  it('rejects the in-flight request when disposed mid-flight', async () => {
    const child = makeFakeChild()
    spawnMock.mockReturnValue(child)
    const { helperProcess } = await import('./helperProcess')

    const pending = helperProcess.windowInfo()
    helperProcess.dispose()
    await expect(pending).rejects.toThrow(/helper exited/)
  })

  it('does not re-spawn on a request after dispose() — a post-quit tick must not orphan a new helper', async () => {
    spawnMock.mockImplementation(() => makeFakeChild())
    const { helperProcess } = await import('./helperProcess')

    void helperProcess.windowInfo().catch(() => {})
    helperProcess.dispose()
    const late = helperProcess.windowInfo()

    expect(spawnMock).toHaveBeenCalledTimes(1)
    await expect(late).rejects.toThrow(/disposed/)
  })

  // Regression: the Linux helper (resources/linux-ocr-helper/omi-ocr-helper)
  // shells out to `tesseract` synchronously per OCR call. Killing only the
  // helper's own PID left that grandchild running — its own execFileSync
  // timeout can't fire once the process enforcing it is gone — orphaning one
  // more `tesseract` process every time a recycle/dispose raced an in-flight
  // request. Confirmed live: 10 accumulated `tesseract` processes and a
  // system slowdown after enough request-timeout/dispose cycles.
  it('kills the whole process group on recycle(), not just the helper PID — an orphaned tesseract grandchild must die too', async () => {
    if (process.platform !== 'linux') return // group-kill is Linux-only; see helperProcess.ts
    const child = makeFakeChild()
    spawnMock.mockReturnValue(child)
    const { helperProcess } = await import('./helperProcess')

    void helperProcess.windowInfo().catch(() => {})
    // dispose() and a request-timeout both funnel through the same private
    // recycle() — exercising it via the public dispose() entry point here.
    helperProcess.dispose()

    expect(vi.mocked(process.kill)).toHaveBeenCalledWith(-child.pid, 'SIGTERM')
    expect(child.kill).not.toHaveBeenCalled()
  })
})
