// Which assistant lane may burn the Vertex PT Flash reservation — a ratchet.
//
// Company-paid `gemini-2.5-flash` in us-central1 burns a saturated, prepaid
// Provisioned Throughput reservation (13,450 tok/s) that is kept for task
// extraction — the one lane Flash-Lite measurably fails (sidebar false-extraction
// at confidence 0.9; silently dropped second commitment). Everything else runs on
// `gemini-2.5-flash-lite`, which is `shared`/on-demand on Vertex and never
// competes with task extraction for the reservation. Evidence: omi-knowledge-base,
// vertex-pt-flash-spend, 2026-08-17 workload value ranking + overflow bakeoff.
//
// Re-pinning a lane onto `gemini-2.5-flash` is a cost regression on a saturated
// reservation, not a free upgrade: change this test only with new lane-level
// evidence, in the same PR as the pin change.
import { describe, expect, it, vi } from 'vitest'

vi.mock('electron', () => ({ net: { fetch: vi.fn() } }))
vi.mock('../core/session', () => ({ getAbortSignal: () => undefined }))

import { TASK_MODEL, TASK_FALLBACK_MODEL } from './tasks/geminiWire'
import { MODEL as FOCUS_MODEL } from './focus/gemini'
import { MODEL as MEMORY_MODEL } from './memory/gemini'
import { MODEL as INSIGHT_MODEL, FALLBACK_MODEL as INSIGHT_FALLBACK_MODEL } from './insight/gemini'
import { geminiProxyFetch, type GeminiFetch } from '../../shared/geminiProxy'

const PT_MODEL = 'gemini-2.5-flash'
const OFF_PT_MODEL = 'gemini-2.5-flash-lite'

describe('assistant model pins vs the Vertex PT reservation', () => {
  it('task extraction keeps the reservation (nowhere cheaper to go)', () => {
    expect(TASK_MODEL).toBe(PT_MODEL)
    expect(TASK_FALLBACK_MODEL).toBe(PT_MODEL)
  })

  it('focus keeps the reservation (small payloads, best-performing lane)', () => {
    expect(FOCUS_MODEL).toBe(PT_MODEL)
  })

  it('memory extraction is evicted to Flash-Lite (worst CTR of any lane)', () => {
    expect(MEMORY_MODEL).toBe(OFF_PT_MODEL)
  })

  it('insight never lands on the PT model, fallback included', () => {
    expect(INSIGHT_MODEL).toBe(OFF_PT_MODEL)
    expect(INSIGHT_FALLBACK_MODEL).toBe(OFF_PT_MODEL)
  })
})

// Compile-time contract for the shared Gemini transport: a misspelled action,
// a missing/invalid lane, or a missing/invalid workload must not compile. This
// file is inside the node tsconfig's include roots, so `pnpm typecheck` is what
// verifies each @ts-expect-error is a real error; the body never runs.
const _compileAssertions = (): void => {
  const impl = fetch as GeminiFetch
  const base = { baseURL: 'b', model: 'm', token: 't', body: '{}', platform: 'windows' as const }
  geminiProxyFetch(impl, {
    ...base,
    // @ts-expect-error action is bounded to the backend allowlist
    action: 'generateContents',
    lane: 'focus',
    workload: 'extraction'
  })
  // @ts-expect-error lane is required — an unattributed request must not compile
  geminiProxyFetch(impl, { ...base, action: 'generateContent', workload: 'extraction' })
  // @ts-expect-error workload is required
  geminiProxyFetch(impl, { ...base, action: 'generateContent', lane: 'focus' })
  geminiProxyFetch(impl, {
    ...base,
    action: 'generateContent',
    // @ts-expect-error lane must be a generated literal
    lane: 'bogus_lane',
    workload: 'extraction'
  })
  geminiProxyFetch(impl, {
    ...base,
    action: 'generateContent',
    lane: 'focus',
    // @ts-expect-error workload must be a generated literal
    workload: 'batch'
  })
}
void _compileAssertions
