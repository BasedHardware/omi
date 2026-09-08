import { describe, expect, it } from 'vitest'
import {
  failureFromError,
  failureFromProcessExit,
  jsonRpcErrorDetail,
  messageFrom,
  sanitizeProcessDiagnostic
} from './failures'
import { AcpError } from './acp'

describe('messageFrom / jsonRpcErrorDetail — never a bare "Internal error"', () => {
  it('folds the packaged claude.exe launch-failure detail into the message', () => {
    // The exact shape observed reproducing the packaged-build spawn bug: a bare
    // -32603 "Internal error" whose real cause lives in data.details.
    const err = new AcpError('Internal error', -32603, {
      details:
        'Claude Code native binary at C:\\...\\app.asar\\node_modules\\@anthropic-ai\\claude-agent-sdk-win32-x64\\claude.exe exists but failed to launch.'
    })
    const msg = messageFrom(err)
    expect(msg).toContain('Internal error')
    expect(msg).toContain('failed to launch')
    expect(msg).not.toBe('Internal error')
  })

  it('surfaces a wrapped provider 401 body from data.error.message', () => {
    const err = new AcpError('Internal error', -32603, {
      error: { type: 'authentication_error', message: 'Invalid authentication credentials' }
    })
    expect(messageFrom(err)).toContain('Invalid authentication credentials')
  })

  it('does not duplicate when the detail repeats the base message', () => {
    const err = new AcpError('Authentication required', -32000, {
      message: 'Authentication required'
    })
    expect(messageFrom(err)).toBe('Authentication required')
  })

  it('caps an oversized detail body', () => {
    const err = new AcpError('Internal error', -32603, { details: 'x'.repeat(5_000) })
    const msg = messageFrom(err)
    expect(msg.length).toBeLessThan(400)
    expect(msg.endsWith('…')).toBe(true)
  })

  it('redacts token shapes in bridge-controlled detail before it reaches pill or logs', () => {
    // data is provider/bridge-controlled: a raw response body echoed into
    // details must never leak credentials through the folded message.
    const err = new AcpError('Internal error', -32603, {
      details:
        'request failed: Authorization: Bearer sk-ant-abc123def456ghi789 api_key=sk-live-000111222333 body={"token":"ghp_abcdefghijklmnop1234"}'
    })
    const msg = messageFrom(err)
    expect(msg).toContain('request failed')
    expect(msg).not.toContain('sk-ant-abc123def456ghi789')
    expect(msg).not.toContain('sk-live-000111222333')
    expect(msg).not.toContain('ghp_abcdefghijklmnop1234')
    expect(msg).toContain('[redacted]')
  })

  it('falls back to stringified data and still redacts it', () => {
    const err = new AcpError('Internal error', -32603, {
      status: 500,
      authorization: 'Bearer sk-proj-zzz999yyy888xxx777'
    })
    const msg = messageFrom(err)
    expect(msg).not.toContain('sk-proj-zzz999yyy888xxx777')
  })

  it('leaves plain Errors and non-numeric-code errors untouched', () => {
    expect(messageFrom(new Error('boom'))).toBe('boom')
    // Node system errors carry a STRING code — must not be treated as JSON-RPC.
    const sysErr = Object.assign(new Error('ENOENT: no such file'), { code: 'ENOENT' })
    expect(jsonRpcErrorDetail(sysErr)).toBeUndefined()
    expect(messageFrom(sysErr)).toBe('ENOENT: no such file')
  })

  it('failureFromError carries the rich detail into userMessage for a raw AcpError', () => {
    const err = new AcpError('Internal error', -32603, { details: 'child boot failed' })
    const failure = failureFromError(err, { code: 'agent_task_failed', adapterId: 'acp' })
    expect(failure.userMessage).toContain('child boot failed')
  })
})

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
