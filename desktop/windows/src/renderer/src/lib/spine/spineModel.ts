// The Activity spine: conversations, memories, tasks and captured screen moments
// composed into one reverse-chronological stream, grouped by day.
//
// Ported from macOS `MainWindow/Spine/SpineModel.swift`. Everything here is pure
// so the composition rules can be tested without a database, a network or a
// renderer - which matters, because almost every rule below exists to stop a
// specific wrong-looking timeline rather than to produce a right-looking one.
//
// Timestamps are epoch milliseconds throughout (the Windows convention; macOS
// uses Date). Day and hour bucketing is done in JS against the LOCAL calendar
// and never in SQL, for the reason the macOS file header gives: local-time
// bucketing is what makes a DST-transition day come out right, and a UTC-keyed
// GROUP BY silently shifts every row near midnight into the wrong day.

/** The one filter axis. "Everything" is the absence of a filter, modelled as
 *  `null` rather than a member, so a row can never claim to be it. */
export type SpineKind = 'conversations' | 'memories' | 'tasks' | 'screen'

export interface SpineMoment {
  id: number
  timestamp: number
  appName: string
  windowTitle: string | null
  imagePath: string | null
}

export interface SpineMemory {
  id: string
  text: string
  timestamp: number
  /** Set when the memory came out of a conversation. */
  conversationId: string | null
}

export interface SpineTask {
  id: string
  text: string
  timestamp: number
  conversationId: string | null
  completed: boolean
  sourceLabel: string
}

export interface SpineConversation {
  id: string
  title: string
  overview: string
  category: string
  emoji: string
  startedAt: number
  finishedAt: number
  starred: boolean
}

/** What one day's screen capture looks like to the spine: an exact total and
 *  per-hour histogram, plus a bounded sample of frames to actually show. */
export interface SpineDayScreen {
  total: number
  /** 24 entries, index = local hour. Exact counts, not sampled. */
  hourCounts: number[]
  sampled: SpineMoment[]
}

export type SpineRowContent =
  | {
      type: 'conversation'
      conversation: SpineConversation
      memoryCount: number
      taskCount: number
      momentCount: number
    }
  | { type: 'memories'; memories: SpineMemory[] }
  | { type: 'tasks'; tasks: SpineTask[] }
  | { type: 'moments'; shown: SpineMoment[]; total: number }
  | { type: 'brainMap'; memoryCount: number }

export interface SpineRow {
  /** `"<prefix>:<recordId>"`. The prefix is an identity CONTRACT, not a
   *  convention: the re-seat pass parses the owner id back out of it. */
  id: string
  /** The only value the stream is ordered by. */
  anchor: number
  kind: SpineKind
  /** True when this row was produced by the conversation directly above it. */
  isAttached: boolean
  content: SpineRowContent
  /** Lowercased haystack a typed query is matched against. */
  searchText: string
}

export interface SpineDay {
  /** Local midnight, epoch ms. The day's identity everywhere. */
  id: number
  title: string
  rows: SpineRow[]
  /** null means "this day's screen capture has not been read yet", which is a
   *  different statement from 0 and must never be collapsed into it. */
  momentCount: number | null
  conversationCount: number
  taskCount: number
  hourCounts: number[]
}

/** Frames shown in one strip. The row still reports the full cluster size, so a
 *  strip can honestly say it is showing 8 of 184. */
export const MOMENTS_PER_STRIP = 8

/** A gap longer than this splits a run of loose frames into two clusters. */
export const MOMENT_CLUSTER_GAP_MS = 45 * 60 * 1000

/** Local midnight for a timestamp, as epoch ms. */
export function startOfLocalDay(ts: number): number {
  const d = new Date(ts)
  return new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime()
}

/** Local hour (0-23) for a timestamp. */
export function localHour(ts: number): number {
  return new Date(ts).getHours()
}

/** Dedupe by id keeping the FIRST sighting and the original order. Load-bearing:
 *  both conversations and memories page by offset against a list the server
 *  re-sorts, so overlapping pages are normal rather than exceptional. */
export function uniqueById<T extends { id: string | number }>(items: T[]): T[] {
  const seen = new Set<string | number>()
  return items.filter((item) => {
    if (seen.has(item.id)) return false
    seen.add(item.id)
    return true
  })
}

/** Splits loose frames into runs, newest first, splitting on a gap strictly
 *  greater than 45 minutes. Frames inside each run stay newest-first. */
export function clusterMoments(moments: SpineMoment[]): SpineMoment[][] {
  const ordered = [...moments].sort((a, b) => b.timestamp - a.timestamp)
  const runs: SpineMoment[][] = []
  let current: SpineMoment[] = []
  for (const moment of ordered) {
    const previous = current[current.length - 1]
    if (previous !== undefined && previous.timestamp - moment.timestamp > MOMENT_CLUSTER_GAP_MS) {
      runs.push(current)
      current = []
    }
    current.push(moment)
  }
  if (current.length > 0) runs.push(current)
  return runs
}

const lower = (parts: Array<string | null | undefined>): string =>
  parts
    .filter((p): p is string => typeof p === 'string' && p.length > 0)
    .join(' ')
    .toLowerCase()

function conversationRow(
  conversation: SpineConversation,
  memoryCount: number,
  taskCount: number,
  momentCount: number
): SpineRow {
  return {
    id: `conv:${conversation.id}`,
    anchor: conversation.startedAt,
    kind: 'conversations',
    isAttached: false,
    content: { type: 'conversation', conversation, memoryCount, taskCount, momentCount },
    searchText: lower([conversation.title, conversation.overview, conversation.category])
  }
}

const memoriesRow = (id: string, memories: SpineMemory[], attached: boolean): SpineRow => ({
  id,
  anchor: Math.max(...memories.map((m) => m.timestamp)),
  kind: 'memories',
  isAttached: attached,
  content: { type: 'memories', memories },
  searchText: lower(memories.map((m) => m.text))
})

const tasksRow = (id: string, tasks: SpineTask[], attached: boolean): SpineRow => ({
  id,
  anchor: Math.max(...tasks.map((t) => t.timestamp)),
  kind: 'tasks',
  isAttached: attached,
  content: { type: 'tasks', tasks },
  searchText: lower(tasks.flatMap((t) => [t.text, t.sourceLabel]))
})

const momentsRow = (id: string, moments: SpineMoment[], attached: boolean): SpineRow => ({
  id,
  anchor: Math.max(...moments.map((m) => m.timestamp)),
  kind: 'screen',
  isAttached: attached,
  content: { type: 'moments', shown: moments.slice(0, MOMENTS_PER_STRIP), total: moments.length },
  searchText: lower(moments.flatMap((m) => [m.appName, m.windowTitle]))
})

/** Fixed presentation order for the rows attached to one conversation. */
const ATTACHMENT_ORDER: Record<SpineKind, number> = {
  conversations: 0,
  memories: 1,
  tasks: 2,
  screen: 3
}

/** The owner conversation id encoded in an attached row's id: everything after
 *  the first colon. */
export function ownerIdOf(rowId: string): string {
  const at = rowId.indexOf(':')
  return at < 0 ? '' : rowId.slice(at + 1)
}

export interface SpineInput {
  conversations: SpineConversation[]
  memories: SpineMemory[]
  tasks: SpineTask[]
  /** Keyed by local-midnight epoch ms. */
  screen: Record<number, SpineDayScreen>
  /** Days whose screen capture has been read. A day absent from this reports a
   *  null moment count, which the rail renders as "counting" rather than zero. */
  loadedScreenDays?: Set<number>
}

/**
 * Composes everything into days, newest first.
 *
 * `now` is injected so day titles are deterministic in tests; production passes
 * Date.now().
 */
export function composeSpine(input: SpineInput, now: number = Date.now()): SpineDay[] {
  const conversations = uniqueById(input.conversations)
  const memories = uniqueById(input.memories)
  const tasks = uniqueById(input.tasks)

  // Attach by conversation id, but only to a conversation that is actually
  // loaded. A memory pointing at a conversation that has not been paged in yet
  // becomes a standalone row - it is never dropped, because the alternative is
  // silently hiding the user's data behind a paging boundary.
  const loaded = new Set(conversations.map((c) => c.id))
  const attachedMemories = new Map<string, SpineMemory[]>()
  const looseMemories: SpineMemory[] = []
  for (const memory of memories) {
    const owner = memory.conversationId
    if (owner !== null && loaded.has(owner)) push(attachedMemories, owner, memory)
    else looseMemories.push(memory)
  }
  const attachedTasks = new Map<string, SpineTask[]>()
  const looseTasks: SpineTask[] = []
  for (const task of tasks) {
    const owner = task.conversationId
    if (owner !== null && loaded.has(owner)) push(attachedTasks, owner, task)
    else looseTasks.push(task)
  }

  const conversationsByDay = new Map<number, SpineConversation[]>()
  for (const c of conversations) push(conversationsByDay, startOfLocalDay(c.startedAt), c)
  const memoriesByDay = new Map<number, SpineMemory[]>()
  for (const m of looseMemories) push(memoriesByDay, startOfLocalDay(m.timestamp), m)
  const tasksByDay = new Map<number, SpineTask[]>()
  for (const t of looseTasks) push(tasksByDay, startOfLocalDay(t.timestamp), t)

  const dayIds = new Set<number>([
    ...conversationsByDay.keys(),
    ...memoriesByDay.keys(),
    ...tasksByDay.keys(),
    ...Object.keys(input.screen).map(Number)
  ])

  return [...dayIds]
    .sort((a, b) => b - a)
    .map((dayId) =>
      composeDay({
        dayId,
        now,
        conversations: conversationsByDay.get(dayId) ?? [],
        looseMemories: memoriesByDay.get(dayId) ?? [],
        looseTasks: tasksByDay.get(dayId) ?? [],
        screen: input.screen[dayId],
        attachedMemories,
        attachedTasks,
        screenLoaded: input.loadedScreenDays?.has(dayId) ?? input.screen[dayId] !== undefined
      })
    )
}

function push<K, V>(map: Map<K, V[]>, key: K, value: V): void {
  const existing = map.get(key)
  if (existing === undefined) map.set(key, [value])
  else existing.push(value)
}

function composeDay(args: {
  dayId: number
  now: number
  conversations: SpineConversation[]
  looseMemories: SpineMemory[]
  looseTasks: SpineTask[]
  screen: SpineDayScreen | undefined
  attachedMemories: Map<string, SpineMemory[]>
  attachedTasks: Map<string, SpineTask[]>
  screenLoaded: boolean
}): SpineDay {
  const ordered = [...args.conversations].sort((a, b) => b.startedAt - a.startedAt)
  const { momentsByConversation, looseMoments } = attachMoments(ordered, args.screen?.sampled ?? [])

  const rows: SpineRow[] = []
  for (const conversation of ordered) {
    const mems = (args.attachedMemories.get(conversation.id) ?? []).sort(
      (a, b) => b.timestamp - a.timestamp
    )
    const tsks = (args.attachedTasks.get(conversation.id) ?? []).sort(
      (a, b) => b.timestamp - a.timestamp
    )
    const moments = momentsByConversation.get(conversation.id) ?? []
    rows.push(conversationRow(conversation, mems.length, tsks.length, moments.length))
    if (mems.length > 0) rows.push(memoriesRow(`conv-mem:${conversation.id}`, mems, true))
    if (tsks.length > 0) rows.push(tasksRow(`conv-task:${conversation.id}`, tsks, true))
    if (moments.length > 0) rows.push(momentsRow(`conv-shot:${conversation.id}`, moments, true))
  }

  // One row per loose memory and per loose task; only attached ones are batched.
  for (const memory of [...args.looseMemories].sort((a, b) => b.timestamp - a.timestamp)) {
    rows.push(memoriesRow(`mem:${memory.id}`, [memory], false))
  }
  for (const task of [...args.looseTasks].sort((a, b) => b.timestamp - a.timestamp)) {
    rows.push(tasksRow(`task:${task.id}`, [task], false))
  }
  for (const cluster of clusterMoments(looseMoments)) {
    rows.push(momentsRow(`shot:${cluster[0].id}`, cluster, false))
  }

  rows.sort(compareRows)

  const seated = reseatAttachments(rows)

  const memoryCount = seated.reduce(
    (n, r) => n + (r.content.type === 'memories' ? r.content.memories.length : 0),
    0
  )
  const taskCount = seated.reduce(
    (n, r) => n + (r.content.type === 'tasks' ? r.content.tasks.length : 0),
    0
  )
  // The brain-map card is appended AFTER the sort and after re-seating, so it
  // sits at the foot of the day regardless of its anchor.
  if (memoryCount > 0) {
    seated.push({
      id: `map:${args.dayId}`,
      anchor: args.dayId,
      // Deliberately `memories`: soloing Conversations on a memories-only day
      // should drop the day entirely rather than leave an orphan map card.
      kind: 'memories',
      isAttached: false,
      content: { type: 'brainMap', memoryCount },
      searchText: 'brain map how the day’s memories connect'
    })
  }

  return {
    id: args.dayId,
    title: formatDayTitle(args.dayId, args.now),
    rows: seated,
    momentCount: args.screenLoaded ? (args.screen?.total ?? 0) : null,
    conversationCount: ordered.length,
    taskCount,
    hourCounts: args.screen?.hourCounts ?? new Array<number>(24).fill(0)
  }
}

/**
 * Stream order: newest anchor first, and at an identical anchor a conversation
 * leads so its own attachments never appear above it before the re-seat pass.
 *
 * The kind tie-break is defence in depth rather than the thing that produces
 * today's order: rows are emitted conversation-first and Array.prototype.sort is
 * stable, so it is already correct without it. It is written out so that
 * changing the emit order cannot silently reorder a conversation under its own
 * memory, and it is exported so the rule can be tested rather than inferred from
 * whatever the emit order happens to be.
 */
export function compareRows(a: SpineRow, b: SpineRow): number {
  if (a.anchor !== b.anchor) return b.anchor - a.anchor
  if (a.kind === 'conversations' && b.kind !== 'conversations') return -1
  if (b.kind === 'conversations' && a.kind !== 'conversations') return 1
  return 0
}

/**
 * Single-pass two-pointer merge that decides which conversation, if any, each
 * frame belongs to. Both lists are newest-first.
 *
 * The cursor advances only past conversations that START AFTER the frame.
 * Advancing on `finishedAt` instead is a real bug: one frame newer than every
 * conversation would consume the whole list and orphan every conversation
 * behind it. macOS regression-tests exactly that
 * (`testAFrameNewerThanEveryConversationDoesNotOrphanTheOnesBehindIt`).
 */
export function attachMoments(
  conversationsNewestFirst: SpineConversation[],
  sampled: SpineMoment[]
): { momentsByConversation: Map<string, SpineMoment[]>; looseMoments: SpineMoment[] } {
  const momentsByConversation = new Map<string, SpineMoment[]>()
  const looseMoments: SpineMoment[] = []
  let cursor = 0
  for (const moment of [...sampled].sort((a, b) => b.timestamp - a.timestamp)) {
    while (
      cursor < conversationsNewestFirst.length &&
      conversationsNewestFirst[cursor].startedAt > moment.timestamp
    ) {
      cursor += 1
    }
    const candidate = conversationsNewestFirst[cursor]
    if (candidate !== undefined && moment.timestamp <= candidate.finishedAt) {
      push(momentsByConversation, candidate.id, moment)
    } else {
      looseMoments.push(moment)
    }
  }
  return { momentsByConversation, looseMoments }
}

/**
 * Pulls every attached row out and re-inserts it directly under its owner
 * conversation. This deliberately defeats the pure-anchor ordering: a memory
 * recorded mid-conversation would otherwise interleave with unrelated rows and
 * read as though it came from somewhere else.
 */
export function reseatAttachments(rows: SpineRow[]): SpineRow[] {
  const attachedByOwner = new Map<string, SpineRow[]>()
  const trunk: SpineRow[] = []
  for (const row of rows) {
    if (row.isAttached) push(attachedByOwner, ownerIdOf(row.id), row)
    else trunk.push(row)
  }
  // Attachments sit under their conversation in a FIXED order - memories, then
  // tasks, then moments - rather than by anchor. Anchor order is right for the
  // trunk, where it means "what happened next", but under a conversation it
  // would put the memory row above the task row on one card and below it on the
  // next depending on which happened to be recorded last, so the same card reads
  // differently every time.
  for (const attached of attachedByOwner.values()) {
    attached.sort((a, b) => ATTACHMENT_ORDER[a.kind] - ATTACHMENT_ORDER[b.kind])
  }
  const out: SpineRow[] = []
  for (const row of trunk) {
    out.push(row)
    if (row.content.type !== 'conversation') continue
    const attached = attachedByOwner.get(row.content.conversation.id)
    if (attached !== undefined) {
      out.push(...attached)
      attachedByOwner.delete(row.content.conversation.id)
    }
  }
  // An attachment whose owner is not in this day's trunk would otherwise vanish.
  for (const orphans of attachedByOwner.values()) out.push(...orphans)
  return out
}

/**
 * Keeps only the rows matching a kind and a query, and drops days left empty.
 *
 * Filtering is presentation over an already-composed stream, so a row's
 * attachment and ordering never depend on what is filtered.
 */
export function filterSpine(days: SpineDay[], kind: SpineKind | null, query: string): SpineDay[] {
  const needle = query.trim().toLowerCase()
  if (kind === null && needle.length === 0) return days
  const out: SpineDay[] = []
  for (const day of days) {
    const rows = day.rows.filter((row) => {
      if (kind !== null && row.kind !== kind) return false
      if (needle.length === 0) return true
      return row.searchText.includes(needle)
    })
    if (rows.length > 0) out.push({ ...day, rows })
  }
  return out
}

/** Rows across every day, for a match count that does not depend on folding. */
export function countRows(days: SpineDay[]): number {
  return days.reduce((n, day) => n + day.rows.length, 0)
}

// --- formatting --------------------------------------------------------------

/** `"Today"`, `"Yesterday"`, `"Wednesday 6 August"`, or `"Wednesday 30 September 2026"`. */
export function formatDayTitle(dayId: number, now: number): string {
  const today = startOfLocalDay(now)
  if (dayId === today) return 'Today'
  const yesterday = startOfLocalDay(today - 12 * 60 * 60 * 1000)
  if (dayId === yesterday) return 'Yesterday'
  const d = new Date(dayId)
  const sameYear = d.getFullYear() === new Date(now).getFullYear()
  return d.toLocaleDateString(undefined, {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
    ...(sameYear ? {} : { year: 'numeric' })
  })
}

/** `"9:41 AM"`. */
export function formatRowTime(ts: number): string {
  return new Date(ts).toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' })
}

/** `"12 AM"`, `"9 AM"`, `"12 PM"`, `"9 PM"`. */
export function formatHourLabel(hour: number): string {
  if (hour === 0) return '12 AM'
  if (hour === 12) return '12 PM'
  return hour < 12 ? `${hour} AM` : `${hour - 12} PM`
}
