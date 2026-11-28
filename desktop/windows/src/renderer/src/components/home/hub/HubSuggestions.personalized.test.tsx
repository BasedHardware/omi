// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, cleanup, screen } from '@testing-library/react'
import { HubSuggestions } from './HubSuggestions'
import { HubChatPanel } from './HubChatPanel'
import { __resetSuggestionsGenerationForTest } from '../../../lib/intelligence/homeSuggestions'

vi.mock('../../../lib/persistentCache', () => ({ getCacheUid: () => 'uid-1' }))
vi.mock('../../../lib/apiClient', () => ({
  omiApi: { get: vi.fn(async () => ({ data: [] })), post: vi.fn(), delete: vi.fn() }
}))
vi.mock('../../../lib/agentLLM', () => ({ callAgentLLM: vi.fn(async () => '{"questions": []}') }))
vi.mock('../../../lib/actionItems', () => ({ fetchAllActionItems: vi.fn(async () => []) }))
vi.mock('../../chat/ChatMessages', () => ({ ChatMessages: () => <div data-testid="messages" /> }))

/* eslint-disable @typescript-eslint/no-empty-function -- no-op stub */
class ResizeObserverStub {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}
/* eslint-enable @typescript-eslint/no-empty-function */
;(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub

beforeEach(() => {
  window.localStorage.clear()
  __resetSuggestionsGenerationForTest()
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe('HubSuggestions personalized feed', () => {
  it('renders a cached personalized question in the second chip', () => {
    window.localStorage.setItem(
      'homePersonalizedSuggestions.v1.uid-1',
      JSON.stringify({ questions: ['Ask Sam about the launch?'], dayStamp: '2000-01-01' })
    )
    render(<HubSuggestions onPick={() => {}} />)
    expect(screen.getByText('What should I do today?')).toBeTruthy()
    expect(screen.getByText('Ask Sam about the launch?')).toBeTruthy()
  })

  it('falls back to the static pair when nothing is cached', () => {
    render(<HubSuggestions onPick={() => {}} />)
    expect(screen.getByText('What did I spend my time on this week?')).toBeTruthy()
    expect(screen.getByText("What's the highest-leverage thing I can do next?")).toBeTruthy()
  })
})

describe('HubChatPanel empty-state extra', () => {
  it('hosts the extra only while the thread is empty and idle', () => {
    const { rerender } = render(
      <HubChatPanel
        messages={[]}
        sending={false}
        onDismiss={() => {}}
        emptyStateExtra={<div data-testid="extra" />}
      >
        <div />
      </HubChatPanel>
    )
    expect(screen.getByTestId('extra')).toBeTruthy()
    rerender(
      <HubChatPanel
        messages={[{ id: 'm1' } as never]}
        sending={false}
        onDismiss={() => {}}
        emptyStateExtra={<div data-testid="extra" />}
      >
        <div />
      </HubChatPanel>
    )
    expect(screen.queryByTestId('extra')).toBeNull()
    expect(screen.getByTestId('messages')).toBeTruthy()
  })
})
