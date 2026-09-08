import { describe, expect, it } from 'vitest'
import { buildListenHeaders } from './omiListen'

describe('Windows listen transport', () => {
  it('adds device provenance to the authenticated WebSocket upgrade', () => {
    expect(buildListenHeaders('firebase-token', 'a1b2c3d4')).toEqual({
      Authorization: 'Bearer firebase-token',
      'X-App-Platform': 'windows',
      'X-Device-Id-Hash': 'a1b2c3d4'
    })
  })
})
