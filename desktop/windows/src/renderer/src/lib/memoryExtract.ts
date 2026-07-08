// LLM-based memory-log extraction — the faithful port of the macOS desktop's
// OnboardingMemoryLogImportService. The desktop sends the pasted export to its
// AgentBridge (harness "piMono"), which authenticates a Firebase ID token
// against POST /v2/chat/completions on the Rust desktop-backend and runs the
// Claude "synthesis" model. We reproduce that transport directly: `desktopApi`
// already targets VITE_OMI_DESKTOP_API_BASE and attaches the Firebase token, so
// a single OpenAI-shaped chat/completions call gets us the same result without
// the Node agent subprocess (which only exists for tool-using chat).
import { desktopApi } from './apiClient'
import { extractJSONObject } from './extractJson'

// ModelQoS.Claude.synthesis on desktop — the cheap extraction tier used for
// calendar/gmail/notes/memory-import synthesis tasks.
const SYNTHESIS_MODEL = 'claude-haiku-4-5-20251001'

// Verbatim from the desktop's bridge.query systemPrompt.
const SYSTEM_PROMPT =
  'You convert memory-log exports into concise durable user memories. Output only valid JSON.'

export type MemorySource = 'chatgpt' | 'claude'

export type ExtractedMemories = { memories: string[]; profile: string }

const SOURCE_LABEL: Record<MemorySource, string> = {
  chatgpt: 'ChatGPT',
  claude: 'Claude'
}

// Mirrors OnboardingMemoryLogImportService.importMemoryLog's prompt, including
// the 40k-char cap on the pasted log. `existing` is the user's current memories;
// the desktop's importer is a one-time onboarding step so it never dedupes
// against prior memories, but Settings can re-run, so we pass them in and ask
// the model to skip anything already known (the only reliable way to catch
// semantic dupes like "NY" vs "New York").
function buildImportPrompt(rawText: string, source: MemorySource, existing: string[]): string {
  const lines = [
    `Analyze this exported ${SOURCE_LABEL[source]} memory log and extract persistent facts about the user.`,
    '',
    'MEMORY LOG:',
    rawText.slice(0, 40_000),
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
    '  "profile": "2-3 sentence summary of what this memory log says about the user"',
    '}',
    '',
    'RULES:',
    '- Extract 12-18 memories grounded in the provided memory log',
    '- Keep only durable, user-specific facts, preferences, relationships, projects, interests, and goals',
    '- CRITICAL — no duplicates: never output two memories that express the same underlying fact, even if worded differently or using abbreviations/aliases. Merge them into ONE entry using the most complete form. For example, "Works in NY" and "Works in New York" are the SAME fact — output only "Works in New York". Re-read your list before responding and remove any such pair.',
    '- Exclude any fact already covered by EXISTING MEMORIES, including reworded, abbreviated, or aliased variants (e.g. treat "NY" and "New York" as the same)',
    '- Exclude tool details, implementation notes, and meta-instructions',
    '- Each memory should be one concise factual statement'
  )

  return lines.join('\n')
}

// Loose normalization for the exact-match guard: lowercase, drop punctuation,
// collapse whitespace. Catches identical/near-identical strings; semantic dupes
// (NY vs New York) are handled by the prompt above, not here.
export function normalize(s: string): string {
  return s
    .toLowerCase()
    .replace(/[^\p{L}\p{N}\s]/gu, '')
    .replace(/\s+/g, ' ')
    .trim()
}

// extractJSONObject now lives in the shared ./extractJson util (imported above);
// re-export it so the integration extractors that import it from ./memoryExtract
// keep resolving after the shared-util refactor.
export { extractJSONObject } from './extractJson'

// Send the pasted export through the synthesis model and parse the JSON result.
// Throws on transport/auth/parse failure so callers can fall back to the local
// heuristic split.
export async function extractMemories(
  rawText: string,
  source: MemorySource = 'chatgpt',
  existing: string[] = []
): Promise<ExtractedMemories> {
  const trimmed = rawText.trim()
  if (!trimmed) return { memories: [], profile: '' }

  // Synthesis over up to 40k chars can exceed the default 12s client timeout.
  const res = await desktopApi.post(
    '/v2/chat/completions',
    {
      model: SYNTHESIS_MODEL,
      stream: false,
      messages: [
        { role: 'system', content: SYSTEM_PROMPT },
        { role: 'user', content: buildImportPrompt(trimmed, source, existing) }
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

  // Exact-match guard against existing memories and within-batch dupes, in case
  // the model slips one through. Semantic dedup is the prompt's job.
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
