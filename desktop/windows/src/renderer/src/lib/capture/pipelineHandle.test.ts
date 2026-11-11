import { describe, it, expect, vi } from 'vitest'
import { makePipelineHandle, type TrackedStream } from './pipelineHandle'

/** A stream with two distinct tracks whose stop() calls are individually spied. */
function fakeStream(): { stream: TrackedStream; stops: ReturnType<typeof vi.fn>[] } {
  const stops = [vi.fn(), vi.fn()]
  const tracks = stops.map((stop) => ({ stop }))
  return { stream: { getTracks: () => tracks }, stops }
}

describe('makePipelineHandle', () => {
  it('tears down the pipeline and stops the mic tracks after setup resolves', async () => {
    const pipeStop = vi.fn()
    const { stream, stops } = fakeStream()
    const handle = makePipelineHandle(stream, Promise.resolve({ stop: pipeStop }))
    await expect(handle.ready).resolves.toEqual({ ok: true })
    handle.stop()
    expect(pipeStop).toHaveBeenCalledOnce()
    for (const s of stops) expect(s).toHaveBeenCalledOnce()
  })

  it('stops mic tracks AND tears down the late pipeline when stop races ahead of setup', async () => {
    const pipeStop = vi.fn()
    let resolveSetup!: (p: { stop: () => void }) => void
    const setup = new Promise<{ stop: () => void }>((r) => (resolveSetup = r))
    const { stream, stops } = fakeStream()

    const handle = makePipelineHandle(stream, setup)
    handle.stop() // BEFORE setup resolves
    expect(stops[0]).toHaveBeenCalledOnce() // mic released immediately
    expect(pipeStop).not.toHaveBeenCalled() // nothing to tear down yet

    resolveSetup({ stop: pipeStop })
    await expect(handle.ready).resolves.toEqual({ ok: true })
    expect(pipeStop).toHaveBeenCalledOnce() // late pipeline torn down on arrival
  })

  it('reports setup failure and still releases the mic when stopped', async () => {
    const { stream, stops } = fakeStream()
    const handle = makePipelineHandle(stream, Promise.reject(new Error('addModule failed')))
    const result = await handle.ready
    expect(result.ok).toBe(false)
    if (!result.ok) expect(result.error.message).toBe('addModule failed')
    handle.stop()
    expect(stops[0]).toHaveBeenCalledOnce()
  })

  it('is idempotent — a second stop() does nothing', async () => {
    const pipeStop = vi.fn()
    const { stream, stops } = fakeStream()
    const handle = makePipelineHandle(stream, Promise.resolve({ stop: pipeStop }))
    await handle.ready
    handle.stop()
    handle.stop()
    expect(pipeStop).toHaveBeenCalledOnce()
    expect(stops[0]).toHaveBeenCalledOnce()
  })
})
