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
    await Promise.resolve() // let the setup .then run
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
    await Promise.resolve()
    expect(pipeStop).toHaveBeenCalledOnce() // late pipeline torn down on arrival
  })

  it('still releases the mic when setup rejects (pipeline failed to start)', async () => {
    const { stream, stops } = fakeStream()
    const handle = makePipelineHandle(stream, Promise.reject(new Error('addModule failed')))
    await Promise.resolve()
    await Promise.resolve()
    handle.stop()
    expect(stops[0]).toHaveBeenCalledOnce()
  })

  it('is idempotent — a second stop() does nothing', async () => {
    const pipeStop = vi.fn()
    const { stream, stops } = fakeStream()
    const handle = makePipelineHandle(stream, Promise.resolve({ stop: pipeStop }))
    await Promise.resolve()
    handle.stop()
    handle.stop()
    expect(pipeStop).toHaveBeenCalledOnce()
    expect(stops[0]).toHaveBeenCalledOnce()
  })
})
