// Which assistant lane may burn the Vertex PT Flash reservation — a ratchet.
//
// Company-paid task extraction now uses the JEV admission gate and Luna through
// the desktop LLM gateway. It does not consume the Vertex Flash reservation.
import { describe, expect, it, vi } from 'vitest'

vi.mock('electron', () => ({
  net: { fetch: vi.fn() },
  app: { isPackaged: false, getVersion: () => 'test' }
}))
vi.mock('../core/session', () => ({ getAbortSignal: () => undefined }))
vi.mock('../ocr/helperProcess', () => ({ helperProcess: { ocr: vi.fn() } }))
vi.mock('./aiUserProfile/service', () => ({ getLatestProfileText: () => null }))

import { TASK_MODEL } from './tasks/screenTaskPipeline'
import { MODEL as FOCUS_MODEL } from './focus/gemini'
import { MODEL as MEMORY_MODEL } from './memory/gemini'
import { geminiProxyFetch, type GeminiFetch } from '../../shared/geminiProxy'

const OFF_PT_MODEL = 'gemini-2.5-flash-lite'
const PT_MODEL = 'gemini-2.5-flash'

describe('assistant model pins vs the Vertex PT reservation', () => {
  it('task extraction uses the mandatory gateway screen extractor alias', () => {
    expect(TASK_MODEL).toBe('gemini-3.8-flash')
  })

  it('focus keeps the reservation (small payloads, best-performing lane)', () => {
    expect(FOCUS_MODEL).toBe(PT_MODEL)
  })

  it('memory extraction is evicted to Flash-Lite (worst CTR of any lane)', () => {
    expect(MEMORY_MODEL).toBe(OFF_PT_MODEL)
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
