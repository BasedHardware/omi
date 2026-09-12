// Personalized home ask-bar suggestions (mac parity: HomeSuggestionsStore +
// HomeSuggestionComposer). The visible chips are LLM-generated from the
// account's own context at most once per owner per local day, cached under
// homePersonalizedSuggestions.v1.<owner>, and composed with the fixed lead chip
// and the static fallbacks. The hub's old static prompt list asked for exactly
// this: "swap them for the feed the day one exists".
//
// Context classification, ported from mac: every source read is individually
// fault-isolated so nil (failed) is distinguishable from empty. All-empty with
// any failure = UNAVAILABLE (the daily generation slot is NOT burned; retry on
// the next visit). All-empty with every read succeeding = THIN (an empty list
// IS cached; there is nothing to personalize today). Otherwise generate.
import { omiApi } from '../apiClient'
import { callAgentLLM } from '../agentLLM'
import { fetchAllActionItems } from '../actionItems'
import { getCacheUid } from '../persistentCache'

export const LEAD_SUGGESTION = 'What should I do today?'

export const STATIC_FALLBACK_SUGGESTIONS = [
  'What did I spend my time on this week?',
  "What's the highest-leverage thing I can do next?"
]

// Questions so universal they add nothing personalized (mac's universal set);
// compared case-insensitively after trimming.
const UNIVERSAL_SUGGESTIONS = new Set([
  'what should i do today?',
  'what should i focus on today to achieve my goals?'
])

const MAX_PERSONALIZED_LENGTH = 72
const CACHE_KEY_PREFIX = 'homePersonalizedSuggestions.v1.'

/** Trim, drop empties and over-length lines, dedupe case-insensitively, and
 *  drop the universal questions. Order-preserving. */
export function sanitizeSuggestions(questions: string[]): string[] {
  const seen = new Set<string>()
  const out: string[] = []
  for (const raw of questions) {
    const trimmed = raw.trim()
    if (!trimmed || trimmed.length > MAX_PERSONALIZED_LENGTH) continue
    const key = trimmed.toLowerCase()
    if (seen.has(key) || UNIVERSAL_SUGGESTIONS.has(key)) continue
    seen.add(key)
    out.push(trimmed)
  }
  return out
}

/** Chip one is always the lead question; the remaining two come from the
 *  personalized set padded by the static fallbacks (mac's composer). */
export function composeSuggestions(personalized: string[]): string[] {
  return [
    LEAD_SUGGESTION,
    ...sanitizeSuggestions([...personalized, ...STATIC_FALLBACK_SUGGESTIONS]).slice(0, 2)
  ]
}

export function suggestionsOwnerId(): string {
  return getCacheUid() ?? 'signed-out'
}

/** Local calendar day stamp; one generation per owner per local day. */
export function suggestionsDayStamp(now: Date = new Date()): string {
  const pad = (n: number): string => String(n).padStart(2, '0')
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`
}

type SuggestionsCache = { questions: string[]; dayStamp: string }

export function readSuggestionsCache(ownerId: string): SuggestionsCache | null {
  try {
    const raw = window.localStorage.getItem(`${CACHE_KEY_PREFIX}${ownerId}`)
    if (!raw) return null
    const parsed = JSON.parse(raw) as Partial<SuggestionsCache> | null
    if (!parsed || !Array.isArray(parsed.questions) || typeof parsed.dayStamp !== 'string')
      return null
    return {
      questions: parsed.questions.filter((q): q is string => typeof q === 'string'),
      dayStamp: parsed.dayStamp
    }
  } catch {
    return null
  }
}

function writeSuggestionsCache(ownerId: string, cache: SuggestionsCache): void {
  try {
    window.localStorage.setItem(`${CACHE_KEY_PREFIX}${ownerId}`, JSON.stringify(cache))
  } catch {
    // Quota failure degrades to regenerating tomorrow.
  }
}

type ContextSample = {
  memories: number | null
  conversations: number | null
  actionItems: number | null
  goals: number | null
}

export type ContextClass = 'unavailable' | 'thin' | 'available'

/** All-empty + any failed read = unavailable; all-empty + all reads succeeded =
 *  thin; anything else = available (mac's classification, verbatim). */
export function classifyContext(sample: ContextSample): ContextClass {
  const counts = [sample.memories, sample.conversations, sample.actionItems, sample.goals]
  const allEmpty = counts.every((c) => c === null || c === 0)
  if (allEmpty && counts.some((c) => c === null)) return 'unavailable'
  if (allEmpty) return 'thin'
  return 'available'
}

type SampleWithText = ContextSample & {
  memoryLines: string[]
  conversationTitles: string[]
  taskLines: string[]
  goalTitles: string[]
}

async function readContext(deps: Deps): Promise<SampleWithText> {
  const sample: SampleWithText = {
    memories: null,
    conversations: null,
    actionItems: null,
    goals: null,
    memoryLines: [],
    conversationTitles: [],
    taskLines: [],
    goalTitles: []
  }
  try {
    const res = await deps.get('/v3/memories', { params: { limit: 200, offset: 0 } })
    const rows = Array.isArray(res.data) ? res.data : []
    sample.memories = rows.length
    sample.memoryLines = rows
      .map((m) => (m as { content?: unknown }).content)
      .filter((c): c is string => typeof c === 'string')
      .slice(0, 40)
  } catch {
    sample.memories = null
  }
  try {
    const res = await deps.get('/v1/conversations', {
      params: { limit: 30, statuses: 'completed' }
    })
    const rows = Array.isArray(res.data) ? res.data : []
    sample.conversations = rows.length
    sample.conversationTitles = rows
      .map((c) => {
        const structured = (c as { structured?: { title?: unknown } }).structured
        return structured && typeof structured.title === 'string' ? structured.title : null
      })
      .filter((t): t is string => t !== null)
      .slice(0, 20)
  } catch {
    sample.conversations = null
  }
  try {
    const items = await deps.fetchActionItems()
    const open = items.filter((t) => !t.completed).slice(0, 50)
    sample.actionItems = open.length
    sample.taskLines = open.map((t) => t.description).slice(0, 25)
  } catch {
    sample.actionItems = null
  }
  try {
    const res = await deps.get('/v1/goals/all')
    const data = res.data as unknown
    const rows = Array.isArray(data) ? data : ((data as { goals?: unknown[] })?.goals ?? [])
    sample.goals = rows.length
    sample.goalTitles = rows
      .map((g) => (g as { title?: unknown }).title)
      .filter((t): t is string => typeof t === 'string')
      .slice(0, 10)
  } catch {
    sample.goals = null
  }
  return sample
}

/** Mac's generation rules, carried into the prompt: at most 48 characters per
 *  question, first person, each must name something concrete from the context,
 *  no generic productivity questions, empty list when the context is thin. */
function generationPrompt(sample: SampleWithText): string {
  const section = (title: string, lines: string[]): string =>
    lines.length > 0 ? `${title}:\n${lines.map((l) => `- ${l}`).join('\n')}\n` : ''
  return (
    'You compose ask-bar suggestions for a personal AI. From the context below, ' +
    'write up to 3 questions the user would plausibly ask their AI right now.\n' +
    'Rules: each question is at most 48 characters, first person, and must name ' +
    'something concrete from the context (a task, goal, person, or topic). No ' +
    'generic productivity questions. If the context is too thin, return an empty ' +
    'list.\n' +
    'Respond with ONLY a JSON object: {"questions": ["..."]}\n\n' +
    section('Open tasks', sample.taskLines) +
    section('Goals', sample.goalTitles) +
    section('Recent conversations', sample.conversationTitles) +
    section('Memories', sample.memoryLines.slice(0, 20))
  )
}

/** Tolerant parse: the reply should be bare JSON, but a chat-tuned fallback lane
 *  may wrap it in prose, so take the first {...} block. */
export function parseGeneratedSuggestions(reply: string): string[] {
  const start = reply.indexOf('{')
  const end = reply.lastIndexOf('}')
  if (start === -1 || end <= start) return []
  try {
    const parsed = JSON.parse(reply.slice(start, end + 1)) as { questions?: unknown }
    if (!Array.isArray(parsed.questions)) return []
    return parsed.questions.filter((q): q is string => typeof q === 'string')
  } catch {
    return []
  }
}

type Deps = {
  get: typeof omiApi.get
  fetchActionItems: typeof fetchAllActionItems
  generate: (prompt: string) => Promise<string>
  now: () => Date
  ownerId: () => string
}

function defaultDeps(): Deps {
  return {
    get: omiApi.get.bind(omiApi),
    fetchActionItems: fetchAllActionItems,
    generate: callAgentLLM,
    now: () => new Date(),
    ownerId: suggestionsOwnerId
  }
}

// Per-owner in-flight refreshes: concurrent callers for the SAME owner share
// one promise (so the second Home surface receives the generated result rather
// than an empty fallback), and one owner's generation never starves another's.
const inflightByOwner = new Map<string, Promise<string[]>>()

/** Test seam: the single-flight table is module state. */
export function __resetSuggestionsGenerationForTest(): void {
  inflightByOwner.clear()
}

/** Return today's personalized questions for the owner, generating at most once
 *  per local day. Publishes the cache immediately when fresh; an UNAVAILABLE
 *  context never burns the daily slot; a generation that finishes after an
 *  owner switch is dropped rather than cached under the wrong account. */
export async function refreshHomeSuggestions(depsOverride: Partial<Deps> = {}): Promise<string[]> {
  const deps = { ...defaultDeps(), ...depsOverride }
  const owner = deps.ownerId()
  const today = suggestionsDayStamp(deps.now())
  const cached = readSuggestionsCache(owner)
  if (cached && cached.dayStamp === today) return cached.questions
  const existing = inflightByOwner.get(owner)
  if (existing) return existing
  const run = (async (): Promise<string[]> => {
    try {
      const sample = await readContext(deps)
      if (deps.ownerId() !== owner) {
        // Account switched while reading context: the sample belongs to the
        // previous owner and must never reach the generator.
        return []
      }
      const classification = classifyContext(sample)
      if (classification === 'unavailable') return cached?.questions ?? []
      let questions: string[] = []
      if (classification === 'available') {
        const reply = await deps.generate(generationPrompt(sample))
        questions = sanitizeSuggestions(parseGeneratedSuggestions(reply)).slice(0, 2)
      }
      if (deps.ownerId() !== owner) {
        // Account switched mid-generation: drop the result (mac parity).
        return []
      }
      writeSuggestionsCache(owner, { questions, dayStamp: today })
      return questions
    } catch {
      // Transport failure: cache untouched, retried on the next visit.
      return cached?.questions ?? []
    } finally {
      inflightByOwner.delete(owner)
    }
  })()
  inflightByOwner.set(owner, run)
  return run
}
