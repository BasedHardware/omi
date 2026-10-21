import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { detectLinuxCompositor, defaultOzonePlatform } from './linuxCompositor'

const MARKERS = ['XDG_SESSION_TYPE', 'NIRI_SOCKET', 'SWAYSOCK', 'HYPRLAND_INSTANCE_SIGNATURE']
const original = Object.fromEntries(MARKERS.map((k) => [k, process.env[k]]))

// Each test starts from a clean slate regardless of the host's own session
// (this repo's dev env may itself be running under niri/sway/hyprland).
beforeEach(() => {
  for (const k of MARKERS) delete process.env[k]
})

afterEach(() => {
  for (const k of MARKERS) {
    if (original[k] === undefined) delete process.env[k]
    else process.env[k] = original[k]
  }
})

describe('detectLinuxCompositor', () => {
  it('returns undefined when no compositor marker is set', () => {
    expect(detectLinuxCompositor()).toBeUndefined()
  })
  it('identifies niri via NIRI_SOCKET', () => {
    process.env.NIRI_SOCKET = '/run/user/1000/niri.sock'
    expect(detectLinuxCompositor()).toBe('niri')
  })
  it('identifies sway via SWAYSOCK', () => {
    process.env.SWAYSOCK = '/run/user/1000/sway-ipc.sock'
    expect(detectLinuxCompositor()).toBe('sway')
  })
  it('identifies hyprland via HYPRLAND_INSTANCE_SIGNATURE', () => {
    process.env.HYPRLAND_INSTANCE_SIGNATURE = 'abc123'
    expect(detectLinuxCompositor()).toBe('hyprland')
  })
})

describe('defaultOzonePlatform', () => {
  it('is x11 on an X11 session', () => {
    process.env.XDG_SESSION_TYPE = 'x11'
    expect(defaultOzonePlatform()).toBe('x11')
  })
  it('is x11 when the session type is unset (non-Linux / unknown)', () => {
    delete process.env.XDG_SESSION_TYPE
    expect(defaultOzonePlatform()).toBe('x11')
  })
  it('is x11 on a Wayland session with no recognized compositor (e.g. GNOME, KDE)', () => {
    process.env.XDG_SESSION_TYPE = 'wayland'
    expect(defaultOzonePlatform()).toBe('x11')
  })
  it('is wayland on a Wayland session under niri', () => {
    process.env.XDG_SESSION_TYPE = 'wayland'
    process.env.NIRI_SOCKET = '/run/user/1000/niri.sock'
    expect(defaultOzonePlatform()).toBe('wayland')
  })
})
