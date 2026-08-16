import { describe, it, expect, beforeEach, vi } from 'vitest'

// Only Menu is used by appMenu.ts; provide a spy-able setApplicationMenu. Defined
// via vi.hoisted so the (hoisted) vi.mock factory can reference it safely.
const { setApplicationMenu } = vi.hoisted(() => ({ setApplicationMenu: vi.fn() }))
vi.mock('electron', () => ({ Menu: { setApplicationMenu } }))

import { disableApplicationMenu } from './appMenu'

describe('disableApplicationMenu', () => {
  beforeEach(() => setApplicationMenu.mockClear())

  it('removes the stock application menu via setApplicationMenu(null)', () => {
    disableApplicationMenu()
    expect(setApplicationMenu).toHaveBeenCalledTimes(1)
    expect(setApplicationMenu).toHaveBeenCalledWith(null)
  })
})
