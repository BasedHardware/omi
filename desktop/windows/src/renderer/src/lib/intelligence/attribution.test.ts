// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { emitFeedbackRecorded, emitInterventionPresented, ATTRIBUTION_EVENT } from './attribution'

const trackEvent = vi.hoisted(() => vi.fn())
vi.mock('../analytics', () => ({ trackEvent }))

beforeEach(() => trackEvent.mockClear())

describe('attribution events', () => {
  it('intervention_presented carries the surface and attaches candidate_id only for candidates', () => {
    emitInterventionPresented({ interventionId: 'iv-1', subjectKind: 'task', subjectId: 't-1' })
    emitInterventionPresented({
      interventionId: 'iv-2',
      subjectKind: 'candidate',
      subjectId: 'c-1'
    })
    expect(trackEvent).toHaveBeenNthCalledWith(
      1,
      ATTRIBUTION_EVENT,
      expect.objectContaining({
        event_type: 'intervention_presented',
        surface: 'what_matters_now',
        subject_kind: 'task'
      })
    )
    expect(trackEvent.mock.calls[0][1]).not.toHaveProperty('candidate_id')
    expect(trackEvent.mock.calls[1][1]).toMatchObject({ candidate_id: 'c-1' })
  })

  it('feedback_recorded includes action, and reason/chain id only when present', () => {
    emitFeedbackRecorded({
      interventionId: 'iv-1',
      subjectKind: 'task',
      subjectId: 't-1',
      action: 'later',
      reason: null,
      attributionChainId: null
    })
    const props = trackEvent.mock.calls[0][1] as Record<string, unknown>
    expect(props.feedback_action).toBe('later')
    expect(props).not.toHaveProperty('feedback_reason')
    expect(props).not.toHaveProperty('attribution_chain_id')
    expect(props.event_id).toMatch(/^attr-/)
  })
})
