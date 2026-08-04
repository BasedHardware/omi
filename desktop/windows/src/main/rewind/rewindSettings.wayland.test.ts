import { describe, it, expect, vi, afterEach } from 'vitest'

// app.getPath isn't available under vitest; the Wayland default is pure env
// logic, so a light electron stub is enough for the module to import.
vi.mock('electron', () => ({ app: { getPath: () => '/tmp' } }))

import { defaultCaptureEnabled } from './rewindSettings'

const original = process.env.XDG_SESSION_TYPE
afterEach(() => {
  if (original === undefined) delete process.env.XDG_SESSION_TYPE
  else process.env.XDG_SESSION_TYPE = original
})

describe('defaultCaptureEnabled (Wayland gating)', () => {
  it('is false on a Wayland session (avoids the per-frame portal prompt)', () => {
    process.env.XDG_SESSION_TYPE = 'wayland'
    expect(defaultCaptureEnabled()).toBe(false)
  })
  it('is true on an X11 session', () => {
    process.env.XDG_SESSION_TYPE = 'x11'
    expect(defaultCaptureEnabled()).toBe(true)
  })
  it('is true when the session type is unset (non-Linux / unknown)', () => {
    delete process.env.XDG_SESSION_TYPE
    expect(defaultCaptureEnabled()).toBe(true)
  })
})
