/**
 * Windows JIT trigger contract.
 *
 * This module is deliberately pure.  The server owns rollout authority and
 * trigger snapshots; this file only validates a bounded snapshot row and
 * evaluates caller-supplied local observations.  It never performs network
 * work, schedules a timer, or calls a model.
 */

export type JitTriState = 'enabled' | 'disabled' | 'unknown'
export type JitRuntimeMode = 'disabled' | 'enabled' | 'compatibility_rollback'

export type JitRuntimeAuthority = {
  mode: JitRuntimeMode
  killSwitchEnabled: boolean
  ownerId: string | null
  accountGeneration: number | null
  snapshotOwnerId: string | null
  snapshotAccountGeneration: number | null
  snapshotIsAuthoritative: boolean
  authorizationIsCurrent: boolean
}

export const JIT_RUNTIME_DEFAULT_AUTHORITY: JitRuntimeAuthority = {
  mode: 'disabled',
  killSwitchEnabled: false,
  ownerId: null,
  accountGeneration: null,
  snapshotOwnerId: null,
  snapshotAccountGeneration: null,
  snapshotIsAuthoritative: false,
  authorizationIsCurrent: false
}

export type JitRolloutDecision = {
  rollout: JitTriState
  killSwitch: JitTriState
  effective: JitTriState
  reason: string
  errorClass: string
}

export type JitRuntimePolicy = {
  schemaVersion: 'jit_trigger_policy.v1'
  plannedNotificationsPerTriggerPerDay: number
  totalProactiveNotificationsPerDay: number
  ambiguousNanoTriagesPerDay: number
  fullAgentTurnsPerCandidate: number
  maxCalendarEvents: number
  embedding: {
    enabled: boolean
    matchSimilarity: number
    triageSimilarity: number
    modelId: string | null
    modelVersion: string | null
    language: string | null
  }
}

export type JitTriggerAction = { type: 'agent_prompt'; prompt: string }

export type JitTriggerSnapshotRow = {
  memoryId: string
  itemRevision: number
  updatedAt: string
  triggerConditionJson: string
  action: JitTriggerAction
  wakeupBudgetPerDay: number | null
  /** Authoritative trigger-level snooze. Undefined is accepted only by local
   * unit fixtures; the wire parser always supplies null or a timezone-aware
   * ISO value. */
  snoozedUntil?: string | null
}

export type JitTriggerSnapshot = {
  ownerId: string
  accountGeneration: number
  headCommitId: string
  commitSequence: number
  snapshotRevision: string
  complete: boolean
  rows: JitTriggerSnapshotRow[]
  policy: JitRuntimePolicy
  failureReason?: string | null
}

export type JitCalendarEvent = { title: string; eventType: string }
export type JitEmbeddingObservation = {
  score: number
  modelId: string
  modelVersion: string
  language: string
  prototypeRevision: string
}

export type JitTriggerObservation = {
  eventId?: string | null
  text?: string
  entityLabels?: string[]
  appName?: string | null
  windowTitle?: string | null
  occurredAt?: Date | null
  calendarEvents?: JitCalendarEvent[]
  calendarAuthorized?: boolean
  embeddingScores?: Record<string, JitEmbeddingObservation>
}

export type JitEmbeddingContract = {
  modelId: string
  modelVersion: string
  language: string
  prototypeRevision: string
}

export type JitTriggerDecisionStatus = 'match' | 'ambiguous' | 'no_match'
export type JitTriggerDecision = {
  status: JitTriggerDecisionStatus
  reason: string
  matchedConditions: string[]
  missingConditions: string[]
  matchedFraction: number
  observationFingerprint: string
  wakeupBudgetDay: string
  wakeupsUsed: number
  wakeupBudgetPerDay: number | null
}

export type JitCompiledTrigger = {
  id: string
  revision: number
  matchMode: 'all' | 'any'
  entities: Record<string, string[]>
  ambiguousAliases: Record<string, string[]>
  keywords: string[]
  regexes: RegExp[]
  apps: string[]
  windows: string[]
  time: { weekdays: number[]; start: number; end: number; timezone: string } | null
  calendar: { eventKeywords: string[]; eventTypes: string[] } | null
  embedding: {
    prototypeId: string
    prototypeRevision: string
    modelId: string
    modelVersion: string
    language: string
    minSimilarity: number
  } | null
  action: JitTriggerAction
  wakeupBudgetPerDay: number | null
  snoozedUntil: string | null
}

export class JitTriggerCompileError extends Error {
  constructor(readonly reason: string) {
    super(reason)
    this.name = 'JitTriggerCompileError'
  }
}

const MAX_CONDITION_KEYS = 12
const MAX_TERM_CHARS = 80
const MAX_TRIGGER_ID_CHARS = 128
const MAX_PROMPT_CHARS = 2_000
const MAX_TEXT_CHARS = 8_000
const MAX_CALENDAR_EVENTS = 32
const MAX_ENTITIES = 12
const MAX_ALIASES_PER_ENTITY = 16
const MAX_KEYWORDS = 32
const MAX_REGEXES = 8
const MAX_APPS = 16
const MAX_WINDOWS = 16
const MAX_BUDGET = 1000

function normalize(value: unknown): string {
  return typeof value === 'string' ? value.trim().replace(/\s+/g, ' ').toLowerCase() : ''
}

function boundedTerm(value: unknown, max = MAX_TERM_CHARS): string {
  const normalized = normalize(value)
  if (!normalized || normalized.length > max)
    throw new JitTriggerCompileError('trigger term invalid')
  return normalized
}

function boundedString(value: unknown, max: number, reason: string): string {
  if (typeof value !== 'string') throw new JitTriggerCompileError(reason)
  const normalized = value.trim()
  if (!normalized || normalized.length > max) throw new JitTriggerCompileError(reason)
  return normalized
}

function parseSnoozedUntil(value: unknown): string | null {
  if (value === undefined || value === null) return null
  const candidate = typeof value === 'string' ? value : null
  const match =
    candidate !== null
      ? /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d{1,9})?(?:Z|[+-]\d{2}:\d{2})$/.exec(
          candidate
        )
      : null
  if (!match) throw new JitTriggerCompileError('trigger snooze malformed')
  const year = Number(match[1])
  const month = Number(match[2])
  const day = Number(match[3])
  const hour = Number(match[4])
  const minute = Number(match[5])
  const second = Number(match[6])
  if (
    month < 1 ||
    month > 12 ||
    day < 1 ||
    day > new Date(Date.UTC(year, month, 0)).getUTCDate() ||
    hour > 23 ||
    minute > 59 ||
    second > 59
  )
    throw new JitTriggerCompileError('trigger snooze malformed')
  const parsed = Date.parse(candidate as string)
  if (!Number.isFinite(parsed)) throw new JitTriggerCompileError('trigger snooze malformed')
  return candidate as string
}

function asRecord(value: unknown, reason: string): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value))
    throw new JitTriggerCompileError(reason)
  return value as Record<string, unknown>
}

function ensureKeys(record: Record<string, unknown>, allowed: readonly string[]): void {
  const known = new Set(allowed)
  for (const key of Object.keys(record)) {
    if (!known.has(key)) throw new JitTriggerCompileError(`unknown trigger key: ${key}`)
  }
}

function asArray(value: unknown, reason: string): unknown[] {
  if (!Array.isArray(value)) throw new JitTriggerCompileError(reason)
  return value
}

function normalizeTerms(value: unknown, maxItems: number, maxChars = MAX_TERM_CHARS): string[] {
  const values = asArray(value, 'trigger selector must be an array')
  if (values.length > maxItems) throw new JitTriggerCompileError('trigger selector bounds exceeded')
  return [...new Set(values.map((item) => boundedTerm(item, maxChars)))].sort()
}

/** Reject duplicate JSON object keys before JSON.parse's last-write-wins rule. */
function assertNoDuplicateKeys(json: string): void {
  // Keep the authority parser independent from JSON.parse's last-key-wins
  // behavior. The scanner below handles nested objects; this cheap guard also
  // makes the common repeated top-level key unmistakable if a future parser
  // refactor regresses the scanner.
  const topLevelKeys = [...json.matchAll(/"([^"\\]*(?:\\.[^"\\]*)*)"\s*:/g)].map(
    (match) => match[1]
  )
  if (new Set(topLevelKeys).size !== topLevelKeys.length)
    throw new JitTriggerCompileError('duplicate trigger key')
  let i = 0
  const skip = (): void => {
    while (/\s/.test(json[i] ?? '')) i++
  }
  const string = (): void => {
    if (json[i++] !== '"') throw new JitTriggerCompileError('malformed trigger JSON')
    while (i < json.length) {
      const c = json[i++]
      if (c === '\\') i++
      else if (c === '"') return
    }
    throw new JitTriggerCompileError('malformed trigger JSON')
  }
  const value = (): void => {
    skip()
    if (json[i] === '"') return string()
    if (json[i] === '{') return object()
    if (json[i] === '[') return array()
    const start = i
    while (i < json.length && !/[\s,\]}]/.test(json[i])) i++
    if (i === start) throw new JitTriggerCompileError('malformed trigger JSON')
  }
  const object = (): void => {
    i++
    skip()
    const keys = new Set<string>()
    if (json[i] === '}') return void i++
    for (;;) {
      skip()
      const start = i
      string()
      const key = JSON.parse(json.slice(start, i)) as string
      if (!keys.add(key)) throw new JitTriggerCompileError('duplicate trigger key')
      skip()
      if (json[i++] !== ':') throw new JitTriggerCompileError('malformed trigger JSON')
      value()
      skip()
      if (json[i] === '}') return void i++
      if (json[i++] !== ',') throw new JitTriggerCompileError('malformed trigger JSON')
    }
  }
  const array = (): void => {
    i++
    skip()
    if (json[i] === ']') return void i++
    for (;;) {
      value()
      skip()
      if (json[i] === ']') return void i++
      if (json[i++] !== ',') throw new JitTriggerCompileError('malformed trigger JSON')
    }
  }
  value()
  skip()
  if (i !== json.length) throw new JitTriggerCompileError('malformed trigger JSON')
}

function parseObject(json: string): Record<string, unknown> {
  if (json.length > 16_000) throw new JitTriggerCompileError('trigger condition oversized')
  assertNoDuplicateKeys(json)
  try {
    return asRecord(JSON.parse(json), 'trigger condition must be an object')
  } catch (error) {
    if (error instanceof JitTriggerCompileError) throw error
    throw new JitTriggerCompileError('malformed trigger JSON')
  }
}

function compileTime(value: unknown): JitCompiledTrigger['time'] {
  const record = asRecord(value, 'time condition malformed')
  ensureKeys(record, ['weekdays', 'start', 'end', 'timezone'])
  const weekdayValues = asArray(record.weekdays, 'time weekdays malformed')
  if (weekdayValues.length > 7) throw new JitTriggerCompileError('time weekdays bounds exceeded')
  const weekdays = [
    ...new Set(
      weekdayValues.map((day) => {
        if (typeof day !== 'number' || !Number.isInteger(day))
          throw new JitTriggerCompileError('time weekdays invalid')
        return day
      })
    )
  ].sort((a, b) => a - b)
  if (weekdays.some((day) => !Number.isInteger(day) || day < 0 || day > 6)) {
    throw new JitTriggerCompileError('time weekdays invalid')
  }
  const parseClock = (raw: unknown): number => {
    if (typeof raw !== 'string' || !/^\d{2}:\d{2}(:\d{2})?$/.test(raw)) {
      throw new JitTriggerCompileError('time clock invalid')
    }
    const [hour = 0, minute = 0, second = 0] = raw.split(':').map(Number) as number[]
    if (hour > 23 || minute > 59 || second > 59)
      throw new JitTriggerCompileError('time clock invalid')
    return hour * 3600 + minute * 60 + second
  }
  const timezone = boundedString(record.timezone ?? 'UTC', 80, 'time timezone invalid')
  try {
    new Intl.DateTimeFormat('en-US', { timeZone: timezone }).format()
  } catch {
    throw new JitTriggerCompileError('time timezone invalid')
  }
  return { weekdays, start: parseClock(record.start), end: parseClock(record.end), timezone }
}

function compileCalendar(value: unknown): JitCompiledTrigger['calendar'] {
  const record = asRecord(value, 'calendar condition malformed')
  ensureKeys(record, ['event_keywords', 'event_types'])
  const eventKeywords = normalizeTerms(record.event_keywords ?? [], MAX_KEYWORDS)
  const eventTypes = normalizeTerms(record.event_types ?? [], MAX_KEYWORDS)
  if (eventKeywords.length + eventTypes.length === 0)
    throw new JitTriggerCompileError('calendar condition empty')
  if (eventKeywords.length + eventTypes.length > MAX_KEYWORDS)
    throw new JitTriggerCompileError('calendar bounds exceeded')
  return { eventKeywords, eventTypes }
}

function compileEmbedding(value: unknown): JitCompiledTrigger['embedding'] {
  const record = asRecord(value, 'embedding condition malformed')
  ensureKeys(record, [
    'prototype_id',
    'prototype_revision',
    'model_id',
    'model_version',
    'language',
    'min_similarity'
  ])
  const prototypeId = boundedTerm(record.prototype_id)
  const prototypeRevision = boundedString(
    record.prototype_revision,
    MAX_TERM_CHARS,
    'embedding prototype revision invalid'
  )
  const modelId = boundedString(record.model_id, MAX_TERM_CHARS, 'embedding model id invalid')
  const modelVersion = boundedString(
    record.model_version,
    MAX_TERM_CHARS,
    'embedding model version invalid'
  )
  const language = boundedString(record.language, MAX_TERM_CHARS, 'embedding language invalid')
  const minSimilarity = record.min_similarity ?? 0.82
  if (
    typeof minSimilarity !== 'number' ||
    !Number.isFinite(minSimilarity) ||
    minSimilarity < 0 ||
    minSimilarity > 1
  ) {
    throw new JitTriggerCompileError('embedding threshold invalid')
  }
  return { prototypeId, prototypeRevision, modelId, modelVersion, language, minSimilarity }
}

export function compileTriggerSnapshotRow(row: JitTriggerSnapshotRow): JitCompiledTrigger {
  const id = boundedString(row.memoryId, MAX_TRIGGER_ID_CHARS, 'trigger id invalid')
  if (!Number.isInteger(row.itemRevision) || row.itemRevision <= 0)
    throw new JitTriggerCompileError('trigger revision invalid')
  const actionRecord = asRecord(row.action, 'trigger action malformed')
  ensureKeys(actionRecord, ['type', 'prompt'])
  if (actionRecord.type !== 'agent_prompt')
    throw new JitTriggerCompileError('trigger action type invalid')
  const action: JitTriggerAction = {
    type: 'agent_prompt',
    prompt: boundedString(actionRecord.prompt, MAX_PROMPT_CHARS, 'trigger prompt invalid')
  }
  if (
    row.wakeupBudgetPerDay !== null &&
    (!Number.isInteger(row.wakeupBudgetPerDay) ||
      row.wakeupBudgetPerDay < 0 ||
      row.wakeupBudgetPerDay > MAX_BUDGET)
  ) {
    throw new JitTriggerCompileError('trigger wakeup budget invalid')
  }
  const snoozedUntil = parseSnoozedUntil(row.snoozedUntil)
  const condition = parseObject(row.triggerConditionJson)
  ensureKeys(condition, [
    'schema_version',
    'match_mode',
    'entity_aliases',
    'keywords',
    'regex',
    'apps',
    'windows',
    'time',
    'calendar',
    'embedding',
    'action'
  ])
  if (condition.schema_version !== 'jit_trigger.v1')
    throw new JitTriggerCompileError('unsupported trigger schema')
  if (condition.match_mode !== 'all' && condition.match_mode !== 'any')
    throw new JitTriggerCompileError('trigger match mode invalid')

  const entityRecord = asRecord(condition.entity_aliases ?? {}, 'entity aliases malformed')
  if (Object.keys(entityRecord).length > MAX_ENTITIES)
    throw new JitTriggerCompileError('entity bounds exceeded')
  const entities: Record<string, string[]> = {}
  for (const [rawEntity, rawAliases] of Object.entries(entityRecord)) {
    const entity = boundedTerm(rawEntity)
    const aliases = normalizeTerms(rawAliases, MAX_ALIASES_PER_ENTITY)
    if (aliases.length === 0) throw new JitTriggerCompileError('entity aliases empty')
    entities[entity] = aliases
  }
  const aliasOwners: Record<string, string[]> = {}
  for (const [entity, aliases] of Object.entries(entities))
    for (const alias of aliases) (aliasOwners[alias] ??= []).push(entity)
  const ambiguousAliases: Record<string, string[]> = {}
  for (const [alias, owners] of Object.entries(aliasOwners))
    if (owners.length > 1) ambiguousAliases[alias] = owners.sort()
  const keywords = normalizeTerms(condition.keywords ?? [], MAX_KEYWORDS)
  const apps = normalizeTerms(condition.apps ?? [], MAX_APPS)
  const windows = normalizeTerms(condition.windows ?? [], MAX_WINDOWS, 120)
  const regexValues = asArray(condition.regex ?? [], 'regex selector malformed')
  if (regexValues.length > MAX_REGEXES) throw new JitTriggerCompileError('regex bounds exceeded')
  const regexes = regexValues
    .map((raw) => {
      const pattern = boundedString(raw, 160, 'regex invalid')
      if (
        /\\[1-9]|\(\?(?:[=!<]|P=)/.test(pattern) ||
        /\([^)]*(?:\*|\+|\{\d+(?:,\d*)?\})[^)]*\)(?:\*|\+|\{)/.test(pattern)
      )
        throw new JitTriggerCompileError('unsafe regex')
      try {
        return new RegExp(pattern, 'i')
      } catch {
        throw new JitTriggerCompileError('regex invalid')
      }
    })
    .sort((a, b) => a.source.localeCompare(b.source))
  const conditionCount =
    Object.keys(entities).length +
    (keywords.length ? 1 : 0) +
    (regexes.length ? 1 : 0) +
    (apps.length ? 1 : 0) +
    (windows.length ? 1 : 0) +
    (condition.time ? 1 : 0) +
    (condition.calendar ? 1 : 0) +
    (condition.embedding ? 1 : 0)
  if (conditionCount < 1 || conditionCount > MAX_CONDITION_KEYS)
    throw new JitTriggerCompileError('trigger must contain 1..12 conditions')
  if (condition.action !== undefined) {
    const embedded = asRecord(condition.action, 'trigger action malformed')
    ensureKeys(embedded, ['type', 'prompt'])
    if (embedded.type !== action.type || normalize(embedded.prompt) !== normalize(action.prompt))
      throw new JitTriggerCompileError('trigger action mismatch')
  }
  return {
    id,
    revision: row.itemRevision,
    matchMode: condition.match_mode,
    entities,
    ambiguousAliases,
    keywords,
    regexes,
    apps,
    windows,
    time:
      condition.time === undefined || condition.time === null ? null : compileTime(condition.time),
    calendar:
      condition.calendar === undefined || condition.calendar === null
        ? null
        : compileCalendar(condition.calendar),
    embedding:
      condition.embedding === undefined || condition.embedding === null
        ? null
        : compileEmbedding(condition.embedding),
    action,
    wakeupBudgetPerDay: row.wakeupBudgetPerDay,
    snoozedUntil
  }
}

function containsTerm(text: string, term: string): boolean {
  if (!term) return false
  const escaped = term.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  return new RegExp(`(?<![\\p{L}\\p{N}_])${escaped}(?![\\p{L}\\p{N}_])`, 'iu').test(text)
}

function timeMatches(
  condition: NonNullable<JitCompiledTrigger['time']>,
  date: Date | null | undefined
): boolean | null {
  if (!date) return null
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: condition.timezone,
    weekday: 'short',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false
  }).formatToParts(date)
  const get = (type: string): string => parts.find((part) => part.type === type)?.value ?? ''
  const weekdays = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
  const weekday = weekdays.indexOf(get('weekday'))
  const isoWeekday = (weekday + 6) % 7
  const hour = Number(get('hour')) % 24
  const seconds = hour * 3600 + Number(get('minute')) * 60 + Number(get('second'))
  if (condition.weekdays.length && !condition.weekdays.includes(isoWeekday)) return false
  return condition.start <= condition.end
    ? seconds >= condition.start && seconds <= condition.end
    : seconds >= condition.start || seconds <= condition.end
}

function calendarMatches(
  condition: NonNullable<JitCompiledTrigger['calendar']>,
  events: JitCalendarEvent[],
  authorized: boolean
): boolean | null {
  if (!authorized || events.length === 0) return false
  return events
    .slice(0, MAX_CALENDAR_EVENTS)
    .some(
      (event) =>
        condition.eventKeywords.some((term) => containsTerm(normalize(event.title), term)) ||
        condition.eventTypes.includes(normalize(event.eventType))
    )
}

function fingerprint(observation: JitTriggerObservation): string {
  const stable = JSON.stringify({
    eventId: observation.eventId ?? null,
    text: (observation.text ?? '').slice(0, MAX_TEXT_CHARS),
    entityLabels: [...new Set((observation.entityLabels ?? []).map(normalize))].sort(),
    appName: normalize(observation.appName),
    windowTitle: normalize(observation.windowTitle),
    occurredAt: observation.occurredAt?.toISOString() ?? null,
    calendarEvents: (observation.calendarEvents ?? [])
      .slice(0, MAX_CALENDAR_EVENTS)
      .map((event) => ({ title: normalize(event.title), eventType: normalize(event.eventType) }))
      .sort((a, b) => JSON.stringify(a).localeCompare(JSON.stringify(b))),
    embeddingKeys: Object.keys(observation.embeddingScores ?? {}).sort()
  })
  // A deterministic, content-free fingerprint is sufficient for local dedupe.
  let hash = 2166136261
  for (let i = 0; i < stable.length; i++) {
    hash ^= stable.charCodeAt(i)
    hash = Math.imul(hash, 16777619)
  }
  return (hash >>> 0).toString(16).padStart(8, '0')
}

export function evaluateJitTrigger(
  trigger: JitCompiledTrigger,
  observation: JitTriggerObservation,
  budgetDay: string,
  wakeupsUsed = 0,
  embeddingContract: JitEmbeddingContract | null = null,
  embeddingTriageSimilarity = 0.74
): JitTriggerDecision {
  const snoozedUntil = trigger.snoozedUntil ? Date.parse(trigger.snoozedUntil) : null
  const observedAt = observation.occurredAt?.getTime() ?? Date.now()
  if ((snoozedUntil !== null && !Number.isFinite(snoozedUntil)) || !Number.isFinite(observedAt)) {
    return {
      status: 'no_match',
      reason: 'trigger_snooze_malformed',
      matchedConditions: [],
      missingConditions: [],
      matchedFraction: 0,
      observationFingerprint: fingerprint(observation),
      wakeupBudgetDay: budgetDay,
      wakeupsUsed: Math.max(0, Number.isFinite(wakeupsUsed) ? Math.trunc(wakeupsUsed) : 0),
      wakeupBudgetPerDay: trigger.wakeupBudgetPerDay
    }
  }
  if (snoozedUntil !== null && observedAt < snoozedUntil) {
    return {
      status: 'no_match',
      reason: 'trigger_snoozed',
      matchedConditions: [],
      missingConditions: [],
      matchedFraction: 0,
      observationFingerprint: fingerprint(observation),
      wakeupBudgetDay: budgetDay,
      wakeupsUsed: Math.max(0, Number.isFinite(wakeupsUsed) ? Math.trunc(wakeupsUsed) : 0),
      wakeupBudgetPerDay: trigger.wakeupBudgetPerDay
    }
  }
  const text = (observation.text ?? '')
    .slice(0, MAX_TEXT_CHARS)
    .trim()
    .replace(/\s+/g, ' ')
    .toLowerCase()
  const labels = new Set((observation.entityLabels ?? []).map(normalize))
  const results = new Map<string, boolean | null>()
  const record = (key: string, value: boolean | null): void => {
    results.set(key, value)
  }
  for (const entity of Object.keys(trigger.entities).sort()) {
    const matches = trigger.entities[entity].filter(
      (alias) => labels.has(alias) || containsTerm(text, alias)
    )
    record(
      `entity:${entity}`,
      matches.some((alias) => trigger.ambiguousAliases[alias]) ? null : matches.length > 0
    )
  }
  if (trigger.keywords.length)
    record(
      'keywords',
      trigger.keywords.some((keyword) => containsTerm(text, keyword))
    )
  if (trigger.regexes.length)
    record(
      'regex',
      trigger.regexes.some((regex) => regex.test(observation.text ?? ''))
    )
  if (trigger.apps.length)
    record(
      'app',
      observation.appName ? trigger.apps.includes(normalize(observation.appName)) : null
    )
  if (trigger.windows.length) {
    const window = normalize(observation.windowTitle)
    record('window', window ? trigger.windows.some((selector) => window.includes(selector)) : null)
  }
  if (trigger.time) record('time', timeMatches(trigger.time, observation.occurredAt))
  if (trigger.calendar)
    record(
      'calendar',
      calendarMatches(
        trigger.calendar,
        observation.calendarEvents ?? [],
        observation.calendarAuthorized === true
      )
    )
  if (trigger.embedding) {
    const score = observation.embeddingScores?.[trigger.embedding.prototypeId]
    const attested =
      score &&
      embeddingContract &&
      score.modelId === embeddingContract.modelId &&
      score.modelVersion === embeddingContract.modelVersion &&
      score.language === embeddingContract.language &&
      score.prototypeRevision === embeddingContract.prototypeRevision &&
      Number.isFinite(score.score) &&
      score.score >= 0 &&
      score.score <= 1
    record(
      `embedding:${trigger.embedding.prototypeId}`,
      attested
        ? score!.score >= trigger.embedding.minSimilarity
          ? true
          : score!.score >= embeddingTriageSimilarity
            ? null
            : false
        : null
    )
  }
  const matched = [...results.entries()]
    .filter(([, value]) => value === true)
    .map(([key]) => key)
    .sort()
  const missing = [...results.entries()]
    .filter(([, value]) => value === null)
    .map(([key]) => key)
    .sort()
  const hasFalse = [...results.values()].some((value) => value === false)
  let status: JitTriggerDecisionStatus
  let reason: string
  if (trigger.matchMode === 'all') {
    status = hasFalse ? 'no_match' : missing.length ? 'ambiguous' : 'match'
    reason = hasFalse
      ? 'condition_not_satisfied'
      : missing.length
        ? 'insufficient_or_ambiguous_context'
        : 'all_conditions_satisfied'
  } else {
    status = matched.length ? 'match' : missing.length ? 'ambiguous' : 'no_match'
    reason = matched.length
      ? 'one_condition_satisfied'
      : missing.length
        ? 'insufficient_or_ambiguous_context'
        : 'no_condition_satisfied'
  }
  const safeUsed = Math.max(0, Number.isFinite(wakeupsUsed) ? Math.trunc(wakeupsUsed) : 0)
  const exhausted =
    status === 'match' &&
    trigger.wakeupBudgetPerDay !== null &&
    safeUsed >= trigger.wakeupBudgetPerDay
  if (exhausted) {
    status = 'no_match'
    reason = 'wakeup_budget_exhausted'
  }
  if (status === 'match' && trigger.wakeupBudgetPerDay === null) {
    status = 'no_match'
    reason = 'wakeup_budget_missing'
  }
  return {
    status,
    reason,
    matchedConditions: matched,
    missingConditions: missing,
    matchedFraction: results.size ? matched.length / results.size : 0,
    observationFingerprint: fingerprint(observation),
    wakeupBudgetDay: budgetDay,
    wakeupsUsed: status === 'match' ? safeUsed + 1 : safeUsed,
    wakeupBudgetPerDay: trigger.wakeupBudgetPerDay
  }
}

export function evaluateJitWatchlist(
  authority: JitRuntimeAuthority,
  triggers: JitCompiledTrigger[],
  observation: JitTriggerObservation,
  budgetDay: string,
  wakeupsUsedByTrigger: Record<string, number> = {},
  embeddingContract: JitEmbeddingContract | null = null,
  embeddingTriageSimilarity = 0.74
): {
  status: 'inactive' | 'rejected' | 'evaluated'
  nextLane: 'none' | 'planned_trigger' | 'bounded_planned_triage' | 'ambient_fallback'
  matches: Array<{ trigger: JitCompiledTrigger; decision: JitTriggerDecision }>
  ambiguous: Array<{ trigger: JitCompiledTrigger; decision: JitTriggerDecision }>
} {
  if (
    authority.mode !== 'enabled' ||
    authority.killSwitchEnabled ||
    !authority.authorizationIsCurrent
  )
    return { status: 'inactive', nextLane: 'none', matches: [], ambiguous: [] }
  if (
    !authority.ownerId ||
    authority.accountGeneration === null ||
    !authority.snapshotIsAuthoritative ||
    authority.snapshotOwnerId !== authority.ownerId ||
    authority.snapshotAccountGeneration !== authority.accountGeneration
  )
    return { status: 'rejected', nextLane: 'none', matches: [], ambiguous: [] }
  if (triggers.length > 500)
    return { status: 'rejected', nextLane: 'none', matches: [], ambiguous: [] }
  const decisions = triggers
    .slice()
    .sort((a, b) => a.id.localeCompare(b.id))
    .map((trigger) => ({
      trigger,
      decision: evaluateJitTrigger(
        trigger,
        observation,
        budgetDay,
        wakeupsUsedByTrigger[trigger.id] ?? 0,
        embeddingContract,
        embeddingTriageSimilarity
      )
    }))
  const matches = decisions.filter(({ decision }) => decision.status === 'match')
  const ambiguous = decisions.filter(({ decision }) => decision.status === 'ambiguous')
  if (matches.length)
    return { status: 'evaluated', nextLane: 'planned_trigger', matches, ambiguous }
  if (ambiguous.length)
    return { status: 'evaluated', nextLane: 'bounded_planned_triage', matches, ambiguous }
  if (triggers.length === 0) return { status: 'evaluated', nextLane: 'none', matches, ambiguous }
  return { status: 'evaluated', nextLane: 'ambient_fallback', matches, ambiguous }
}
