import { omiApi } from './apiClient'
import { fetchAllMemories, deleteMemoriesPaced } from './memoriesBulk'
import { planRetention, memoryJunkBreakdown, type SweepConvo } from './retentionRules'
import { invalidateConversationsCache } from './pageCache'
import { getPreferences } from './preferences'
import type { CloudConversation } from './conversationTypes'

const SWEEP_INTERVAL_MS = 30 * 60 * 1000
const sleep = (ms: number): Promise<void> => new Promise((r) => setTimeout(r, ms))

// Normalize local + cloud conversations into SweepConvo for the planner.
async function loadConvos(): Promise<SweepConvo[]> {
  const out: SweepConvo[] = []
  try {
    const locals = await window.omi.listLocalConversations()
    for (const c of locals) {
      out.push({ id: c.id, source: 'local', kind: c.kind, text: c.transcript ?? '' })
    }
  } catch (e) {
    console.warn('[retention] local conversations read failed:', (e as Error).message)
  }
  try {
    const r = await omiApi.get<CloudConversation[]>('/v1/conversations', {
      params: { limit: 200, offset: 0 }
    })
    const list = Array.isArray(r.data) ? r.data : []
    for (const c of list) {
      // Only completed conversations are eligible — never feed a still-`processing`
      // one to the planner (its transcript_segments may not be filled in yet).
      if (c.status !== 'completed') continue
      const text = (c.transcript_segments ?? []).map((s) => s.text).join(' ')
      out.push({ id: c.id, source: 'cloud', text })
    }
  } catch (e) {
    console.warn('[retention] cloud conversations read failed:', (e as Error).message)
  }
  return out
}

// Delete conversations paced under the rate cap (live mode only).
async function deleteConvosPaced(localIds: string[], cloudIds: string[]): Promise<number> {
  let n = 0
  for (const id of localIds) {
    try {
      await window.omi.deleteLocalConversation(id)
      n++
    } catch (e) {
      console.warn('[retention] local convo delete failed:', id, (e as Error).message)
    }
    await sleep(200)
  }
  for (const id of cloudIds) {
    try {
      await omiApi.delete(`/v1/conversations/${id}`)
      n++
    } catch (e) {
      console.warn('[retention] cloud convo delete failed:', id, (e as Error).message)
    }
    await sleep(1100) // stay under the per-hour cap
  }
  return n
}

let running = false

// One sweep pass: identify junk, then log (dry-run) or delete (live).
export async function runRetentionSweep(): Promise<void> {
  const mode = getPreferences().retentionMode ?? 'dry-run'
  if (mode === 'off' || running) return
  running = true
  try {
    const [convos, memories] = await Promise.all([loadConvos(), fetchAllMemories()])
    const plan = planRetention(convos, memories)
    const counts = {
      convos: plan.localConvoIds.length + plan.cloudConvoIds.length,
      memories: plan.memoryIds.length
    }
    if (counts.convos === 0 && counts.memories === 0) return

    if (mode === 'dry-run') {
      const memBreakdown = memoryJunkBreakdown(memories)
      // Print the actual CONTENT of (up to 25 of) the memories that would be deleted
      // INLINE as readable lines (not a nested object that collapses to "Object" in
      // DevTools), so the user can read what they are before switching to live.
      const junkSet = new Set(plan.memoryIds)
      const sampleLines = memories
        .filter((m) => junkSet.has(m.id))
        .slice(0, 25)
        .map((m, i) => `  ${i + 1}. ${(m.content ?? '(no content)').replace(/\s+/g, ' ').slice(0, 200)}`)
        .join('\n')
      console.log(
        `[retention] DRY-RUN would remove ${counts.convos} convos ` +
          `(${plan.localConvoIds.length} local, ${plan.cloudConvoIds.length} cloud), ` +
          `${counts.memories} memories — ` +
          `${memBreakdown.screenSynth} screen-synth, ${memBreakdown.appIndex} app-index, ` +
          `${memBreakdown.meta} meta, ${memBreakdown.duplicate} duplicate\n` +
          `Sample memories that would be deleted:\n${sampleLines}`
      )
      return
    }

    // mode === 'live'
    const convoN = await deleteConvosPaced(plan.localConvoIds, plan.cloudConvoIds)
    const memRes = await deleteMemoriesPaced(plan.memoryIds, () => {})
    console.log(`[retention] removed ${convoN} convos, ${memRes.deleted} memories (${memRes.failed} failed)`)
    invalidateConversationsCache()
  } catch (e) {
    console.warn('[retention] sweep failed:', (e as Error).message)
  } finally {
    running = false
  }
}

let started = false

// Start the periodic sweep once per app session (deferred past startup, then every
// 30 min). No-op when retentionMode is 'off' (re-checked each pass).
export function maybeStartRetentionSweep(): void {
  if (started) return
  started = true
  setTimeout(() => void runRetentionSweep(), 8000)
  setInterval(() => void runRetentionSweep(), SWEEP_INTERVAL_MS)
}
