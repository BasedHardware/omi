// Synthesize Gmail metadata (Subject/From/snippet — never bodies) into durable,
// atomic memories. Reuses the memoryExtract transport + JSON/dedupe helpers; only
// the prompt is Gmail-specific. Mirrors stickyNotesExtract.ts.
import { desktopApi } from './apiClient'
import { extractJSONObject, normalize } from './memoryExtract'
import type { GmailItem } from '../../../shared/types'

const SYNTHESIS_MODEL = 'claude-haiku-4-5-20251001'
const SYSTEM_PROMPT =
  'You convert email metadata into concise durable user memories. Output only valid JSON.'

export function buildGmailPrompt(items: GmailItem[], existing: string[]): string {
  const lines = [
    'Analyze these email summaries (subject, sender, snippet only — no full bodies) and extract persistent facts about the user.',
    '',
    'EMAILS:'
  ]
  for (const it of items.slice(0, 50)) {
    lines.push(`- From: ${it.from} | Subject: ${it.subject} | ${it.snippet}`.slice(0, 500))
  }
  lines.push('')
  if (existing.length > 0) {
    lines.push(
      'EXISTING MEMORIES (do NOT repeat any fact already covered below):',
      ...existing.slice(0, 200).map((m) => `- ${m}`),
      ''
    )
  }
  lines.push(
    'Respond ONLY with valid JSON (no markdown, no code fences):',
    '{ "memories": ["clear factual statement about the user"] }',
    '',
    'RULES:',
    '- Extract durable, user-specific facts: relationships, employer, recurring services/subscriptions, projects, interests, travel, commitments grounded in the emails.',
    '- Decompose compound statements into SEPARATE atomic memories — each memory captures exactly ONE fact.',
    '- Ignore marketing/newsletters/transactional noise that says nothing durable about the user.',
    '- Do not invent facts not supported by the metadata.',
    '- CRITICAL — no duplicates: never output two memories expressing the same underlying fact. (Distinct atomic facts are NOT duplicates.)',
    '- Exclude any fact already covered by EXISTING MEMORIES.',
    '- Each memory is a single concise factual statement.'
  )
  return lines.join('\n')
}

/** Parse the model's JSON into deduped memory strings. Pure: tolerates fences
 *  and returns [] on parse failure (so one bad LLM response can't abort a sync). */
export function parseGmailMemories(content: string, existing: string[]): string[] {
  let parsed: { memories?: unknown }
  try {
    parsed = JSON.parse(extractJSONObject(content)) as { memories?: unknown }
  } catch {
    return []
  }
  const raw = Array.isArray(parsed.memories)
    ? parsed.memories.filter((m): m is string => typeof m === 'string' && m.trim().length > 0)
    : []
  const seen = new Set(existing.map(normalize))
  const out: string[] = []
  for (const m of raw) {
    const key = normalize(m)
    if (!key || seen.has(key)) continue
    seen.add(key)
    out.push(m)
  }
  return out
}

export async function extractGmailMemories(
  items: GmailItem[],
  existing: string[] = []
): Promise<string[]> {
  if (items.length === 0) return []
  const res = await desktopApi.post(
    '/v2/chat/completions',
    {
      model: SYNTHESIS_MODEL,
      stream: false,
      messages: [
        { role: 'system', content: SYSTEM_PROMPT },
        { role: 'user', content: buildGmailPrompt(items, existing) }
      ]
    },
    { timeout: 60_000 }
  )
  const content: string =
    (res.data as { choices?: { message?: { content?: string } }[] })?.choices?.[0]?.message
      ?.content ?? ''
  return parseGmailMemories(content, existing)
}
