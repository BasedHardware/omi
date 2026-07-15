// Port of macOS agent/tests/runtime-adapter.test.ts "ACP authentication
// recovery classification" — the accept/reject matrix for the error classifier
// that decides whether a failed ACP call should re-enter the Claude sign-in
// flow. Keeping the same cases keeps Windows and macOS from drifting apart.
import { describe, it, expect } from 'vitest'
import { AcpError, isRecoverableAcpAuthError } from './acp'

describe('isRecoverableAcpAuthError', () => {
  it('accepts the canonical ACP auth-required error (-32000)', () => {
    expect(isRecoverableAcpAuthError(new AcpError('Authentication required', -32000))).toBe(true)
  })

  it('accepts the wrapped provider 401 returned during session/prompt (-32603 + marker)', () => {
    const error = new AcpError(
      'Internal error: Failed to authenticate. API Error: 401 {"type":"error","error":{"type":"authentication_error","message":"Invalid authentication credentials"}}',
      -32603
    )
    expect(isRecoverableAcpAuthError(error)).toBe(true)
  })

  it('accepts structured auth failure data when the message is generic', () => {
    const error = new AcpError('Internal error', -32603, {
      error: { type: 'authentication_error', message: 'token rejected' }
    })
    expect(isRecoverableAcpAuthError(error)).toBe(true)
  })

  it('leaves unrelated internal and non-ACP errors terminal', () => {
    expect(
      isRecoverableAcpAuthError(new AcpError('Internal error: database unavailable', -32603))
    ).toBe(false)
    expect(isRecoverableAcpAuthError(new Error('Invalid authentication credentials'))).toBe(false)
    // A method-not-found (-32601) is not an auth failure.
    expect(isRecoverableAcpAuthError(new AcpError('Method not handled', -32601))).toBe(false)
  })
})
