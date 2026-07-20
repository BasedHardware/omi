import { describe, expect, it, vi } from 'vitest'
import type { AgentRuntimeEvent } from './native'

const runtime = vi.hoisted(() => ({
  listener: undefined as ((event: AgentRuntimeEvent) => void) | undefined,
  dispatch: vi.fn()
}))

runtime.dispatch.mockImplementation(async (payload: Record<string, unknown>) => {
  const requestId = payload.requestId as string | undefined
  if (payload.type === 'configure_default_execution_profile') {
    queueMicrotask(() => runtime.listener?.({ type: 'default_execution_profile_configured', requestId }))
  }
  if (payload.type === 'resolve_surface_session') {
    queueMicrotask(() => runtime.listener?.({ type: 'surface_session_resolved', requestId, sessionId: 'session-1' }))
  }
  if (payload.type === 'query') {
    queueMicrotask(() => runtime.listener?.({ type: 'text_delta', requestId, text: 'Hello' }))
    queueMicrotask(() => runtime.listener?.({ type: 'result', requestId, sessionId: 'session-1', text: 'Hello' }))
  }
})

vi.mock('./native', () => ({
  native: {
    agentRuntimeDispatch: runtime.dispatch,
    agentRuntimeRequest: vi.fn(async (payload: Record<string, unknown>) => {
      await runtime.dispatch(payload)
      if (payload.type === 'configure_default_execution_profile') {
        return { type: 'default_execution_profile_configured', requestId: payload.requestId }
      }
      return { type: 'surface_session_resolved', requestId: payload.requestId, sessionId: 'session-1' }
    }),
    onAgentRuntimeEvent: vi.fn(async (next: (event: AgentRuntimeEvent) => void) => {
      runtime.listener = next
      return () => {
        runtime.listener = undefined
      }
    })
  }
}))

import { streamAgentResponse } from './agentRuntime'

describe('streamAgentResponse', () => {
  it('configures rx4, resolves the persisted conversation, and relays deltas', async () => {
    const deltas: string[] = []
    await expect(
      streamAgentResponse({
        ownerId: 'owner-1',
        token: 'token-1',
        conversationId: 'chat-1',
        prompt: 'Hello',
        onDelta: (delta) => deltas.push(delta)
      })
    ).resolves.toBe('Hello')
    expect(deltas).toEqual(['Hello'])
    expect(runtime.dispatch.mock.calls.map(([payload]) => payload.type)).toEqual([
      'refresh_owner',
      'refresh_token',
      'configure_default_execution_profile',
      'resolve_surface_session',
      'query'
    ])
    expect(runtime.dispatch.mock.calls[2]?.[0]).toMatchObject({ adapterId: 'rx4', modelProfile: 'omi-sonnet' })
  })
})
