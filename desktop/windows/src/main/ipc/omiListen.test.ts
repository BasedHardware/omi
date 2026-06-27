import { describe, it, expect } from 'vitest'
import { classifyWsFatal } from './omiListen'

// Unit tests for the WebSocket fatal-error classification logic.
// "fatal" means the renderer should abort the session immediately.
// A pre-connect error (connected=false) is fatal — the stream never came up.
// A post-connect error (connected=true) is non-fatal — the 'close' event
// fires next and drives normal teardown in the renderer via onLost.

describe('classifyWsFatal', () => {
  it('is fatal when error fires before connection opens (connected=false)', () => {
    expect(classifyWsFatal(false)).toBe(true)
  })

  it('is not fatal when error fires after connection opened (connected=true)', () => {
    expect(classifyWsFatal(true)).toBe(false)
  })
})

