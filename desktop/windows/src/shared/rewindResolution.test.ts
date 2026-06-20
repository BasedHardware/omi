import { describe, it, expect } from 'vitest'
import {
  clampCaptureMaxEdge,
  DEFAULT_CAPTURE_MAX_EDGE,
  CAPTURE_RESOLUTIONS
} from './rewindResolution'

describe('clampCaptureMaxEdge', () => {
  it('passes through an exact preset value', () => {
    for (const r of CAPTURE_RESOLUTIONS) {
      expect(clampCaptureMaxEdge(r.maxEdge)).toBe(r.maxEdge)
    }
  })

  it('snaps an off-preset value to the nearest preset', () => {
    expect(clampCaptureMaxEdge(1000)).toBe(960) // closer to Low than Balanced
    expect(clampCaptureMaxEdge(1300)).toBe(1280) // closer to Balanced
    expect(clampCaptureMaxEdge(5000)).toBe(1920) // beyond High → clamps to High
  })

  it('falls back to the default for invalid input', () => {
    expect(clampCaptureMaxEdge(undefined)).toBe(DEFAULT_CAPTURE_MAX_EDGE)
    expect(clampCaptureMaxEdge(null)).toBe(DEFAULT_CAPTURE_MAX_EDGE)
    expect(clampCaptureMaxEdge('1280')).toBe(DEFAULT_CAPTURE_MAX_EDGE)
    expect(clampCaptureMaxEdge(0)).toBe(DEFAULT_CAPTURE_MAX_EDGE)
    expect(clampCaptureMaxEdge(-100)).toBe(DEFAULT_CAPTURE_MAX_EDGE)
    expect(clampCaptureMaxEdge(NaN)).toBe(DEFAULT_CAPTURE_MAX_EDGE)
  })

  it('default is one of the offered presets', () => {
    expect(CAPTURE_RESOLUTIONS.map((r) => r.maxEdge)).toContain(DEFAULT_CAPTURE_MAX_EDGE)
  })
})
