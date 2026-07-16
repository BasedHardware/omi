// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { render, cleanup, waitFor, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

// C3 regression: embedded action items on a conversation never carry an `id`
// (backend's embedded ActionItem model has none — see backend/models/structured.py),
// so the toggle always fell through to a PATCH shaped like
// `{ action_item_idx, completed }`. The backend's SetConversationActionItemsStateRequest
// (backend/routers/conversations.py) requires parallel arrays `items_idx`/`values` and
// 422s on anything else — every checkbox click failed and the optimistic UI reverted.

const patchMock = vi.fn().mockResolvedValue({ data: { status: 'Ok' } })
const getMock = vi.fn()

vi.mock('../lib/apiClient', () => ({
  omiApi: {
    get: (...args: unknown[]) => getMock(...args),
    patch: (...args: unknown[]) => patchMock(...args)
  }
}))

vi.mock('../lib/pageCache', () => ({ invalidateConversationsCache: vi.fn() }))
vi.mock('../lib/toast', () => ({ toast: vi.fn() }))

import { ConversationDetail } from './ConversationDetail'

const CONVERSATION = {
  id: 'conv1',
  created_at: '2026-07-01T00:00:00Z',
  status: 'completed',
  structured: {
    title: 'Planning sync',
    overview: 'Discussed the roadmap.',
    action_items: [
      { description: 'Buy milk', completed: false },
      { description: 'Send recap', completed: false }
    ]
  },
  transcript_segments: []
}

// The embedded ActionItem model never actually sets `id` today, but the
// `item.id` branch still exists in the component — pin its contract too so a
// future change that starts returning ids doesn't silently regress it.
const CONVERSATION_WITH_ID = {
  ...CONVERSATION,
  structured: {
    ...CONVERSATION.structured,
    action_items: [{ id: 'ai_1', description: 'Buy milk', completed: false }]
  }
}

beforeEach(() => {
  patchMock.mockClear()
  getMock.mockReset()
  getMock.mockResolvedValue({ data: CONVERSATION })
})

afterEach(() => cleanup())

describe('ConversationDetail — action item toggle (C3)', () => {
  it('sends parallel items_idx/values arrays, not action_item_idx/completed', async () => {
    const { getAllByTitle } = render(
      <MemoryRouter>
        <ConversationDetail conversationId="conv1" />
      </MemoryRouter>
    )

    // Both fixture items start incomplete, so both toggles share the "Mark as
    // done" title — grab the first (index 0) explicitly.
    const toggle = await waitFor(() => getAllByTitle('Mark as done')[0])
    fireEvent.click(toggle)

    await waitFor(() => expect(patchMock).toHaveBeenCalledTimes(1))
    expect(patchMock).toHaveBeenCalledWith('/v1/conversations/conv1/action-items', {
      items_idx: [0],
      values: [true]
    })
  })

  it('toggles the second item with its own index, not always 0', async () => {
    const { getAllByTitle } = render(
      <MemoryRouter>
        <ConversationDetail conversationId="conv1" />
      </MemoryRouter>
    )

    const toggles = await waitFor(() => {
      const found = getAllByTitle('Mark as done')
      expect(found).toHaveLength(2)
      return found
    })
    fireEvent.click(toggles[1])

    await waitFor(() => expect(patchMock).toHaveBeenCalledTimes(1))
    expect(patchMock).toHaveBeenCalledWith('/v1/conversations/conv1/action-items', {
      items_idx: [1],
      values: [true]
    })
  })

  it('reverts the optimistic check mark when the PATCH fails', async () => {
    patchMock.mockRejectedValueOnce(new Error('422'))
    const { getAllByTitle, findByTitle } = render(
      <MemoryRouter>
        <ConversationDetail conversationId="conv1" />
      </MemoryRouter>
    )

    const toggle = await waitFor(() => getAllByTitle('Mark as done')[0])
    fireEvent.click(toggle)

    // Optimistic flip first ("Mark as open" = now completed)...
    await findByTitle('Mark as open')
    // ...then reverts once the rejected PATCH resolves — back to both items open.
    await waitFor(() => expect(getAllByTitle('Mark as done')).toHaveLength(2))
  })

  it('sends `completed` as a query param, not a JSON body, when the item has an id', async () => {
    getMock.mockResolvedValue({ data: CONVERSATION_WITH_ID })
    const { getByTitle } = render(
      <MemoryRouter>
        <ConversationDetail conversationId="conv1" />
      </MemoryRouter>
    )

    const toggle = await waitFor(() => getByTitle('Mark as done'))
    fireEvent.click(toggle)

    // backend/routers/action_items.py toggle_action_item_completion binds
    // `completed` as a Query(...) param — a JSON body is silently ignored and
    // the missing required query param 422s.
    await waitFor(() => expect(patchMock).toHaveBeenCalledTimes(1))
    expect(patchMock).toHaveBeenCalledWith('/v1/action-items/ai_1/completed', null, {
      params: { completed: true }
    })
  })
})

// PR-D: a failed load must never render the raw axios/Error string as the page
// body — it shows friendly copy (see detailErrors.test.ts for the mapping) and a
// retry. These pin the rendered behaviour end-to-end.
describe('ConversationDetail — error copy (PR-D)', () => {
  it('renders friendly copy, not the raw error string, when the load fails', async () => {
    getMock.mockReset()
    getMock.mockRejectedValue(new Error('Request failed with status code 500'))
    const { findByText, queryByText } = render(
      <MemoryRouter>
        <ConversationDetail conversationId="conv1" />
      </MemoryRouter>
    )

    await findByText('Couldn’t load this conversation.')
    expect(queryByText('Request failed with status code 500')).toBeNull()
  })

  it('Try again re-runs the load; a recovered fetch clears the error', async () => {
    getMock.mockReset()
    getMock
      .mockRejectedValueOnce(new Error('Request failed with status code 500'))
      .mockResolvedValue({ data: CONVERSATION })
    const { findByText, findByRole, findAllByTitle, queryByText } = render(
      <MemoryRouter>
        <ConversationDetail conversationId="conv1" />
      </MemoryRouter>
    )

    await findByText('Couldn’t load this conversation.')
    fireEvent.click(await findByRole('button', { name: /Try again/i }))

    // The conversation body renders on the recovered load (its action-item rows
    // appear), and the error clears.
    await findAllByTitle('Mark as done')
    expect(queryByText('Couldn’t load this conversation.')).toBeNull()
  })
})
