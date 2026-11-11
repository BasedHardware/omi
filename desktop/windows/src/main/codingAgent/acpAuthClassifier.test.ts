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

  it('accepts expired / rejected OAuth credentials so they reopen the reconnect flow', () => {
    // A failed refresh returns the standard OAuth2 invalid_grant; access-token
    // expiry surfaces as "access/oauth token expired"/"token has expired". All
    // must reconnect, never terminate as a "Failed" pill.
    expect(
      isRecoverableAcpAuthError(new AcpError('Internal error: OAuth error: invalid_grant', -32603))
    ).toBe(true)
    expect(
      isRecoverableAcpAuthError(new AcpError('Internal error: token has expired', -32603))
    ).toBe(true)
    expect(
      isRecoverableAcpAuthError(
        new AcpError('Internal error', -32603, { details: 'access token expired' })
      )
    ).toBe(true)
    expect(
      isRecoverableAcpAuthError(
        new AcpError('Internal error', -32603, { details: 'OAuth token expired' })
      )
    ).toBe(true)
  })

  it('does NOT treat a coincidental bare "token expired" in a non-auth error as auth', () => {
    // The markers are anchored ("access/oauth token expired") on purpose: an
    // unrelated internal error whose body happens to contain the words "token
    // expired" (e.g. a cache/session token) must stay terminal, not open a
    // surprise login flow.
    expect(
      isRecoverableAcpAuthError(
        new AcpError('Internal error', -32603, {
          details: 'render cache token expired, rebuilding'
        })
      )
    ).toBe(false)
  })

  it('leaves the packaged claude.exe launch failure TERMINAL (not auth), with detail intact', () => {
    // The bug this PR fixes: a child-boot failure is a real terminal error, not
    // an auth problem — it must NOT open a surprise login. (Its detail is surfaced
    // separately via messageFrom; see failures.test.ts.)
    const launchFailure = new AcpError('Internal error', -32603, {
      details: 'Claude Code native binary ... exists but failed to launch.'
    })
    expect(isRecoverableAcpAuthError(launchFailure)).toBe(false)
  })

  it('leaves the bridge non-auth "session has ended" message terminal', () => {
    expect(
      isRecoverableAcpAuthError(
        new AcpError('Internal error: The Claude Agent session has ended.', -32603)
      )
    ).toBe(false)
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
