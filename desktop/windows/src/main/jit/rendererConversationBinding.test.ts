import { beforeEach, describe, expect, it } from 'vitest'
import {
  clearRendererConversationBinding,
  fenceRendererConversationOwner,
  rendererConversationBinding,
  rendererConversationBindingIsCurrent,
  resetRendererConversationBindingForTests,
  setRendererConversationSelection
} from './rendererConversationBinding'

describe('renderer-visible JIT conversation binding', () => {
  beforeEach(() => resetRendererConversationBindingForTests())

  it('records an explicit selection before any chat send', () => {
    expect(rendererConversationBinding()).toBeNull()

    setRendererConversationSelection('account-A', 'chat-selected-before-send')

    expect(rendererConversationBinding()).toEqual({
      ownerId: 'account-A',
      accountGeneration: 1,
      deletionKey: 'chat-selected-before-send'
    })
  })

  it('captures a turn owner so a concurrent selection cannot retarget it', () => {
    setRendererConversationSelection('account-A', 'chat-A')
    const admitted = rendererConversationBinding()
    expect(admitted).not.toBeNull()

    setRendererConversationSelection('account-A', 'chat-B')

    expect(admitted?.deletionKey).toBe('chat-A')
    expect(rendererConversationBinding()?.deletionKey).toBe('chat-B')
    expect(admitted && rendererConversationBindingIsCurrent(admitted)).toBe(true)
  })

  it('invalidates the old account binding on sign-out and account switch', () => {
    setRendererConversationSelection('account-A', 'chat-A')
    const old = rendererConversationBinding()
    expect(old).not.toBeNull()

    clearRendererConversationBinding()
    expect(rendererConversationBinding()).toBeNull()
    expect(old && rendererConversationBindingIsCurrent(old)).toBe(false)

    setRendererConversationSelection('account-B', 'chat-B')
    const next = rendererConversationBinding()
    expect(next?.ownerId).toBe('account-B')
    expect(next?.accountGeneration).toBeGreaterThan(old?.accountGeneration ?? 0)
    expect(next && rendererConversationBindingIsCurrent(next)).toBe(true)
  })

  it('fences an account switch even when sign-out delivery is delayed', () => {
    setRendererConversationSelection('account-A', 'chat-A')
    const old = rendererConversationBinding()

    fenceRendererConversationOwner('account-B')

    expect(rendererConversationBinding()).toBeNull()
    expect(old && rendererConversationBindingIsCurrent(old)).toBe(false)
  })

  it('clears pre-chat and malformed selections', () => {
    setRendererConversationSelection('account-A', null)
    expect(rendererConversationBinding()).toBeNull()

    setRendererConversationSelection('account-A', '   ')
    expect(rendererConversationBinding()).toBeNull()
  })

  it('adopts a cold-start selection only after the host supplies an owner', () => {
    setRendererConversationSelection(null, 'chat-before-auth')
    expect(rendererConversationBinding()).toBeNull()

    fenceRendererConversationOwner('account-A')

    expect(rendererConversationBinding()?.deletionKey).toBe('chat-before-auth')
  })
})
