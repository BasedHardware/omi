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

  // The scripts (seed-auth / dev:instance) must resolve the SAME effective ports
  // the app binds, or the documented "set OMI_DEV_PORT to move it" remedy silently
  // targets the wrong port. computeInstance (mjs) mirrors computeDevInstance (TS)
  // including env-override precedence.
  it('resolves identical ports under env overrides (precedence parity)', () => {
    const envs: Array<Record<string, string>> = [
      {},
      { OMI_DEV_PORT: '5210' },
      { OMI_DEV_CDP_PORT: '9251' },
      { OMI_DEV_REMOTE_DEBUG: '9333' },
      // OMI_DEV_REMOTE_DEBUG must win over OMI_DEV_CDP_PORT.
      { OMI_DEV_CDP_PORT: '9251', OMI_DEV_REMOTE_DEBUG: '9333' },
      { OMI_DEV_PORT: '70000', OMI_DEV_CDP_PORT: 'abc' }, // garbage → fall through
      { OMI_INSTANCE: 'primary' },
      { OMI_INSTANCE: 'other-wt', OMI_DEV_CDP_PORT: '9270' }
    ]
    for (const base of [
      { name: 'multi-worktree-dev', isPrimary: false },
      { name: 'omi', isPrimary: true }
    ]) {
      for (const env of envs) {
        const a = ts.computeDevInstance(base.name, base.isPrimary, env)
        const b = mjs.computeInstance(base.name, base.isPrimary, env)
        expect({ n: b.name, p: b.isPrimary, r: b.rendererPort, c: b.cdpPort }).toEqual({
          n: a.name,
          p: a.isPrimary,
          r: a.rendererPort,
          c: a.cdpPort
        })
      }
    }
  })
})
