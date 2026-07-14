import { omiApi } from './apiClient'
import type { ActionItemResponse as ActionItem, ActionItemsResponse } from './omiApi.generated'

// Page through /v1/action-items following `has_more` (Mac pages at 100) instead
// of relying on a single request with a hard cap — a hard `limit` alone silently
// truncates users with more items than the cap. `pageCap` bounds a runaway loop
// if the server ever reports `has_more: true` forever.
//
// Lives here rather than in pages/Tasks.tsx because the Hub's stat ribbon counts
// tasks off the SAME fetch: two callers, one definition of "all the user's tasks".
const TASKS_PAGE_SIZE = 100

export async function fetchAllActionItems(pageCap = 100): Promise<ActionItem[]> {
  const all: ActionItem[] = []
  let offset = 0
  for (let page = 0; page < pageCap; page++) {
    const res = await omiApi.get('/v1/action-items', {
      params: { limit: TASKS_PAGE_SIZE, offset }
    })
    const data = res.data as ActionItem[] | ActionItemsResponse
    const batch = Array.isArray(data) ? data : (data.action_items ?? [])
    all.push(...batch)
    const hasMore = Array.isArray(data) ? batch.length === TASKS_PAGE_SIZE : Boolean(data.has_more)
    if (!hasMore || batch.length === 0) break
    offset += TASKS_PAGE_SIZE
  }
  return all
}
