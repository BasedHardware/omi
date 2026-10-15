// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { CurrentPlanCard } from './CurrentPlanCard'
import type { UserSubscriptionResponse } from '../../../lib/omiApi.generated'

afterEach(cleanup)

describe('CurrentPlanCard provider-scoped BYOK', () => {
  it.each([
    ['plan_within_allowance', 'Transcription: Omi plan allowance'],
    ['plan_allowance_exhausted', 'Transcription: Omi plan allowance'],
    ['byok', 'Transcription: Deepgram BYOK'],
    ['allowance_unavailable', 'Transcription allowance unavailable — refresh to check'],
    ['usage_invalid', 'Transcription allowance unavailable — refresh to check'],
    [undefined, 'Transcription allowance unavailable — refresh to check']
  ])('shows the server transcription allowance for %s', (reason, expected) => {
    const sub: UserSubscriptionResponse = {
      subscription: { plan: 'unlimited', status: 'active', features: ['byok'] },
      available_plans: [],
      insights_gained_limit: 0,
      insights_gained_used: 0,
      transcription_seconds_limit: reason === 'byok' ? 0 : 1800,
      transcription_seconds_used: reason === 'plan_allowance_exhausted' ? 1800 : 0,
      words_transcribed_limit: 0,
      words_transcribed_used: 0,
      transcription_allowance: reason
        ? {
            mode: reason === 'plan_allowance_exhausted' ? 'on_device' : 'managed',
            remaining_seconds:
              reason === 'byok' ? null : reason === 'plan_allowance_exhausted' ? 0 : 600,
            reason
          }
        : undefined
    }
    render(
      <CurrentPlanCard
        sub={sub}
        portalBusy={false}
        refreshing={false}
        onManage={vi.fn()}
        onRefresh={vi.fn()}
      />
    )

    expect(
      screen.getByText('Chat and AI: BYOK supported — configure keys in Developer settings')
    ).not.toBeNull()
    expect(screen.queryByText('Chat and AI: BYOK keys active')).toBeNull()
    expect(screen.getByText(expected)).not.toBeNull()
  })
})
