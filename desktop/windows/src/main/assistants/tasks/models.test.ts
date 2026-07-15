import { describe, expect, it } from 'vitest'
import { parseExtractTask, validateTaskTitle, wordCount, type ExtractedTask } from './models'

// A complete, valid `extract_task` args object (all 19 tool params) with a title
// that passes `validateTaskTitle` (8 words: Karthik / Q3 / Friday are proper nouns).
function fullArgs(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    title: 'Send Karthik the Q3 revenue deck by Friday',
    description: 'He asked in the standup thread',
    priority: 'high',
    tags: ['deck', 'finance'],
    source_app: 'Slack',
    inferred_deadline: '2026-07-17',
    confidence: 0.91,
    context_summary: 'Looking at a Slack DM',
    current_activity: 'Reading a message from Karthik',
    source_category: 'direct_request',
    source_subcategory: 'message',
    capture_kind: 'clear_commitment',
    owner: 'user',
    concrete_deliverable: true,
    public_broadcast: false,
    direct_mention: true,
    duplicate_of: '',
    refines_task: '',
    ownership_confidence: 0.8,
    ...overrides
  }
}

describe('parseExtractTask', () => {
  it('parses a full 19-field args object into an ExtractedTask', () => {
    const t = parseExtractTask(fullArgs()) as ExtractedTask
    expect(t).not.toBeNull()
    expect(t.title).toBe('Send Karthik the Q3 revenue deck by Friday')
    expect(t.description).toBe('He asked in the standup thread')
    expect(t.priority).toBe('high')
    expect(t.tags).toEqual(['deck', 'finance'])
    expect(t.sourceApp).toBe('Slack')
    expect(t.inferredDeadline).toBe('2026-07-17')
    expect(t.confidence).toBe(0.91)
    expect(t.sourceCategory).toBe('direct_request')
    expect(t.sourceSubcategory).toBe('message')
    expect(t.captureKind).toBe('clear_commitment')
    expect(t.owner).toBe('user')
    expect(t.concreteDeliverable).toBe(true)
    expect(t.publicBroadcast).toBe(false)
    expect(t.directMention).toBe(true)
    expect(t.duplicateOf).toBeNull() // "" collapses to null
    expect(t.refinesTask).toBeNull()
    expect(t.ownershipConfidence).toBe(0.8)
    expect(t.alreadyDone).toBe(false) // capture_kind !== "already_done"
  })

  it('returns null for a non-object args', () => {
    expect(parseExtractTask(null)).toBeNull()
    expect(parseExtractTask(undefined)).toBeNull()
    expect(parseExtractTask('nope')).toBeNull()
    expect(parseExtractTask(42)).toBeNull()
    expect(parseExtractTask(['a'])).toBeNull()
  })

  it('returns null when the title is missing (empty → validateTaskTitle rejects)', () => {
    const args = fullArgs()
    delete args['title']
    expect(parseExtractTask(args)).toBeNull()
  })

  it('returns null when the title fails validation (too short)', () => {
    expect(parseExtractTask(fullArgs({ title: 'Send the deck now' }))).toBeNull()
  })

  it('applies Mac defaults for missing priority / confidence / tags', () => {
    const t = parseExtractTask({
      title: 'Send Karthik the Q3 revenue deck by Friday'
    }) as ExtractedTask
    expect(t).not.toBeNull()
    expect(t.priority).toBe('medium')
    expect(t.confidence).toBe(0.5)
    expect(t.tags).toEqual([])
    expect(t.sourceCategory).toBe('other')
    expect(t.sourceSubcategory).toBe('other')
    expect(t.sourceApp).toBe('') // no appName in the parser — loop substitutes
    expect(t.captureKind).toBeNull()
    expect(t.owner).toBeNull()
    expect(t.concreteDeliverable).toBeNull()
    expect(t.ownershipConfidence).toBeNull()
  })

  it('coerces an invalid priority to "medium"', () => {
    expect((parseExtractTask(fullArgs({ priority: 'urgent' })) as ExtractedTask).priority).toBe(
      'medium'
    )
  })

  it('does NOT coerce a numeric-string confidence (Mac accepts Double/Int only) → 0.5', () => {
    expect((parseExtractTask(fullArgs({ confidence: '0.9' })) as ExtractedTask).confidence).toBe(
      0.5
    )
    expect((parseExtractTask(fullArgs({ confidence: 'xx' })) as ExtractedTask).confidence).toBe(0.5)
  })

  it('does NOT apply the 0.75 confidence gate — a low-confidence task still parses', () => {
    const t = parseExtractTask(fullArgs({ confidence: 0.2 })) as ExtractedTask
    expect(t).not.toBeNull()
    expect(t.confidence).toBe(0.2)
  })

  it('derives alreadyDone from capture_kind === "already_done"', () => {
    expect(
      (parseExtractTask(fullArgs({ capture_kind: 'already_done' })) as ExtractedTask).alreadyDone
    ).toBe(true)
  })

  it('collapses empty-string description / inferred_deadline / duplicate_of / refines_task to null', () => {
    const t = parseExtractTask(
      fullArgs({ description: '', inferred_deadline: '', duplicate_of: '', refines_task: '' })
    ) as ExtractedTask
    expect(t.description).toBeNull()
    expect(t.inferredDeadline).toBeNull()
    expect(t.duplicateOf).toBeNull()
    expect(t.refinesTask).toBeNull()
  })

  it('keeps only string entries in tags; a non-array tags → []', () => {
    expect(
      (parseExtractTask(fullArgs({ tags: ['ok', 3, null, 'yes'] })) as ExtractedTask).tags
    ).toEqual(['ok', 'yes'])
    expect((parseExtractTask(fullArgs({ tags: 'nope' })) as ExtractedTask).tags).toEqual([])
  })
})

describe('wordCount', () => {
  it('splits on the ASCII space and omits empty subsequences (Swift split semantics)', () => {
    expect(wordCount('a b c')).toBe(3)
    expect(wordCount('  a   b  ')).toBe(2) // runs of spaces + leading/trailing collapse
    expect(wordCount('')).toBe(0)
    expect(wordCount('one')).toBe(1)
  })
})

describe('validateTaskTitle', () => {
  it('rejects an empty or whitespace-only title', () => {
    expect(validateTaskTitle('', 0)).toBe('Title is empty')
    expect(validateTaskTitle('   ', 0)).toBe('Title is empty')
  })

  it('rejects a title under 6 words', () => {
    expect(validateTaskTitle('Send the deck now', 4)).toBe('Title too short (4 words, minimum 6)')
    expect(validateTaskTitle('Email Sarah today', 3)).toBe('Title too short (3 words, minimum 6)')
  })

  // The `wordCount < 6` gate makes the generic-pattern block unreachable via a real
  // word count (both sub-branches need count <= 4, which the short gate returns
  // first). It is ported verbatim from Mac; test the reachable `lowered === pattern`
  // branch directly by supplying count = 6 so it clears the short gate. This also
  // asserts every banned prefix string is present verbatim.
  const bannedPrefixes = [
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
  it('rejects each banned generic pattern (verbatim list)', () => {
    for (const pattern of bannedPrefixes) {
      expect(validateTaskTitle(pattern, 6)).toBe(
        `Title too generic (matches vague pattern '${pattern}')`
      )
    }
  })

  it('accepts a valid title bearing a proper noun after the verb', () => {
    expect(validateTaskTitle('Send Karthik the Q3 revenue deck by Friday', 8)).toBeNull()
    expect(validateTaskTitle('Email Sarah about the budget review tomorrow', 7)).toBeNull()
  })

  it('rejects a ≥6-word title with no proper noun after the first word', () => {
    expect(validateTaskTitle('send the revenue deck to the team lead', 8)).toBe(
      'Title lacks a specific name (person, project, or app) — no proper nouns found after the verb'
    )
    // First word capitalized but nothing after it is → still rejected (heuristic looks AFTER word 1).
    expect(validateTaskTitle('Send the report to the whole team today', 8)).toBe(
      'Title lacks a specific name (person, project, or app) — no proper nouns found after the verb'
    )
  })
})
