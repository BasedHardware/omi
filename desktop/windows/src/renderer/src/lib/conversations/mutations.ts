// Cloud-conversation mutations for the Conversations list: star, move-to-folder,
// and merge. All target the backend by conversation id (the authoritative store);
// callers apply optimistic UI updates and revert on rejection. Only cloud-backed
// rows may be passed here — local-only/chat rows have no backend id (see
// isCloudBacked in filtering.ts).

import { omiApi } from '../apiClient'
import type { MergeConversationsResponse } from '../omiApi.generated'

/** Toggle a conversation's starred flag. Backend contract: starred is a QUERY
 *  param on a bodyless PATCH (not a JSON body). */
export async function setConversationStarred(id: string, starred: boolean): Promise<void> {
  await omiApi.patch(`/v1/conversations/${id}/starred`, null, { params: { starred } })
}

/** Assign a conversation to a folder (or unfile it with null). Backend contract:
 *  folder_id is a JSON BODY ({folder_id}), unlike starred. */
export async function moveConversationToFolder(id: string, folderId: string | null): Promise<void> {
  await omiApi.patch(`/v1/conversations/${id}/folder`, { folder_id: folderId })
}

/** Rename a cloud conversation. Backend contract: title is a QUERY param on a
 *  bodyless PATCH (same shape as starred). Local rows rename via
 *  window.omi.updateLocalConversationTitle instead. */
export async function setConversationTitle(id: string, title: string): Promise<void> {
  await omiApi.patch(`/v1/conversations/${id}/title`, null, { params: { title } })
}

/** Mac's "Copy link" (APIClient.getConversationShareLink): flip the conversation
 *  to "shared" visibility, then hand back the public web URL.
 *
 *  Backend contract: `value` is a required QUERY param
 *  (backend/routers/conversations.py::set_conversation_visibility). Mac also
 *  sends a redundant `visibility=` param that the backend never binds — not
 *  ported. */
export async function getConversationShareLink(id: string): Promise<string> {
  await omiApi.patch(`/v1/conversations/${id}/visibility`, null, {
    params: { value: 'shared' }
  })
  return `https://h.omi.me/conversations/${id}`
}

/** Re-run Omi's summarization. `appId` targets a specific app (Mac's App Insights
 *  "Reprocess" picker); omitted, it regenerates the default summary. Both params
 *  are query params. */
export async function reprocessConversation(id: string, appId?: string): Promise<void> {
  await omiApi.post(`/v1/conversations/${id}/reprocess`, null, {
    params: appId ? { app_id: appId } : {}
  })
}

/** Merge ≥2 conversations into one. FIRE-AND-FORGET: the backend returns
 *  {status:'merging', conversation_ids} and does NOT return the new conversation's
 *  id — the caller must refetch the list to see the result. */
export async function mergeConversations(ids: string[]): Promise<MergeConversationsResponse> {
  const r = await omiApi.post<MergeConversationsResponse>('/v1/conversations/merge', {
    conversation_ids: ids,
    reprocess: true
  })
  return r.data
}
