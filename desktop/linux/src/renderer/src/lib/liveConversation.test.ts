import { it, expect, beforeEach } from 'vitest'
import {
  liveConversation,
  isConversationBoundary
} from './liveConversation'

beforeEach(() => {
  liveConversation.reset()
})

it('starts idle and empty', () => {
  expect(liveConversation.getSegments()).toEqual([])
  expect(liveConversation.getStatus()).toBe('idle')
})

it('appendLine adds segments and notifies subscribers', () => {
  let calls = 0
  const unsub = liveConversation.subscribe(() => {
    calls++
  })
  liveConversation.appendLine({ text: 'hello', speaker: 'You' })
  liveConversation.appendLine({ text: 'world' })
  expect(liveConversation.getSegments().map((s) => s.text)).toEqual(['hello', 'world'])
  expect(calls).toBe(2)
  unsub()
})

it('reset clears segments and sets idle', () => {
  liveConversation.setStatus('live')
  liveConversation.appendLine({ text: 'x' })
  liveConversation.reset()
  expect(liveConversation.getSegments()).toEqual([])
  expect(liveConversation.getStatus()).toBe('idle')
})

it('isConversationBoundary detects memory_creating only', () => {
  expect(isConversationBoundary({ type: 'memory_creating', raw: {} })).toBe(true)
  expect(isConversationBoundary({ type: 'last_audio_bytes', raw: {} })).toBe(false)
  expect(isConversationBoundary({ type: 'freemium_threshold_reached', raw: {} })).toBe(false)
})
