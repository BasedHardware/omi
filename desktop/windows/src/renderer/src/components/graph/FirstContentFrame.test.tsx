// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, cleanup } from '@testing-library/react'

// Mock the r3f frame loop: capture the useFrame callback so the test can drive
// "frames" by hand, and expose the invalidate() from useThree. This lets us unit
// test FirstContentFrame — the load-bearing "first painted content frame" signal
// the Memories preview reveals on — without mounting a real WebGL Canvas.
let frameCb: (() => void) | undefined
const invalidate = vi.fn()
vi.mock('@react-three/fiber', () => ({
  useThree: (sel: (s: { invalidate: () => void }) => unknown) => sel({ invalidate }),
  useFrame: (cb: () => void) => {
    frameCb = cb
  }
}))

import { FirstContentFrame } from './FirstContentFrame'

const tick = (): void => frameCb?.()

beforeEach(() => {
  frameCb = undefined
  invalidate.mockClear()
})
afterEach(() => cleanup())

describe('FirstContentFrame', () => {
  it('does not fire while not ready, even across frames', () => {
    const onFire = vi.fn()
    render(<FirstContentFrame ready={false} onFire={onFire} />)
    tick()
    tick()
    expect(onFire).not.toHaveBeenCalled()
    expect(invalidate).not.toHaveBeenCalled()
  })

  it('kicks a render (invalidate) when ready flips true, then fires onFire on the next frame', () => {
    const onFire = vi.fn()
    const { rerender } = render(<FirstContentFrame ready={false} onFire={onFire} />)
    expect(invalidate).not.toHaveBeenCalled()

    // content becomes ready (nodes populated)
    rerender(<FirstContentFrame ready={true} onFire={onFire} />)
    // the effect kicked a demand-mode repaint…
    expect(invalidate).toHaveBeenCalledTimes(1)
    // …but nothing fires until a frame actually runs
    expect(onFire).not.toHaveBeenCalled()

    tick()
    expect(onFire).toHaveBeenCalledTimes(1)
  })

  it('fires exactly once and never re-fires on later frames or re-renders', () => {
    const onFire = vi.fn()
    const { rerender } = render(<FirstContentFrame ready={true} onFire={onFire} />)
    tick()
    expect(onFire).toHaveBeenCalledTimes(1)
    // subsequent frames must not re-fire
    tick()
    tick()
    expect(onFire).toHaveBeenCalledTimes(1)
    // a data swap (still ready) within the same mount must not re-fire either
    rerender(<FirstContentFrame ready={true} onFire={onFire} />)
    tick()
    expect(onFire).toHaveBeenCalledTimes(1)
  })

  it('mounting already-ready fires on the first frame', () => {
    const onFire = vi.fn()
    render(<FirstContentFrame ready={true} onFire={onFire} />)
    expect(invalidate).toHaveBeenCalledTimes(1)
    expect(onFire).not.toHaveBeenCalled()
    tick()
    expect(onFire).toHaveBeenCalledTimes(1)
  })
})
