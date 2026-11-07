// Client-side attribution analytics for the intelligence loop (mac parity:
// TaskIntelligenceAttributionEvent, TaskModels.swift). Two events on this
// surface, exactly like mac's DashboardIntelligenceStore:
// - intervention_presented, once per intervention id per store lifetime;
// - feedback_recorded, only after the server accepted the feedback.
// candidate_id is attached only when the subject is a candidate.
import { trackEvent } from '../analytics'
import type { FeedbackAction, FeedbackReason, FeedbackSubjectKind } from './wireTypes'

export const ATTRIBUTION_EVENT = 'task_intelligence_attribution'
const SURFACE_WHAT_MATTERS_NOW = 'what_matters_now'

type AttributionBase = {
  interventionId: string
  subjectKind: FeedbackSubjectKind
  subjectId: string
}

function baseProperties(event: AttributionBase, eventType: string): Record<string, unknown> {
  return {
    schema_version: 1,
    event_id: `attr-${crypto.randomUUID()}`,
    event_type: eventType,
    source_class: 'screen',
    occurred_at: new Date().toISOString(),
    surface: SURFACE_WHAT_MATTERS_NOW,
    intervention_id: event.interventionId,
    subject_kind: event.subjectKind,
    subject_id: event.subjectId,
    ...(event.subjectKind === 'candidate' ? { candidate_id: event.subjectId } : {})
  }
}

export function emitInterventionPresented(event: AttributionBase): void {
  trackEvent(ATTRIBUTION_EVENT, baseProperties(event, 'intervention_presented'))
}

export function emitFeedbackRecorded(
  event: AttributionBase & {
    action: FeedbackAction
    reason: FeedbackReason | null
    attributionChainId: string | null
  }
): void {
  trackEvent(ATTRIBUTION_EVENT, {
    ...baseProperties(event, 'feedback_recorded'),
    feedback_action: event.action,
    ...(event.reason !== null ? { feedback_reason: event.reason } : {}),
    ...(event.attributionChainId !== null ? { attribution_chain_id: event.attributionChainId } : {})
  })
}
