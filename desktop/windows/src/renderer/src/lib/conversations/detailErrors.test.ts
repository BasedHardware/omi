import { describe, it, expect } from 'vitest'
import { friendlyConversationError } from './detailErrors'

// PR-D: a failed conversation load must render friendly copy, never a raw
// axios/Error string. 404 / not-found reads as gone; everything else is generic.
describe('friendlyConversationError', () => {
  it('maps a 404 to "no longer exists"', () => {
    expect(friendlyConversationError('Request failed with status code 404')).toBe(
      'This conversation no longer exists.'
    )
  })

  it('maps the local "not found" path to "no longer exists"', () => {
    expect(friendlyConversationError('Local conversation not found')).toBe(
      'This conversation no longer exists.'
    )
  })

  it('maps any other error to the generic load-failure copy', () => {
    expect(friendlyConversationError('Request failed with status code 500')).toBe(
      'Couldn’t load this conversation.'
    )
    expect(friendlyConversationError('Network Error')).toBe('Couldn’t load this conversation.')
  })
})
