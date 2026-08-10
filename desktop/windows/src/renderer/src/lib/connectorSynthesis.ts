// Shared transport for connector synthesis (calendar / gmail / notes).
// The prompt, the model and the output contract live in the backend behind
// POST /v1/connectors/synthesize (managed memories → OpenRouter Luna SSOT); the
// renderer only formats its own rows and reads the structured response.
import { omiApi } from './apiClient'
import { normalize } from './memoryExtract'

export type ConnectorSource = 'calendar' | 'gmail' | 'notes'

export type SynthesizedTask = { description: string; priority: string; dueAt?: string }

export type ConnectorSynthesis = { memories: string[]; tasks: SynthesizedTask[]; profile: string }

export async function synthesizeConnectorItems(
  source: ConnectorSource,
  items: string[],
  existing: string[] = []
): Promise<ConnectorSynthesis> {
  const rows = items.map((i) => i.trim()).filter((i) => i.length > 0)
  if (rows.length === 0) return { memories: [], tasks: [], profile: '' }

  const res = await omiApi.post(
    '/v1/connectors/synthesize',
    {
      source,
      items: rows.slice(0, 200).map((i) => i.slice(0, 1000)),
      existing_memories: existing.slice(0, 200)
    },
    { timeout: 60_000 }
  )

  const data = res.data as { memories?: unknown; tasks?: unknown; profile?: unknown }

  // Exact-match guard against existing memories and within-batch dupes, in case the
  // model slips one through. Semantic dedup is the backend prompt's job.
  const seen = new Set(existing.map(normalize))
  const memories: string[] = []
  if (Array.isArray(data.memories)) {
    for (const m of data.memories) {
      if (typeof m !== 'string') continue
      const key = normalize(m)
      if (!key || seen.has(key)) continue
      seen.add(key)
      memories.push(m.trim())
    }
  }

  const tasks: SynthesizedTask[] = []
  if (Array.isArray(data.tasks)) {
    for (const t of data.tasks) {
      if (typeof t !== 'object' || t === null) continue
      const description = (t as { description?: unknown }).description
      if (typeof description !== 'string' || !description.trim()) continue
      const priority = (t as { priority?: unknown }).priority
      const dueAt = (t as { due_at?: unknown }).due_at
      tasks.push({
        description: description.trim(),
        priority: typeof priority === 'string' && priority.trim() ? priority.trim() : 'medium',
        dueAt: typeof dueAt === 'string' && dueAt.trim() ? dueAt.trim() : undefined
      })
    }
  }

  const profile = typeof data.profile === 'string' ? data.profile : ''
  return { memories, tasks, profile }
}
