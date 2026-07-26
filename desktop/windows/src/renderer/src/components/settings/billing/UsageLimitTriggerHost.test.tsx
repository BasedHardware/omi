// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, render } from '@testing-library/react'

const appState = vi.hoisted(() => ({
  chat: {
    sending: false,
    quotaCheckSeq: 0
  }
}))
const syncSpy = vi.hoisted(() => vi.fn(() => Promise.resolve()))

vi.mock('../../../state/appState', () => ({
  useAppState: () => appState
}))
vi.mock('../../../hooks/useChat', () => ({
  mainChatQuotaGate: { sync: syncSpy }
}))

import { UsageLimitTriggerHost } from './UsageLimitTriggerHost'

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
  appState.chat = {
    sending: false,
    quotaCheckSeq: 0
  }
})

describe('UsageLimitTriggerHost', () => {
  it('probes only for an explicit hosted-chat completion, not a generic busy-to-idle edge', () => {
    const { rerender } = render(<UsageLimitTriggerHost />)

    act(() => {
      appState.chat = { sending: true, quotaCheckSeq: 0 }
      rerender(<UsageLimitTriggerHost />)
    })
    act(() => {
      appState.chat = { sending: false, quotaCheckSeq: 0 }
      rerender(<UsageLimitTriggerHost />)
    })
    expect(syncSpy).not.toHaveBeenCalled()

    act(() => {
      appState.chat = { sending: false, quotaCheckSeq: 1 }
      rerender(<UsageLimitTriggerHost />)
    })
    expect(syncSpy).toHaveBeenCalledOnce()
  })
})
