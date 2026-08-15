// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach } from 'vitest'
import {
  DISMISS_SUPPRESSION_MS,
  LATER_SUPPRESSION_MS,
  MAX_VISIBLE_SUGGESTED,
  acceptSuggestedCandidate,
  isSuppressed,
  loadSuggestedCandidates,
  projectCandidate,
  rejectSuggestedCandidate,
  suppressCandidate,
  type SuggestedCandidate
} from './suggestedTasks'

vi.mock('./apiClient', () => ({ omiApi: { get: vi.fn(), post: vi.fn() } }))
vi.mock('./persistentCache', () => ({ getCacheUid: () => 'uid-1' }))

const wire = (over: Record<string, unknown> = {}): Record<string, unknown> => ({
  candidate_id: 'c-1',
  status: 'pending',
  subject_kind: 'task',
  proposed_action: 'create',
  task_change: { description: 'Follow up with the vendor' },
  ...over
})

const card = (over: Partial<SuggestedCandidate> = {}): SuggestedCandidate => ({
  id: 'c-1',
  title: 'Follow up with the vendor',
  detail: null,
  accountGeneration: 3,
  ...over
})

const controlOk = { data: { workflow_mode: 'read', account_generation: 3 } }

beforeEach(() => {
  window.localStorage.clear()
})

describe('projectCandidate', () => {
  it('projects a pending create-task candidate with its description as the title', () => {
    expect(projectCandidate(wire() as never)).toEqual({
      id: 'c-1',
      title: 'Follow up with the vendor',
      detail: null
    })
  })

  it('rejects non-pending, non-task, non-create, and blank-title records', () => {
    expect(projectCandidate(wire({ status: 'accepted' }) as never)).toBeNull()
    expect(projectCandidate(wire({ subject_kind: 'workstream' }) as never)).toBeNull()
    expect(projectCandidate(wire({ proposed_action: 'update' }) as never)).toBeNull()
    expect(projectCandidate(wire({ task_change: { description: '  ' } }) as never)).toBeNull()
    expect(projectCandidate(wire({ candidate_id: undefined }) as never)).toBeNull()
  })

  it('carries a trimmed context summary as the detail line', () => {
    const p = projectCandidate(
      wire({ task_change: { description: 'T', context_summary: ' seen in Slack ' } }) as never
    )
    expect(p?.detail).toBe('seen in Slack')
  })
})

describe('suppressions', () => {
  it('suppresses for the given window and expires after it', () => {
    const t0 = 1_000_000
    suppressCandidate('c-9', LATER_SUPPRESSION_MS, t0)
    expect(isSuppressed('c-9', t0 + LATER_SUPPRESSION_MS - 1)).toBe(true)
    expect(isSuppressed('c-9', t0 + LATER_SUPPRESSION_MS + 1)).toBe(false)
  })
})

describe('loadSuggestedCandidates', () => {
  it('returns an empty rail when the workflow is not in read mode', async () => {
    const get = vi
      .fn()
      .mockResolvedValue({ data: { workflow_mode: 'shadow', account_generation: 2 } })
    const result = await loadSuggestedCandidates({ get })
    expect(result).toEqual({ candidates: [], accountGeneration: 2 })
    expect(get).toHaveBeenCalledTimes(1)
  })

  it('lists pending suggested candidates and stamps the account generation', async () => {
    const get = vi
      .fn()
      .mockResolvedValueOnce(controlOk)
      .mockResolvedValueOnce({ data: { candidates: [wire(), wire({ candidate_id: 'c-2' })] } })
    const result = await loadSuggestedCandidates({ get })
    expect(get).toHaveBeenCalledWith('/v1/candidates', {
      params: { status: 'pending', limit: 100, offset: 0, surface: 'suggested' }
    })
    expect(result.candidates.map((c) => c.id)).toEqual(['c-1', 'c-2'])
    expect(result.candidates[0].accountGeneration).toBe(3)
  })

  it('treats a 404 list as empty, not an error', async () => {
    const get = vi
      .fn()
      .mockResolvedValueOnce(controlOk)
      .mockRejectedValueOnce({ response: { status: 404 } })
    const result = await loadSuggestedCandidates({ get })
    expect(result.candidates).toEqual([])
  })

  it('propagates non-404 list failures', async () => {
    const get = vi
      .fn()
      .mockResolvedValueOnce(controlOk)
      .mockRejectedValueOnce({ response: { status: 500 } })
    await expect(loadSuggestedCandidates({ get })).rejects.toBeTruthy()
  })

  it('filters suppressed candidates and caps the rail', async () => {
    suppressCandidate('c-0', DISMISS_SUPPRESSION_MS, Date.now())
    const records = Array.from({ length: MAX_VISIBLE_SUGGESTED + 3 }, (_, i) =>
      wire({ candidate_id: `c-${i}` })
    )
    const get = vi
      .fn()
      .mockResolvedValueOnce(controlOk)
      .mockResolvedValueOnce({ data: { candidates: records } })
    const result = await loadSuggestedCandidates({ get })
    expect(result.candidates).toHaveLength(MAX_VISIBLE_SUGGESTED)
    expect(result.candidates.some((c) => c.id === 'c-0')).toBe(false)
  })
})

describe('accept / reject', () => {
  it('accept posts with the account generation header and returns the task id', async () => {
    const post = vi
      .fn()
      .mockResolvedValueOnce({ data: { task_id: 't-7' } })
      .mockResolvedValue({ data: {} })
    const result = await acceptSuggestedCandidate(card(), { post })
    expect(post).toHaveBeenCalledWith(
      '/v1/candidates/c-1/accept',
      {},
      { headers: { 'X-Account-Generation': 3 } }
    )
    expect(result.taskId).toBe('t-7')
    // Attribution rides behind with the generated FeedbackCreate wire shape and
    // both required headers.
    expect(post).toHaveBeenCalledWith(
      '/v1/task-intelligence/feedback',
      { action: 'accept_candidate', subject_id: 'c-1', subject_kind: 'candidate' },
      {
        headers: {
          'Idempotency-Key': 'suggested:c-1:accept_candidate',
          'X-Account-Generation': 3
        }
      }
    )
  })

  it('reject posts the resolution and persists the 30-day suppression', async () => {
    const post = vi.fn().mockResolvedValue({ data: {} })
    const t0 = 5_000_000
    await rejectSuggestedCandidate(card(), { post, now: () => t0 })
    expect(post).toHaveBeenCalledWith(
      '/v1/candidates/c-1/reject',
      { reason: null },
      { headers: { 'X-Account-Generation': 3 } }
    )
    expect(isSuppressed('c-1', t0 + DISMISS_SUPPRESSION_MS - 1)).toBe(true)
  })

  it('a failed reject does not suppress (the card is restorable)', async () => {
    const post = vi.fn().mockRejectedValue(new Error('down'))
    await expect(rejectSuggestedCandidate(card(), { post })).rejects.toThrow('down')
    expect(isSuppressed('c-1')).toBe(false)
  })

  it('a failed feedback post never fails the accept', async () => {
    const post = vi
      .fn()
      .mockResolvedValueOnce({ data: { task_id: 't-1' } })
      .mockRejectedValueOnce(new Error('telemetry down'))
    const result = await acceptSuggestedCandidate(card(), { post })
    expect(result.taskId).toBe('t-1')
  })
})
