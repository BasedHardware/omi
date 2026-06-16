// Synthesize upcoming Calendar events into actionable tasks. Reuses the
// memoryExtract transport + extractJSONObject helper. parseCalendarTasks is
// split out (pure) so the JSON handling is unit-tested without the network.
import { desktopApi } from './apiClient'
import { extractJSONObject } from './memoryExtract'
import type { CalendarItem } from '../../../shared/types'

const SYNTHESIS_MODEL = 'claude-haiku-4-5-20251001'
const SYSTEM_PROMPT =
  'You convert upcoming calendar events into concise actionable to-do items. Output only valid JSON.'

export type SynthesizedTask = { description: string; dueAt?: string }

export function buildCalendarPrompt(items: CalendarItem[]): string {
  const lines = [
    'These are the user’s upcoming calendar events. For events that imply something the user should DO or PREPARE, produce a short actionable task. Skip purely passive/informational events (e.g. "Lunch", "Day off") that need no preparation.',
    '',
    'EVENTS:'
  ]
  for (const it of items.slice(0, 50)) {
    const start = it.startMs ? new Date(it.startMs).toISOString() : 'unknown'
    const loc = it.location ? ` @ ${it.location}` : ''
    lines.push(`- ${it.title}${loc} | starts ${start} | id=${it.id}`)
  }
  lines.push(
    '',
    'Respond ONLY with valid JSON (no markdown, no code fences):',
    '{ "tasks": [ { "description": "actionable task", "dueAt": "ISO-8601 or omit" } ] }',
    '',
    'RULES:',
    '- description: imperative and specific (e.g. "Prepare slides for the Q3 review").',
    '- dueAt: the event start time in ISO-8601 when a deadline is implied; omit if none.',
    '- At most one task per event; skip events that need no action.',
    '- Do not invent events or details not present above.'
  )
  return lines.join('\n')
}

/** Parse the model's JSON into tasks. Pure: tolerates fences, drops blanks. */
export function parseCalendarTasks(content: string): SynthesizedTask[] {
  let parsed: { tasks?: unknown }
  try {
    parsed = JSON.parse(extractJSONObject(content)) as { tasks?: unknown }
  } catch {
    return []
  }
  if (!Array.isArray(parsed.tasks)) return []
  const out: SynthesizedTask[] = []
  for (const t of parsed.tasks) {
    if (typeof t !== 'object' || t === null) continue
    const desc = (t as { description?: unknown }).description
    if (typeof desc !== 'string' || !desc.trim()) continue
    const dueAt = (t as { dueAt?: unknown }).dueAt
    out.push({
      description: desc.trim(),
      dueAt: typeof dueAt === 'string' && dueAt.trim() ? dueAt.trim() : undefined
    })
  }
  return out
}

export async function extractCalendarTasks(items: CalendarItem[]): Promise<SynthesizedTask[]> {
  if (items.length === 0) return []
  const res = await desktopApi.post(
    '/v2/chat/completions',
    {
      model: SYNTHESIS_MODEL,
      stream: false,
      messages: [
        { role: 'system', content: SYSTEM_PROMPT },
        { role: 'user', content: buildCalendarPrompt(items) }
      ]
    },
    { timeout: 60_000 }
  )
  const content: string =
    (res.data as { choices?: { message?: { content?: string } }[] })?.choices?.[0]?.message
      ?.content ?? ''
  return parseCalendarTasks(content)
}
