import { describe, expect, it } from 'vitest'
import {
  derivePort,
  fnv1a,
  planPortSequence,
  FALLBACK_PORTS,
  PORT_BASE,
  PORT_SPAN,
  RETRY_DELAYS_MS
} from './portDerivation'

describe('derivePort', () => {
  it('is deterministic for the same path', () => {
    const p = 'C:\\Users\\chris\\AppData\\Roaming\\Omi for Windows'
    expect(derivePort(p)).toBe(derivePort(p))
  })

  it('normalizes case and separators (Windows path semantics)', () => {
    expect(derivePort('C:\\Users\\Chris\\AppData\\Roaming\\Omi')).toBe(
      derivePort('c:/users/chris/appdata/roaming/omi/')
    )
  })

  it('stays within [base, base+span)', () => {
    const paths = [
      'C:\\Users\\a\\AppData\\Roaming\\Omi for Windows',
      'C:\\sandbox\\one',
      'C:\\sandbox\\two',
      'D:\\Some\\Other\\Install',
      ''
    ]
    for (const p of paths) {
      const port = derivePort(p)
      expect(port).toBeGreaterThanOrEqual(PORT_BASE)
      expect(port).toBeLessThan(PORT_BASE + PORT_SPAN)
    }
  })

  it('gives distinct ports to distinct sandbox userData paths (dispersion sanity)', () => {
    const ports = new Set<number>()
    for (let i = 0; i < 50; i++) ports.add(derivePort(`C:\\sandboxes\\instance-${i}`))
    // Not a strict guarantee (pigeonhole), but 50 short suffixes into 500 slots
    // should almost never collide more than a few times; require strong spread.
    expect(ports.size).toBeGreaterThan(45)
  })

  it('fnv1a matches the reference vector', () => {
    // Known FNV-1a 32-bit test vectors
    expect(fnv1a('')).toBe(0x811c9dc5)
    expect(fnv1a('a')).toBe(0xe40c292c)
    expect(fnv1a('foobar')).toBe(0xbf9cf968)
  })
})

describe('planPortSequence', () => {
  it('retries the derived port with backoff before falling back', () => {
    const plan = planPortSequence(17400)
    const retries = plan.filter((a) => !a.isFallback)
    expect(retries).toHaveLength(RETRY_DELAYS_MS.length)
    expect(retries.every((a) => a.port === 17400)).toBe(true)
    expect(retries.map((a) => a.delayMs)).toEqual(RETRY_DELAYS_MS)
  })

  it('falls back to sequential ports, flagged as session-breaking', () => {
    const plan = planPortSequence(17400)
    const fallbacks = plan.filter((a) => a.isFallback)
    expect(fallbacks).toHaveLength(FALLBACK_PORTS)
    expect(fallbacks.map((a) => a.port)).toEqual(
      Array.from({ length: FALLBACK_PORTS }, (_, i) => 17401 + i)
    )
    expect(fallbacks.every((a) => a.delayMs === 0)).toBe(true)
  })

  it('orders retries strictly before fallbacks', () => {
    const plan = planPortSequence(17400)
    const firstFallback = plan.findIndex((a) => a.isFallback)
    expect(plan.slice(0, firstFallback).every((a) => !a.isFallback)).toBe(true)
    expect(plan.slice(firstFallback).every((a) => a.isFallback)).toBe(true)
  })
})
