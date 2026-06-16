import { describe, it, expect } from 'vitest'
import { OVERLAY_ACCELERATOR } from './shortcut'

describe('OVERLAY_ACCELERATOR', () => {
  it('defaults to Shift+Space', () => {
    expect(OVERLAY_ACCELERATOR).toBe('Shift+Space')
  })
})
