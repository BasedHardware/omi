import { describe, expect, it } from 'vitest'
import { scrubPackagedE2EEnvironment } from './e2eEnvironment'

describe('scrubPackagedE2EEnvironment', () => {
  it('removes test-only flags from packaged launches', () => {
    const env = { OMI_E2E: '1', OMI_E2E_FAKE_AUTH: '1', KEEP_ME: 'yes' }
    scrubPackagedE2EEnvironment(true, env)
    expect(env).toEqual({ KEEP_ME: 'yes' })
  })

  it('retains flags for an unpackaged test harness', () => {
    const env = { OMI_E2E: '1', OMI_E2E_FAKE_AUTH: '1' }
    scrubPackagedE2EEnvironment(false, env)
    expect(env).toEqual({ OMI_E2E: '1', OMI_E2E_FAKE_AUTH: '1' })
  })
})
