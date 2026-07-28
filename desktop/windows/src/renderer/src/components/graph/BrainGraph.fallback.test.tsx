// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, act, cleanup } from '@testing-library/react'

// The real Canvas needs a GPU; stub the r3f surface so these tests exercise
// BrainGraph's own degradation logic, not three.js. Children are NOT rendered (the
// scene needs a live r3f context) — the canvas stub's presence is the "the REAL
// graph mounted" signal, which is the thing that must not regress.
let canvasThrows = false
vi.mock('@react-three/fiber', () => ({
  Canvas: ({ onCreated }: { onCreated?: () => void }): React.JSX.Element => {
    // Mirrors three: a context that cannot be had THROWS during construction.
    if (canvasThrows) throw new Error('Error creating WebGL context.')
    onCreated?.()
    return <div data-testid="brain-graph-canvas" />
  },
  useFrame: () => {},
  useThree: () => undefined
}))

const trackEvent = vi.fn()
vi.mock('../../lib/analytics', () => ({ trackEvent: (...a: unknown[]) => trackEvent(...a) }))

import { BrainGraph } from './BrainGraph'

const GRAPH = { nodes: [], edges: [] }

let gpuListeners: Array<() => void> = []

describe('BrainGraph — fails OPEN', () => {
  beforeEach(() => {
    vi.useFakeTimers()
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

  // THE REGRESSION. The first cut of this component pre-probed for a WebGL context
  // and mounted the fallback when the probe came back null. A probe has to CREATE a
  // context to answer, contexts are a capped shared resource (the bar Orb and this
  // map already hold some), and near that cap the PROBE is what fails — so on the
  // product owner's perfectly healthy machine the probe reported "WebGL is broken"
  // and his real brain map was replaced by the static mark. Nothing but an actual,
  // observed renderer failure may suppress the graph. There is deliberately no probe
  // left to mock here: mounting the real canvas is the unconditional default.
  it('mounts the REAL graph by default — nothing but a real failure may replace it', () => {
    render(<BrainGraph graph={GRAPH} />)
    expect(screen.getByTestId('brain-graph-canvas')).toBeTruthy()
    expect(screen.queryByTestId('brain-graph-fallback')).toBeNull()
    // No mode change happened, so nothing may be reported as degraded.
    expect(trackEvent).not.toHaveBeenCalledWith(
      'fallback_triggered',
      expect.objectContaining({ outcome: 'degraded' })
    )
  })

  it('shows the static fallback ONLY when the renderer actually throws', () => {
    canvasThrows = true
    const err = vi.spyOn(console, 'error').mockImplementation(() => {})
    render(
      <div data-testid="host">
        <BrainGraph graph={GRAPH} />
      </div>
    )
    // The throw is contained — onboarding mounts this directly, with no boundary
    // above it, and must not be taken down with it.
    expect(screen.getByTestId('host')).toBeTruthy()
    expect(screen.getByTestId('brain-graph-fallback')).toBeTruthy()
    expect(screen.queryByTestId('brain-graph-canvas')).toBeNull()
    expect(trackEvent).toHaveBeenCalledWith('fallback_triggered', {
      component: 'brain_graph_render',
      from: 'webgl',
      to: 'static',
      reason: 'renderer_init_failed',
      outcome: 'degraded'
    })
    err.mockRestore()
  })

  it('reports readiness in fallback mode so a host loading placeholder clears', () => {
    canvasThrows = true
    const err = vi.spyOn(console, 'error').mockImplementation(() => {})
    const onReady = vi.fn()
    render(<BrainGraph graph={GRAPH} onReady={onReady} />)
    expect(onReady).toHaveBeenCalled()
    err.mockRestore()
  })

  it('heals back to the real graph once the GPU recovers', () => {
    canvasThrows = true
    const err = vi.spyOn(console, 'error').mockImplementation(() => {})
    render(<BrainGraph graph={GRAPH} />)
    expect(screen.getByTestId('brain-graph-fallback')).toBeTruthy()

    // GPU process restarted: main broadcasts context-loss, which drives
    // useWebglRecovery's debounced remount — and that resets the boundary.
    canvasThrows = false
    act(() => {
      gpuListeners.forEach((l) => l())
      vi.advanceTimersByTime(1000) // past the 600ms debounce
    })

    expect(screen.getByTestId('brain-graph-canvas')).toBeTruthy()
    expect(screen.queryByTestId('brain-graph-fallback')).toBeNull()
    expect(trackEvent).toHaveBeenLastCalledWith('fallback_triggered', {
      component: 'brain_graph_render',
      from: 'static',
      to: 'webgl',
      reason: 'renderer_init_failed',
      outcome: 'recovered'
    })
    err.mockRestore()
  })

  it('an EMPTY-looking canvas never triggers the fallback (must not mask the render bug)', () => {
    // The graph currently paints zero pixels on some healthy contexts — a separate
    // rendering bug. The canvas mounts and does not throw, so the fallback must stay
    // away; firing on "looks blank" would hide that bug instead of exposing it.
    render(<BrainGraph graph={{ nodes: [], edges: [] }} />)
    expect(screen.getByTestId('brain-graph-canvas')).toBeTruthy()
    expect(screen.queryByTestId('brain-graph-fallback')).toBeNull()
  })
})
