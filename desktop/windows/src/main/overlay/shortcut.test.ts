import { describe, it, expect, vi } from 'vitest'

vi.mock('electron', () => ({
  globalShortcut: {
    register: () => true,
    unregister: () => {}
  }
}))

import { OVERLAY_ACCELERATOR } from './shortcut'

describe('OVERLAY_ACCELERATOR', () => {
  it('defaults to Shift+Space', () => {
    expect(OVERLAY_ACCELERATOR).toBe('Shift+Space')
  })
})
