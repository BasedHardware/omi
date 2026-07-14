// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, act, cleanup } from '@testing-library/react'

// The real Canvas needs a GPU; stub the r3f surface so these tests exercise
// BrainGraph's own WebGL-availability branching, not three.js. Children are NOT
// rendered (the scene needs a live r3f context), which is all we need: the canvas
// stub's presence is the "we mounted WebGL" signal.
let canvasThrows = false
vi.mock('@react-three/fiber', () => ({
  Canvas: (): React.JSX.Element => {
    if (canvasThrows) throw new Error('Error creating WebGL context.')
    return <div data-testid="brain-graph-canvas" />
  },
  useFrame: () => {},
  useThree: () => undefined
}))

// Controllable WebGL probe.
let webglAvailable = true
vi.mock('../../lib/webglSupport', () => ({
  isWebglAvailable: (): boolean => webglAvailable
}))

const trackEvent = vi.fn()
vi.mock('../../lib/analytics', () => ({ trackEvent: (...a: unknown[]) => trackEvent(...a) }))

import { BrainGraph } from './BrainGraph'

const GRAPH = { nodes: [], edges: [] }

// Drive the main-process GPU_CONTEXT_LOST broadcast that useWebglRecovery listens
// for. Its remount is debounced (600ms), so tests advance timers past it.
let gpuListeners: Array<() => void> = []

describe('BrainGraph WebGL fallback', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    webglAvailable = true
    canvasThrows = false
    trackEvent.mockClear()
    gpuListeners = []
    ;(window as unknown as { omi: unknown }).omi = {
      onGpuContextLost: (cb: () => void) => {
        gpuListeners.push(cb)
        return () => {
          gpuListeners = gpuListeners.filter((l) => l !== cb)
        }
      }
    }
  })
  afterEach(() => {
    vi.useRealTimers()
    cleanup()
  })

  it('mounts the WebGL canvas when a context is available', () => {
    render(<BrainGraph graph={GRAPH} />)
    expect(screen.getByTestId('brain-graph-canvas')).toBeTruthy()
    expect(screen.queryByTestId('brain-graph-fallback')).toBeNull()
  })

  it('renders the static fallback (never an empty pane) when WebGL is unavailable', () => {
    webglAvailable = false
    render(<BrainGraph graph={GRAPH} />)
    expect(screen.getByTestId('brain-graph-fallback')).toBeTruthy()
    expect(screen.queryByTestId('brain-graph-canvas')).toBeNull()
    // A rendering-mode change must not be silent (AGENTS.md fallback telemetry).
    expect(trackEvent).toHaveBeenCalledWith('fallback_triggered', {
      component: 'brain_graph_render',
      from: 'webgl',
      to: 'static',
      reason: 'gpu_unavailable',
      outcome: 'degraded'
    })
  })

  it('reports readiness in fallback mode so a host loading placeholder clears', () => {
    webglAvailable = false
    const onReady = vi.fn()
    render(<BrainGraph graph={GRAPH} onReady={onReady} />)
    expect(onReady).toHaveBeenCalled()
  })

  it('re-probes on the GPU context-lost broadcast and heals once the GPU is back', () => {
    webglAvailable = false
    render(<BrainGraph graph={GRAPH} />)
    expect(screen.getByTestId('brain-graph-fallback')).toBeTruthy()

    // GPU process restarted; a context is obtainable again.
    webglAvailable = true
    act(() => {
      gpuListeners.forEach((l) => l())
      vi.advanceTimersByTime(1000) // past useWebglRecovery's 600ms debounce
    })

    expect(screen.getByTestId('brain-graph-canvas')).toBeTruthy()
    expect(screen.queryByTestId('brain-graph-fallback')).toBeNull()
    expect(trackEvent).toHaveBeenLastCalledWith('fallback_triggered', {
      component: 'brain_graph_render',
      from: 'static',
      to: 'webgl',
      reason: 'gpu_unavailable',
      outcome: 'recovered'
    })
  })

  it('stays on the fallback while the GPU is still down after a remount attempt', () => {
    webglAvailable = false
    render(<BrainGraph graph={GRAPH} />)
    act(() => {
      gpuListeners.forEach((l) => l())
      vi.advanceTimersByTime(1000)
    })
    expect(screen.getByTestId('brain-graph-fallback')).toBeTruthy()
    expect(screen.queryByTestId('brain-graph-canvas')).toBeNull()
  })

  it('contains a throwing three.js renderer instead of taking down the screen', () => {
    // The probe succeeds but the context dies before/while three builds its
    // renderer — WebGLRenderer throws. The boundary must catch it and degrade.
    canvasThrows = true
    const err = vi.spyOn(console, 'error').mockImplementation(() => {})
    render(
      <div data-testid="host">
        <BrainGraph graph={GRAPH} />
      </div>
    )
    expect(screen.getByTestId('host')).toBeTruthy() // the host survived the throw
    expect(screen.getByTestId('brain-graph-fallback')).toBeTruthy()
    expect(trackEvent).toHaveBeenCalledWith('fallback_triggered', {
      component: 'brain_graph_render',
      from: 'webgl',
      to: 'static',
      reason: 'renderer_init_failed',
      outcome: 'degraded'
    })
    err.mockRestore()
  })
})
