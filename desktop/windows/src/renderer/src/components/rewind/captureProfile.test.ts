import { describe, it, expect } from 'vitest'
import { rewindCaptureProfile, sampledCanvasSize } from './captureProfile'

// #10489: 720p screenshots were too low-res for OCR, with no way to raise them.
// These pin the opt-in contract: the default profile is unchanged (no perf
// regression), the high profile is strictly higher-res + higher-quality, and the
// sampling math never upscales.

describe('rewindCaptureProfile', () => {
  it('keeps the perf-tuned 720p baseline when high-res is off (default)', () => {
    expect(rewindCaptureProfile(false)).toEqual({
      maxWidth: 1280,
      maxHeight: 720,
      maxEdge: 1600,
      jpegQuality: 0.6
    })
  })

  it('raises resolution and quality when high-res is on', () => {
    const high = rewindCaptureProfile(true)
    const standard = rewindCaptureProfile(false)
    expect(high.maxWidth).toBeGreaterThan(standard.maxWidth)
    expect(high.maxHeight).toBeGreaterThan(standard.maxHeight)
    expect(high.maxEdge).toBeGreaterThanOrEqual(high.maxWidth)
    expect(high.jpegQuality).toBeGreaterThan(standard.jpegQuality)
  })
})

describe('sampledCanvasSize', () => {
  it('never upscales a source smaller than maxEdge', () => {
    const p = rewindCaptureProfile(false) // maxEdge 1600
    expect(sampledCanvasSize(1280, 720, p)).toEqual({ width: 1280, height: 720 })
  })

  it('downscales the longest edge to maxEdge, preserving aspect ratio', () => {
    const p = rewindCaptureProfile(true) // maxEdge 1920
    // A 3840×2160 (4K) frame → longest 3840 scales to 1920 (×0.5).
    expect(sampledCanvasSize(3840, 2160, p)).toEqual({ width: 1920, height: 1080 })
  })

  it('is safe on a zero-sized (not-yet-ready) video frame', () => {
    const p = rewindCaptureProfile(false)
    expect(sampledCanvasSize(0, 0, p)).toEqual({ width: 0, height: 0 })
  })
})
