// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from 'vitest'
import { isWebglAvailable } from './webglSupport'

// jsdom has no GL, so drive getContext directly — the point is the null/throw
// handling, which is exactly what a GPU-crashed Chromium does.
function stubGetContext(impl: () => unknown): void {
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockImplementation(impl as never)
}

describe('isWebglAvailable', () => {
  afterEach(() => vi.restoreAllMocks())

  it('is true when a webgl2 context is granted', () => {
    stubGetContext(() => ({ getExtension: () => null }))
    expect(isWebglAvailable()).toBe(true)
  })

  it('is false when Chromium refuses the context (returns null)', () => {
    stubGetContext(() => null)
    expect(isWebglAvailable()).toBe(false)
  })

  it('is false when getContext throws outright', () => {
    stubGetContext(() => {
      throw new Error('context creation failed')
    })
    expect(isWebglAvailable()).toBe(false)
  })
})
