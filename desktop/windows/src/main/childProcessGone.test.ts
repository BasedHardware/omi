import { describe, it, expect } from 'vitest'
import { classifyChildProcessGone } from './childProcessGone'

describe('classifyChildProcessGone', () => {
  // THE regression. On Windows a clean quit terminates the GPU process with
  // TerminateProcess, which Chromium reports as reason=killed exitCode=1 — field
  // for field identical to a real GPU kill. Before this filter, every quit wrote a
  // fatal "GPU crash" line to crash.log; five quits read as a GPU crash LOOP and
  // sent a human chasing a phantom. Any telemetry keyed off this handler would have
  // reported a GPU crash for every clean quit in the fleet.
  it('does NOT report a GPU crash when the app is quitting (Windows TerminateProcess)', () => {
    expect(classifyChildProcessGone({ type: 'GPU', reason: 'killed' }, true)).toEqual({
      fatal: false,
      broadcastGpuLoss: false
    })
  })

  it('reports a REAL GPU crash while the app is running, and broadcasts context loss', () => {
    expect(classifyChildProcessGone({ type: 'GPU', reason: 'crashed' }, false)).toEqual({
      fatal: true,
      broadcastGpuLoss: true
    })
    // `killed` while NOT quitting is the field failure from crash.log — still real.
    expect(classifyChildProcessGone({ type: 'GPU', reason: 'killed' }, false)).toEqual({
      fatal: true,
      broadcastGpuLoss: true
    })
  })

  it('never treats a clean exit as a crash', () => {
    expect(classifyChildProcessGone({ type: 'GPU', reason: 'clean-exit' }, false)).toEqual({
      fatal: false,
      broadcastGpuLoss: false
    })
  })

  it('reports a non-GPU child crash but does not broadcast WebGL context loss', () => {
    expect(classifyChildProcessGone({ type: 'Utility', reason: 'crashed' }, false)).toEqual({
      fatal: true,
      broadcastGpuLoss: false
    })
  })
})
