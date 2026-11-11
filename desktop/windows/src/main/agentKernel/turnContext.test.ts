// SCA-358: surfaces other than main_chat had no clock anywhere in their turn
// context, yet their agents resolve relative dates ("schedule it for Friday",
// create_action_item due_at) against tool timestamps. main_chat applies
// currentTimePrompt upstream in mainChat.ts, so the kernel-side block must skip
// that surface to avoid doubling. Hermetic: no store or services are reached
// with a null conversationId and a non-completion user text.
import { describe, expect, it } from 'vitest'

import { assembleTurnContext } from './turnContext'
import type { AssembleTurnContextInput } from './turnContext'

function input(surfaceKind: string, overrides: Partial<AssembleTurnContextInput> = {}) {
  return {
    store: {} as AssembleTurnContextInput['store'],
    services: {
      routeDesktopIntent: () => ({ intent: 'unknown', sessionId: null, runId: null, dispatchId: null, explanation: '' }),
      listSessions: () => []
    } as unknown as AssembleTurnContextInput['services'],
    ownerId: 'owner',
    sessionId: 'session',
    conversationId: null,
    surfaceRef: { surfaceKind, externalRefKind: 'chat', externalRefId: 'chat-1' },
    userText: 'Schedule the design review for Friday',
    imagePresent: false,
    bindingCarriesNativeHistory: false,
    nowMs: Date.parse('2026-08-25T12:00:00Z'),
    ...overrides
  }
}

describe('turn-context current time (SCA-358)', () => {
  it('carries the current-time block for non-main-chat surfaces', () => {
    const assembled = assembleTurnContext(input('floating_chat'))

    // Local rendering varies by runner timezone; the anchor is the block header
    // plus the full ISO date. 12:00Z keeps the calendar day on 2026-08-25 for
    // every zone from UTC-11 to UTC+11.
    expect(assembled.prompt).toMatch(/# Current Time\n2026-08-25T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2} \(.+\)/)
    expect(assembled.prompt).toContain('# User Message\n\nSchedule the design review for Friday')
  })

  it('does not double the clock on main_chat, which wraps upstream', () => {
    const assembled = assembleTurnContext(input('main_chat'))

    expect(assembled.prompt).not.toContain('# Current Time')
    expect(assembled.prompt).toContain('# User Message')
  })

  it('uses the injected clock, not Date.now()', () => {
    const assembled = assembleTurnContext(input('task_chat', { nowMs: Date.parse('2020-01-07T12:00:00Z') }))

    expect(assembled.prompt).toMatch(/# Current Time\n2020-01-07T/)
  })
})
