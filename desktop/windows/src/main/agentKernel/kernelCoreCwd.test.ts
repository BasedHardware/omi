// Regression: an agent run/binding with no explicit cwd must fall back to the
// user's HOME dir, never process.cwd().
//
// WHY THIS MATTERS. In a packaged app launched from a shortcut, process.cwd() is
// the shortcut's "Start in" directory — often C:\Windows\System32 or another
// unwritable/surprising path — not the repo dir it is under `pnpm dev`. A no-cwd
// agent run therefore executed somewhere different (and possibly unwritable) in a
// shipped build vs dev. fallbackCwd() pins the default to homedir(), which is
// stable + writable on every platform.

import { homedir } from 'node:os'
import { describe, expect, it } from 'vitest'
import { fallbackCwd } from './kernelCore'

describe('fallbackCwd', () => {
  it('returns the user home dir', () => {
    expect(fallbackCwd()).toBe(homedir())
  })

  it('is not process.cwd() (the packaged-launch trap) when the two differ', () => {
    // In CI/dev the checkout dir (cwd) is not the home dir, so a regression back to
    // process.cwd() would change this value. Guard only asserts the distinction when
    // they genuinely differ, so it never flakes on an env where home == cwd.
    if (homedir() !== process.cwd()) {
      expect(fallbackCwd()).not.toBe(process.cwd())
    }
    expect(fallbackCwd()).toBe(homedir())
  })
})
