import { describe, expect, it } from 'vitest'
import * as ts from './devInstance'
import * as mjs from '../../scripts/lib/dev-ports.mjs'

// scripts/lib/dev-ports.mjs mirrors the port math of devInstance.ts so the
// plain-Node helper scripts can resolve ports without a TS loader. This test
// fails the moment the two drift — edit both or neither.
describe('dev-ports.mjs parity with devInstance.ts', () => {
  it('shares the same constants', () => {
    expect(mjs.PRIMARY_RENDERER_PORT).toBe(ts.PRIMARY_RENDERER_PORT)
    expect(mjs.PRIMARY_CDP_PORT).toBe(ts.PRIMARY_CDP_PORT)
    expect(mjs.DEV_RENDERER_BASE).toBe(ts.DEV_RENDERER_BASE)
    expect(mjs.DEV_RENDERER_SPAN).toBe(ts.DEV_RENDERER_SPAN)
    expect(mjs.DEV_CDP_BASE).toBe(ts.DEV_CDP_BASE)
    expect(mjs.DEV_CDP_SPAN).toBe(ts.DEV_CDP_SPAN)
  })

  it('derives identical ports + slugs across a name corpus', () => {
    const names = [
      'multi-worktree-dev',
      'primary',
      'Feat/My Branch!',
      'fix-orb',
      'a',
      '///',
      'UPPER_case.1',
      'worktree-99'
    ]
    for (const n of names) {
      expect(mjs.deriveRendererPort(n)).toBe(ts.deriveRendererPort(n))
      expect(mjs.deriveCdpPort(n)).toBe(ts.deriveCdpPort(n))
      expect(mjs.sanitizeInstanceName(n)).toBe(ts.sanitizeInstanceName(n))
    }
  })
})
