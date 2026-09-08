import { describe, it, expect } from 'vitest'
import { UsageAccumulator } from './usageAccumulator'

const MAX_GAP = 10_000

describe('UsageAccumulator', () => {
  it('credits the earlier sample with the elapsed gap', () => {
    const a = new UsageAccumulator(MAX_GAP)
    a.addSample('C:\\a\\chrome.exe', 1000)
    a.addSample('C:\\a\\chrome.exe', 5000) // +4000ms to chrome
    a.addSample('C:\\b\\code.exe', 6000) // +1000ms to chrome
    const drained = a.drain()
    expect(drained).toEqual([{ exePath: 'C:\\a\\chrome.exe', ms: 5000 }])
  })

  it('caps gaps larger than maxGap (idle/sleep)', () => {
    const a = new UsageAccumulator(MAX_GAP)
    a.addSample('C:\\a\\chrome.exe', 1000)
    a.addSample('C:\\a\\chrome.exe', 1_000_000) // huge gap → not credited
    expect(a.drain()).toEqual([])
  })

  it('ignores null/empty foreground samples', () => {
    const a = new UsageAccumulator(MAX_GAP)
    a.addSample(null, 1000)
    a.addSample('C:\\a\\chrome.exe', 2000)
    a.addSample('C:\\a\\chrome.exe', 4000) // +2000ms
    expect(a.drain()).toEqual([{ exePath: 'C:\\a\\chrome.exe', ms: 2000 }])
  })

  it('drain clears accumulated totals', () => {
    const a = new UsageAccumulator(MAX_GAP)
    a.addSample('C:\\a\\chrome.exe', 1000)
    a.addSample('C:\\a\\chrome.exe', 3000)
    a.drain()
    expect(a.drain()).toEqual([])
  })
})
