import { omiApi } from './apiClient'

export type CleanupStrategy =
  | 'stale_age'
  | 'overdue'
  | 'semantic_dedup'
  | 'llm_relevance'
  | 'conversation_context'
  | 'vague'

export interface CleanupPreviewParams {
  strategies: CleanupStrategy[]
  age_days?: number
  overdue_days?: number
  similarity_threshold?: number
  llm_confidence_threshold?: number
  scan_cursor?: string | null
}

export interface CleanupSampleItem {
  description: string
  strategy: string
}

export interface CleanupCandidateMeta {
  id: string
  strategy: string
  description: string
}

export interface CleanupPreviewResult {
  session_id: string
  total_candidates: number
  breakdown: Record<string, number>
  sample: CleanupSampleItem[]
  candidate_ids: string[]
  candidate_meta: CleanupCandidateMeta[]
  expires_in_seconds: number
  total_open_action_items: number
  scan_cap: number
  scan_truncated: boolean
  next_scan_cursor?: string | null
}

export interface CleanupExecuteResult {
  deleted_count: number
}

// LLM strategies over a large task set can take 60–120 seconds server-side.
const PREVIEW_TIMEOUT_MS = 180_000

export async function taskCleanupPreview(
  params: CleanupPreviewParams
): Promise<CleanupPreviewResult> {
  const r = await omiApi.post<CleanupPreviewResult>('/v1/action-items/cleanup/preview', params, {
    timeout: PREVIEW_TIMEOUT_MS
  })
  return r.data
}

export async function taskCleanupExecute(
  sessionId: string,
  excludedIds: string[] = []
): Promise<CleanupExecuteResult> {
  const r = await omiApi.post<CleanupExecuteResult>('/v1/action-items/cleanup/execute', {
    session_id: sessionId,
    excluded_ids: excludedIds
  })
  return r.data
}
