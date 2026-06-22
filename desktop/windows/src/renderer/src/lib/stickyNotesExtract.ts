// Synthesize Windows Sticky Notes text into durable memories — the renderer half
// of parity item 3e, mirroring macOS AppleNotesReaderService. Reuses the exact
// transport used by memoryExtract.ts (desktopApi → POST /v2/chat/completions,
// the Claude "synthesis" tier) plus its JSON-parse + dedupe helpers; only the
// prompt is notes-specific.
import { desktopApi } from './apiClient'
import { extractJSONObject, normalize } from './memoryExtract'

const SYNTHESIS_MODEL = 'claude-haiku-4-5-20251001'

const SYSTEM_PROMPT =
  'You convert a person’s notes into concise durable user memories. Output only valid JSON.'

export type ExtractedMemories = { memories: string[]; profile: string }

function buildNotesPrompt(notesText: string, existing: string[]): string {
  const lines = [
    'Analyze these personal sticky notes and extract persistent facts about the user.',
    '',
    'NOTES:',
    notesText.slice(0, 40_000),
    ''
  ]

  if (existing.length > 0) {
    lines.push(
      'EXISTING MEMORIES (the user already has these — do NOT repeat any fact already covered below):',
      ...existing.slice(0, 200).map((m) => `- ${m}`),
      ''
    )
  }

  lines.push(
    'Respond ONLY with valid JSON (no markdown, no code fences):',
    '{',
    '  "memories": [',
    '    "clear factual statement about the user"',
    '  ],',
    '  "profile": "2-3 sentence summary of what these notes say about the user"',
    '}',
    '',
    'RULES:',
    '- Extract durable, user-specific facts, preferences, relationships, projects, interests, goals, and commitments grounded in the notes',
    '- Decompose compound statements into SEPARATE atomic memories — each memory captures exactly ONE fact. Example: a note saying "watched The Machinist for the first time with my girlfriend when we both lived in Bilbao" yields four memories: "The Machinist is a favorite movie", "Has a girlfriend", "Has lived in Bilbao", "Watched The Machinist with their girlfriend".',
    '- Skip transient one-off reminders that carry no lasting signal (e.g. "buy milk")',
    '- CRITICAL — no duplicates: never output two memories that express the same underlying fact. (Distinct atomic facts are NOT duplicates.)',
    '- Exclude any fact already covered by EXISTING MEMORIES, including reworded/abbreviated variants',
    '- Each memory is a single concise factual statement'
  )

  return lines.join('\n')
}

// Send the combined note text through the synthesis model and parse the result.
// Throws on transport/auth/parse failure so the caller can surface an error
// (no local fallback: notes are short and writing them verbatim pollutes memory).
export async function extractNoteMemories(
  notesText: string,
  existing: string[] = []
): Promise<ExtractedMemories> {
  const trimmed = notesText.trim()
  if (!trimmed) return { memories: [], profile: '' }

  const res = await desktopApi.post(
    '/v2/chat/completions',
    {
      model: SYNTHESIS_MODEL,
      stream: false,
      messages: [
        { role: 'system', content: SYSTEM_PROMPT },
        { role: 'user', content: buildNotesPrompt(trimmed, existing) }
      ]
    },
    { timeout: 60_000 }
  )

  const content: string =
    (res.data as { choices?: { message?: { content?: string } }[] })?.choices?.[0]?.message
      ?.content ?? ''
  const parsed = JSON.parse(extractJSONObject(content)) as {
    memories?: unknown
    profile?: unknown
  }

  const raw = Array.isArray(parsed.memories)
    ? parsed.memories.filter((m): m is string => typeof m === 'string' && m.trim().length > 0)
    : []

  const seen = new Set(existing.map(normalize))
  const memories: string[] = []
  for (const m of raw) {
    const key = normalize(m)
    if (!key || seen.has(key)) continue
    seen.add(key)
    memories.push(m)
  }

  const profile = typeof parsed.profile === 'string' ? parsed.profile : ''
  return { memories, profile }
}
