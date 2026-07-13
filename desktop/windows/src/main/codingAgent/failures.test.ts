import { describe, expect, it } from 'vitest'
import { failureFromProcessExit, sanitizeProcessDiagnostic } from './failures'

describe('sanitizeProcessDiagnostic', () => {
  it('redacts bearer tokens, sk- keys, and api_key fields', () => {
    const out = sanitizeProcessDiagnostic(
      'auth: Bearer abc.123-secret api_key="sk-aaaabbbbccccdddd" and api-key: qqqq1234'
    )
    expect(out).toContain('Bearer [redacted]')
    expect(out).not.toContain('abc.123-secret')
    expect(out).not.toContain('sk-aaaabbbbccccdddd')
    expect(out).not.toContain('qqqq1234')
  })

  it('redacts token/secret/password-style fields and provider token shapes', () => {
    const out = sanitizeProcessDiagnostic(
      'login failed: token=tok_livevalue password: hunter2 secret="s3cr3tvalue" ' +
        'gh: ghp_abcdefghijklmnop1234 pat: github_pat_11ABCDEFG0123456789abc slack: xoxb-1234567890-abcdef'
    )
    expect(out).not.toContain('tok_livevalue')
    expect(out).not.toContain('hunter2')
    expect(out).not.toContain('s3cr3tvalue')
    expect(out).not.toContain('ghp_abcdefghijklmnop1234')
    expect(out).not.toContain('github_pat_11ABCDEFG0123456789abc')
    expect(out).not.toContain('xoxb-1234567890-abcdef')
  })

  it('keeps the TAIL of long diagnostics so the final error lines survive', () => {
    const out = sanitizeProcessDiagnostic('x'.repeat(1_500) + ' FINAL_ERROR_LINE')
    expect(out).toHaveLength(1_000)
    expect(out).toContain('FINAL_ERROR_LINE')
  })

  it('trailing OpenClaw config errors still classify after truncation', () => {
    const failure = failureFromProcessExit({
      adapterId: 'openclaw',
      exitCode: 1,
      recentStderr: 'noise '.repeat(300) + 'openclaw config is invalid, run openclaw doctor --fix'
    })
    expect(failure.code).toBe('adapter_config_invalid')
    expect(failure.retryable).toBe(false)
  })
})
