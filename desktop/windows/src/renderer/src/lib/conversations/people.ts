// Account-wide People + speaker assignment. NOTE people are NOT scoped to a
// conversation — /v1/users/people is the user's whole roster, so a person named
// in one conversation is offered in every other one.

import { omiApi } from '../apiClient'
import type { BulkAssignSegmentsRequest, Conversation, Person } from '../omiApi.generated'

/** The user's full person roster (account-wide). */
export async function fetchPeople(): Promise<Person[]> {
  const r = await omiApi.get<Person[]>('/v1/users/people')
  return Array.isArray(r.data) ? r.data : []
}

/** Create (or get) a person by name. Backend: POST /v1/users/people {name}. */
export async function createPerson(name: string): Promise<Person> {
  const r = await omiApi.post<Person>('/v1/users/people', { name })
  return r.data
}

/**
 * Attribute segments to the user or to a person.
 *
 * Guard (the Mac bug this PR fixes): the server resolves segments by REAL id, so
 * an id it doesn't know silently matches nothing and the whole PATCH no-ops with
 * a 200. Callers must pass real backend segment ids only — never a synthesized
 * placeholder. An empty list is a programming error, not a no-op request, so we
 * throw instead of firing a PATCH that would do nothing.
 */
export async function assignSegmentsBulk(
  conversationId: string,
  segmentIds: string[],
  assign: { type: 'is_user' } | { type: 'person_id'; personId: string }
): Promise<void> {
  if (segmentIds.length === 0) {
    throw new Error('assignSegmentsBulk: no synced segment ids to assign')
  }
  const body: BulkAssignSegmentsRequest = {
    segment_ids: segmentIds,
    assign_type: assign.type,
    value: assign.type === 'person_id' ? assign.personId : null
  }
  await omiApi.patch<Conversation>(
    `/v1/conversations/${conversationId}/segments/assign-bulk`,
    body
  )
}
