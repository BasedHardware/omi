import { describe, it, expect } from 'vitest'
import {
  reduceCaptureState,
  computeCaptureDirective,
  BATTERY_CAPTURE_INTERVAL_MULTIPLIER,
  type CaptureDirectiveState
} from './captureDirective'

const base: CaptureDirectiveState = {
  suspended: false,
  locked: false,
  onBattery: false,
  baseIntervalMs: 1000
}

describe('computeCaptureDirective — battery cadence', () => {
  it('keeps the base interval on AC power', () => {
    expect(computeCaptureDirective(base)).toEqual({ paused: false, intervalMs: 1000 })
  })
  it('multiplies the interval by 3 on battery', () => {
    expect(computeCaptureDirective({ ...base, onBattery: true })).toEqual({
      paused: false,
      intervalMs: 1000 * BATTERY_CAPTURE_INTERVAL_MULTIPLIER
    })
  })
  it('scales an arbitrary base interval by the multiplier on battery', () => {
    expect(computeCaptureDirective({ ...base, baseIntervalMs: 2500, onBattery: true })).toEqual({
      paused: false,
      intervalMs: 2500 * BATTERY_CAPTURE_INTERVAL_MULTIPLIER
    })
  })
})

describe('reduceCaptureState — power transitions', () => {
  it('on-battery → 3× interval, on-ac → base interval', () => {
    const onBattery = reduceCaptureState(base, 'on-battery')
    expect(computeCaptureDirective(onBattery).intervalMs).toBe(3000)
    const backToAc = reduceCaptureState(onBattery, 'on-ac')
    expect(computeCaptureDirective(backToAc).intervalMs).toBe(1000)
  })
})
