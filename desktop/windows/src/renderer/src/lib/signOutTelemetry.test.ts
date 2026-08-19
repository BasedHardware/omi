import { beforeEach, describe, expect, it, vi } from 'vitest'

const h = vi.hoisted(() => ({
  signOutUser: vi.fn(async () => {}),
  trackSignedOut: vi.fn()
}))

vi.mock('./firebase', () => ({
  auth: { currentUser: { uid: 'user-before-sign-out' } },
  signOutUser: h.signOutUser
}))
vi.mock('./analytics', () => ({ trackSignedOut: h.trackSignedOut }))

import { signOutAndTrack } from './signOutTelemetry'

beforeEach(() => vi.clearAllMocks())

describe('signOutAndTrack', () => {
  it('records success against the identity captured before Firebase clears it', async () => {
    await signOutAndTrack()

    expect(h.signOutUser).toHaveBeenCalledOnce()
    expect(h.trackSignedOut).toHaveBeenCalledExactlyOnceWith('user-before-sign-out')
  })

  it('does not claim success when sign-out fails', async () => {
    h.signOutUser.mockRejectedValueOnce(new Error('failed'))

    await expect(signOutAndTrack()).rejects.toThrow('failed')
    expect(h.trackSignedOut).not.toHaveBeenCalled()
  })
})
