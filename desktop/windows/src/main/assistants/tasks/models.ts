// The TaskAssistant's parse layer: the `extract_task` tool call's args → a
// validated `ExtractedTask`, plus the `validateTaskTitle` specificity gate. Pure
// — no network, no Electron, no DB. Modeled on `insight/models.ts`
// (`parseProvideAdvice`) and ported 1:1 from Mac's `TaskAssistant.swift` /
// `TaskModels.swift`.
//
// Fidelity notes (Mac is the reference implementation):
//  - `extract_task` declares 19 tool params. Mac's `ExtractedTask` struct
//    (TaskModels.swift:407) stores 18 of them, routing `context_summary`/
//    `current_activity` to the extraction RESULT instead. On Windows the loop
//    returns `ExtractedTask[]` with NO separate per-frame result object, so the
//    two context strings are carried ON the task (they are still per-extract_task
//    tool params, one pair per call) and flow into create.ts's staged metadata.
//    `alreadyDone` is DERIVED (`capture_kind == "already_done"`), not a param.
//  - Every non-title field has a Mac default (TA:1135–1163), so the only inputs
//    that yield `null` are a non-object `args` and a title that fails
//    `validateTaskTitle` (which includes an empty/missing title → "Title is
//    empty"). The 0.75 confidence gate is NOT applied here — it runs later at
//    save time (spec §5), so a low-confidence task still parses.
//  - Word count is Swift's `title.split(separator: " ").count`, which OMITS empty
//    subsequences — replicated as split-on-space + drop-empties (collapses runs of
//    spaces; only the ASCII space is a separator, matching Swift).

/** Mac `TaskPriority` raw values (TaskModels.swift). */
export type TaskPriority = 'high' | 'medium' | 'low'

/**
 * Mac's `ExtractedTask` (TaskModels.swift:407), ported field-for-field. Optional
 * Swift types (`String?`, `Bool?`, `Double?`) → `T | null`. `alreadyDone` is a
 * concrete boolean because Mac's init always assigns `capture_kind == "already_done"`
 * (a nil `captureKind` compares false, never nil).
 */
export type ExtractedTask = {
  title: string
  description: string | null
  priority: TaskPriority
  sourceApp: string
  inferredDeadline: string | null
  confidence: number
  tags: string[]
  sourceCategory: string
  sourceSubcategory: string
  captureKind: string | null
  owner: string | null
  concreteDeliverable: boolean | null
  publicBroadcast: boolean | null
  directMention: boolean | null
  alreadyDone: boolean
  duplicateOf: string | null
  refinesTask: string | null
  ownershipConfidence: number | null
  /** The two extraction-context strings (`context_summary` / `current_activity`
   *  tool params). Mac routes these to the extraction RESULT; Windows carries them
   *  on the task so create.ts can write them into the staged row + metadata dict.
   *  Default "" when the model omits them (Mac sends ""). */
  contextSummary: string
  currentActivity: string
}

const VALID_PRIORITIES: readonly TaskPriority[] = ['high', 'medium', 'low']

/** Swift `title.split(separator: " ").count` — split on the ASCII space,
 *  omitting empty subsequences (so runs of spaces and leading/trailing spaces
 *  don't inflate the count). */
export function wordCount(title: string): number {
  return title.split(' ').filter((w) => w.length > 0).length
}

/** Mac `arguments["x"] as? String ?? "medium"` then `TaskPriority(rawValue:) ?? .medium`:
 *  a recognized priority string, else "medium". */
function parsePriority(v: unknown): TaskPriority {
  return typeof v === 'string' && (VALID_PRIORITIES as readonly string[]).includes(v)
    ? (v as TaskPriority)
    : 'medium'
}

/** Mac's task `confidence`/`ownership_confidence`: a finite Double/Int only — NO
 *  numeric-string coercion (unlike Insight). Absent/junk → the provided fallback. */
function parseNumber(v: unknown, fallback: number | null): number | null {
  return typeof v === 'number' && Number.isFinite(v) ? v : fallback
}

/** Mac `as? String` with an empty-string → nil collapse (`$0.isEmpty ? nil : $0`).
 *  Used for description/inferred_deadline/duplicate_of/refines_task. */
function nonEmptyString(v: unknown): string | null {
  return typeof v === 'string' && v.length > 0 ? v : null
}

/** Mac `as? String` (no empty collapse) — keeps "" as-is; non-string → nil. */
function optionalString(v: unknown): string | null {
  return typeof v === 'string' ? v : null
}

/** Mac `as? Bool` — a real boolean or nil. */
function optionalBool(v: unknown): boolean | null {
  return typeof v === 'boolean' ? v : null
}

/** Mac `as? [Any]` → `compactMap { $0 as? String }`, else []. */
function parseTags(v: unknown): string[] {
  return Array.isArray(v) ? v.filter((x): x is string => typeof x === 'string') : []
}

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null && !Array.isArray(v)
}

/**
 * `extract_task` args → `ExtractedTask`, or `null` when the args aren't an object
 * or the title fails `validateTaskTitle`. Every other field takes Mac's per-field
 * default (TA:1135–1163). `sourceApp` defaults to "" here (Mac defaults it to the
 * current app name, which lives in the loop, not the parser — the loop substitutes
 * when empty).
 */
export function parseExtractTask(args: unknown): ExtractedTask | null {
  if (!isRecord(args)) return null

  const title = typeof args['title'] === 'string' ? (args['title'] as string) : ''
  const words = wordCount(title)
  if (validateTaskTitle(title, words) !== null) return null

  const captureKind = optionalString(args['capture_kind'])

  return {
    title,
    description: nonEmptyString(args['description']),
    priority: parsePriority(args['priority']),
    sourceApp: typeof args['source_app'] === 'string' ? (args['source_app'] as string) : '',
    inferredDeadline: nonEmptyString(args['inferred_deadline']),
    confidence: parseNumber(args['confidence'], 0.5) as number,
    tags: parseTags(args['tags']),
    sourceCategory:
      typeof args['source_category'] === 'string' ? (args['source_category'] as string) : 'other',
    sourceSubcategory:
      typeof args['source_subcategory'] === 'string'
        ? (args['source_subcategory'] as string)
        : 'other',
    captureKind,
    owner: optionalString(args['owner']),
    concreteDeliverable: optionalBool(args['concrete_deliverable']),
    publicBroadcast: optionalBool(args['public_broadcast']),
    directMention: optionalBool(args['direct_mention']),
    alreadyDone: captureKind === 'already_done',
    duplicateOf: nonEmptyString(args['duplicate_of']),
    refinesTask: nonEmptyString(args['refines_task']),
    ownershipConfidence: parseNumber(args['ownership_confidence'], null),
    // Mac `arguments["context_summary"] as? String ?? ""` — kept as-is (no empty
    // collapse), defaulting to "" so the metadata dict always has the two keys.
    contextSummary: typeof args['context_summary'] === 'string' ? (args['context_summary'] as string) : '',
    currentActivity: typeof args['current_activity'] === 'string' ? (args['current_activity'] as string) : ''
  }
}

/** The generic verb prefixes Mac rejects when they are the whole (short) title.
 *  VERBATIM from TA:1352–1356 — order preserved. */
const GENERIC_PATTERNS: readonly string[] = [
  'investigate',
  'check logs',
  'clean up',
  'look into',
  'look through',
  'update to',
  'fix the',
  'review the',
  'check the',
  'modify the',
  'track the'
]

/**
 * Mac `validateTaskTitle` (TA:1338–1379), ported verbatim. Returns an error
 * string when the title is too vague, else `null`. `wordCount` is passed in
 * (computed by the caller on the untrimmed title, Swift-style — see `wordCount`).
 */
export function validateTaskTitle(title: string, count: number): string | null {
  const trimmed = title.trim()

  // Must not be empty
  if (trimmed.length === 0) {
    return 'Title is empty'
  }

  // Minimum 6 words
  if (count < 6) {
    return `Title too short (${count} words, minimum 6)`
  }

  // Reject titles that are purely generic verbs with no specifics
  const lowered = trimmed.toLowerCase()
  for (const pattern of GENERIC_PATTERNS) {
    // If the entire title is just a generic pattern (possibly with 1-2 filler words), reject
    if (lowered === pattern || (count <= 4 && lowered.startsWith(pattern))) {
      return `Title too generic (matches vague pattern '${pattern}')`
    }
  }

  // Must contain at least one capitalized proper noun (person, project, app name)
  // Heuristic: after the first word (verb), there should be at least one word starting with uppercase
  const words = trimmed.split(' ').filter((w) => w.length > 0)
  const hasProperNoun = words.slice(1).some((word) => /^\p{Lu}/u.test(word))
  if (!hasProperNoun) {
    return 'Title lacks a specific name (person, project, or app) — no proper nouns found after the verb'
  }

  return null
}
