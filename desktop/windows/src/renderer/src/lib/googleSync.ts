// Orchestrate one Google sync from the renderer (it holds the Firebase token):
// pull fresh items from main → synthesize → write /v3/memories + /v1/action-items
// → markProcessed the whole fetched batch. Idempotency is the processed-ID set in
// main; this also dedups Calendar tasks against current open action-items.
import { omiApi } from './apiClient'
import { extractGmailMemories } from './gmailExtract'
import { extractCalendarTasks } from './calendarExtract'
import { normalize } from './memoryExtract'

const GMAIL_TAG = 'gmail/import/note'

export type SyncOutcome = { memoriesAdded: number; tasksAdded: number; errors: string[] }

async function syncGmail(existingMemories: string[]): Promise<{ added: number; error?: string }> {
  const res = await window.omi.googleGmailFetchNew()
  if (!res.ok) return res.error === 'not_connected' ? { added: 0 } : { added: 0, error: res.error }
  if (res.items.length === 0) return { added: 0 }

  const memories = await extractGmailMemories(res.items, existingMemories)
  let added = 0
  let writeError = ''
  for (const content of memories) {
    try {
      await omiApi.post('/v3/memories', { content, tags: [GMAIL_TAG] })
      added++
    } catch (e) {
      if (!writeError) writeError = (e as Error).message
    }
  }
  // A write failure leaves the whole batch unprocessed so the next sync retries
  // it (the existing-memory dedup prevents re-adding the ones that did succeed).
  if (writeError) return { added, error: writeError }
  await window.omi.googleMarkProcessed(
    'gmail',
    res.items.map((i) => i.id)
  )
  return { added }
}

async function openTaskDescriptions(): Promise<Set<string>> {
  try {
    const r = await omiApi.get('/v1/action-items', { params: { limit: 300, offset: 0 } })
    const data = r.data as { description?: string }[] | { action_items?: { description?: string }[] }
    const list = Array.isArray(data) ? data : (data.action_items ?? [])
    return new Set(list.map((i) => normalize(i.description ?? '')))
  } catch {
    return new Set()
  }
}

async function syncCalendar(): Promise<{ added: number; error?: string }> {
  const res = await window.omi.googleCalendarFetchNew()
  if (!res.ok) return res.error === 'not_connected' ? { added: 0 } : { added: 0, error: res.error }
  if (res.items.length === 0) return { added: 0 }

  const tasks = await extractCalendarTasks(res.items)
  const existing = await openTaskDescriptions()
  let added = 0
  let writeError = ''
  for (const t of tasks) {
    const key = normalize(t.description)
    if (!key || existing.has(key)) continue
    try {
      await omiApi.post('/v1/action-items', {
        description: t.description,
        ...(t.dueAt ? { due_at: t.dueAt } : {})
      })
      existing.add(key)
      added++
    } catch (e) {
      if (!writeError) writeError = (e as Error).message
    }
  }
  // Leave the batch unprocessed on a write failure so it retries next sync (the
  // open-task dedup prevents duplicating the ones that did succeed).
  if (writeError) return { added, error: writeError }
  await window.omi.googleMarkProcessed(
    'calendar',
    res.items.map((i) => i.id)
  )
  return { added }
}

export async function runGoogleSync(existingMemories: string[]): Promise<SyncOutcome> {
  const errors: string[] = []
  const g = await syncGmail(existingMemories)
  if (g.error) errors.push(`Gmail: ${g.error}`)
  const c = await syncCalendar()
  if (c.error) errors.push(`Calendar: ${c.error}`)
  return { memoriesAdded: g.added, tasksAdded: c.added, errors }
}
