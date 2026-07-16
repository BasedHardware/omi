// One-shot client-side goal generation: assemble context → a single structured
// Gemini call (responseSchema JSON) → parse & validate → POST /v1/goals → record
// attribution → notify + refresh. Port of Mac's `GoalsAIService.generateGoal`.
//
// The Gemini call MIRRORS focus/gemini.ts's structured wire (net.fetch through the
// Rust proxy, `responseMimeType: application/json` + `responseSchema`, [2s,8s]
// transient retry, session-abort). insight/gemini.ts is a multi-turn TOOL loop —
// the wrong shape for a single structured completion — so we reuse focus's
// single-shot template rather than that one. No new Gemini client, no BYOK key.
//
// TASK LINKING: Mac links `linked_task_ids` to the new goal by setting each
// action item's `goalId`. The live backend has NO such field (UpdateActionItem
// has no goal_id; nothing accepts one), so linking cannot be persisted. We still
// parse + validate the ids against the bundle (below) so the model output is fully
// handled; `linkTasks` is a documented no-op seam awaiting an orchestrator ruling.
import { BrowserWindow, net } from 'electron'
import {
  getAbortSignal,
  getBackendSession,
  getSessionEpoch,
  type BackendSession
} from '../core/session'
import { notifyProactive } from '../core/notify'
import { getAppSettings, setAppSettings } from '../../appSettings'
import { fetchGoalContext, hasSufficientContext, type GoalContextData } from './context'
import { GOAL_SYSTEM_PROMPT, GOAL_SUGGESTION_SCHEMA, fillPrompt } from './prompt'

const MODEL = 'gemini-2.5-flash'
const REQUEST_TIMEOUT_MS = 30_000
/** 3 attempts total. Mac's backoff, exactly: 2s then 8s. */
const RETRY_DELAYS_MS = [2_000, 8_000]

/** The assistant id under which the "New Goal" toast is throttled/logged. */
export const GOALS_ASSISTANT_ID = 'goals'

/** Carries the status only — never a response body (it can echo the prompt, which
 *  carries the user's memories/conversations). */
export class GeminiHttpError extends Error {
  constructor(readonly status: number) {
    super(`gemini proxy HTTP ${status}`)
    this.name = 'GeminiHttpError'
  }
}

function isTransient(e: unknown): boolean {
  if (e instanceof GeminiHttpError) return e.status === 429 || e.status >= 500
  return !(e instanceof Error && e.name === 'AbortError')
}

function sleep(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) return reject(new DOMException('aborted', 'AbortError'))
    const t = setTimeout(resolve, ms)
    signal?.addEventListener(
      'abort',
      () => {
        clearTimeout(t)
        reject(new DOMException('aborted', 'AbortError'))
      },
      { once: true }
    )
  })
}

async function withTimeout<T>(
  ms: number,
  fn: (signal: AbortSignal) => Promise<T>,
  external?: AbortSignal
): Promise<T> {
  const ctrl = new AbortController()
  let timedOut = false
  const onAbort = (): void => ctrl.abort(external?.reason)
  const timer = setTimeout(() => {
    timedOut = true
    ctrl.abort(new DOMException('request timed out', 'TimeoutError'))
  }, ms)
  if (external?.aborted) ctrl.abort(external.reason)
  else external?.addEventListener('abort', onAbort, { once: true })
  try {
    return await fn(ctrl.signal)
  } catch (e) {
    if (timedOut) throw new DOMException('request timed out', 'TimeoutError')
    throw e
  } finally {
    clearTimeout(timer)
    external?.removeEventListener('abort', onAbort)
  }
}

function extractText(json: unknown): string {
  const parts = (json as { candidates?: { content?: { parts?: { text?: string }[] } }[] })
    ?.candidates?.[0]?.content?.parts
  if (!Array.isArray(parts)) return ''
  return parts
    .map((p) => p.text ?? '')
    .join('')
    .trim()
}

async function attempt(
  session: BackendSession,
  prompt: string,
  external?: AbortSignal
): Promise<string> {
  return withTimeout(
    REQUEST_TIMEOUT_MS,
    async (signal) => {
      const res = await net.fetch(
        `${session.desktopApiBase}/v1/proxy/gemini/models/${MODEL}:generateContent`,
        {
          method: 'POST',
          headers: {
            Authorization: `Bearer ${session.token}`,
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({
            contents: [{ role: 'user', parts: [{ text: prompt }] }],
            systemInstruction: { parts: [{ text: GOAL_SYSTEM_PROMPT }] },
            generationConfig: {
              responseMimeType: 'application/json',
              responseSchema: GOAL_SUGGESTION_SCHEMA
            }
          }),
          signal
        }
      )
      if (!res.ok) throw new GeminiHttpError(res.status)
      return extractText(await res.json())
    },
    external
  )
}

/** One structured completion, with Mac's retry policy. Returns the raw JSON text,
 *  or '' if the model returned nothing usable. Throws on transport failure after
 *  all attempts. */
export async function generateSuggestionText(
  session: BackendSession,
  prompt: string
): Promise<string> {
  const external = getAbortSignal()
  let lastError: unknown
  for (let i = 0; i <= RETRY_DELAYS_MS.length; i++) {
    try {
      return await attempt(session, prompt, external)
    } catch (e) {
      lastError = e
      if (i === RETRY_DELAYS_MS.length || !isTransient(e)) break
      await sleep(RETRY_DELAYS_MS[i], external)
    }
  }
  throw lastError
}

// --- Parse / validate (pure) -------------------------------------------------

export type GoalType = 'boolean' | 'scale' | 'numeric'

/** A validated model suggestion. `target`/`min`/`max` are finite numbers; `type`
 *  is always one of the three; `linkedTaskIds` are strings (unvalidated against
 *  the bundle here — validateLinkedTaskIds does that). */
export type GoalSuggestion = {
  title: string
  description: string
  type: GoalType
  target: number
  min: number
  max: number
  reasoning: string
  linkedTaskIds: string[]
}

const GOAL_TYPES: readonly GoalType[] = ['boolean', 'scale', 'numeric']

/** Parse + validate the model's JSON. Returns null when it is unusable (no title,
 *  or no numeric target — the two fields we cannot invent). A non-enum type
 *  coerces to 'numeric' (a safe countable default) rather than rejecting. */
export function parseGoalSuggestion(text: string): GoalSuggestion | null {
  if (!text) return null
  let raw: Record<string, unknown>
  try {
    raw = JSON.parse(text) as Record<string, unknown>
  } catch {
    return null
  }
  if (!raw || typeof raw !== 'object') return null

  const title = typeof raw.suggested_title === 'string' ? raw.suggested_title.trim() : ''
  if (!title) return null

  const target = typeof raw.suggested_target === 'number' ? raw.suggested_target : NaN
  if (!Number.isFinite(target)) return null

  const type = GOAL_TYPES.includes(raw.suggested_type as GoalType)
    ? (raw.suggested_type as GoalType)
    : 'numeric'
  const min =
    typeof raw.suggested_min === 'number' && Number.isFinite(raw.suggested_min)
      ? raw.suggested_min
      : 0
  const max =
    typeof raw.suggested_max === 'number' && Number.isFinite(raw.suggested_max)
      ? raw.suggested_max
      : target
  const description =
    typeof raw.suggested_description === 'string' ? raw.suggested_description.trim() : ''
  const reasoning = typeof raw.reasoning === 'string' ? raw.reasoning.trim() : ''
  const linkedTaskIds = Array.isArray(raw.linked_task_ids)
    ? raw.linked_task_ids.filter((x): x is string => typeof x === 'string' && x.trim().length > 0)
    : []

  return { title, description, type, target, min, max, reasoning, linkedTaskIds }
}

/** The POST /v1/goals body. `target_value` is ALWAYS sent (the backend 422s
 *  without it, even for boolean goals) — a non-positive/NaN target defaults to 1,
 *  matching the renderer's create path. `source` is sent for forward-compat even
 *  though the backend currently drops it. */
export function buildCreateBody(s: GoalSuggestion): Record<string, unknown> {
  const target = Number.isFinite(s.target) && s.target > 0 ? s.target : 1
  return {
    title: s.title,
    target_value: target,
    current_value: 0,
    min_value: Number.isFinite(s.min) ? s.min : 0,
    max_value: Number.isFinite(s.max) && s.max > 0 ? s.max : target,
    goal_type: s.type,
    source: 'ai_suggested'
  }
}

/** The subset of the model's `linked_task_ids` that actually exist in the fetched
 *  bundle — the model may hallucinate ids, so only bundle-present ids are kept. */
export function validateLinkedTaskIds(
  s: GoalSuggestion,
  bundleTaskIds: Iterable<string>
): string[] {
  const present = new Set(bundleTaskIds)
  return s.linkedTaskIds.filter((id) => present.has(id))
}

// --- Orchestration (injectable side-effects) ---------------------------------

/** The outcome of a generation run. `created` carries the new goal id + title.
 *  `error` is reserved for callers (schedule.generateGoalNow) to report a
 *  transport failure after retries; runGoalGenerationWith itself never returns it
 *  (a transport failure throws out of `deps.generate`/`deps.createGoal`). */
export type GenerateSkipReason =
  | 'no_session'
  | 'insufficient_context'
  | 'invalid_suggestion'
  | 'stale'
  | 'error'
export type GenerateResult =
  | { status: 'created'; goalId: string; title: string }
  | { status: 'skipped'; reason: GenerateSkipReason }

/** Injected side-effects, so the flow is unit-testable without network/Electron.
 *  `realGenerateDeps()` binds these to the live session + notify + broadcast. */
export type GenerateDeps = {
  /** Assemble the context bundle, or null when there is no session. */
  getContext: () => Promise<GoalContextData | null>
  /** Run the structured model call for the filled prompt → raw JSON text. */
  generate: (prompt: string) => Promise<string>
  /** POST /v1/goals with the built body → the created goal id. */
  createGoal: (body: Record<string, unknown>) => Promise<string>
  /** Persist the created goal id into the local attribution record. */
  recordAttribution: (goalId: string) => void
  /** Link validated task ids to the goal. No-op today (no backend field). */
  linkTasks: (goalId: string, taskIds: string[]) => Promise<void>
  /** Fire the "New Goal" notification (throttle-respecting per `manual`). */
  notify: (title: string, reasoning: string) => void
  /** Broadcast so an open Goals page refreshes. */
  broadcastChanged: () => void
  /** Session epoch at entry; a change means sign-out/switch → discard the run. */
  epochAtEntry: number
  /** Read the live epoch (compared to `epochAtEntry` before the write). */
  currentEpoch: () => number
}

/**
 * Run one generation end to end with injected side-effects. Returns a
 * `GenerateResult`. Skips (never throws) on: no session, insufficient context, an
 * unparseable/invalid model response, or a session change mid-run (epoch guard,
 * checked before the create so a departed user's goal is never written).
 */
export async function runGoalGenerationWith(deps: GenerateDeps): Promise<GenerateResult> {
  const context = await deps.getContext()
  if (!context) return { status: 'skipped', reason: 'no_session' }

  // Mac's insufficientContext guard — a bundle with no memories/conversations/
  // tasks has nothing to reason from.
  if (!hasSufficientContext(context)) return { status: 'skipped', reason: 'insufficient_context' }

  const text = await deps.generate(fillPrompt(context))
  const suggestion = parseGoalSuggestion(text)
  if (!suggestion) return { status: 'skipped', reason: 'invalid_suggestion' }

  // Epoch guard: a sign-out or user switch since entry means this goal would land
  // in the wrong (or wiped) account — discard rather than create.
  if (deps.currentEpoch() !== deps.epochAtEntry) return { status: 'skipped', reason: 'stale' }

  const goalId = await deps.createGoal(buildCreateBody(suggestion))
  deps.recordAttribution(goalId)

  const linked = validateLinkedTaskIds(
    suggestion,
    context.tasks.map((t) => t.id)
  )
  if (linked.length > 0) {
    // Best-effort: never let a link failure undo the created goal.
    await deps.linkTasks(goalId, linked).catch((e) => {
      console.warn('[goals] task linking failed:', e instanceof Error ? e.name : 'Error')
    })
  }

  deps.notify(suggestion.title, suggestion.reasoning || suggestion.description)
  deps.broadcastChanged()
  return { status: 'created', goalId, title: suggestion.title }
}

// --- Real side-effects -------------------------------------------------------

/** Cap the local attribution record so it can't grow without bound (the sanitizer
 *  caps reads at 256 too — keep the two in step). */
const ATTRIBUTION_CAP = 256

/** POST /v1/goals → the created goal id. Throws on non-OK (the caller treats a
 *  create failure as "no goal this run", not a persisted partial). */
async function createGoalOnBackend(
  session: BackendSession,
  body: Record<string, unknown>
): Promise<string> {
  const external = getAbortSignal()
  return withTimeout(
    REQUEST_TIMEOUT_MS,
    async (signal) => {
      const res = await net.fetch(`${session.apiBase}/v1/goals`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${session.token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
        signal
      })
      if (!res.ok) throw new Error(`create goal HTTP ${res.status}`)
      const json = (await res.json()) as { id?: string }
      const id = json?.id
      if (!id) throw new Error('create goal returned no id')
      return id
    },
    external
  )
}

/** Append a self-generated goal id to the local attribution record (the ONLY way
 *  stale-cleanup can tell a Windows-generated goal from a user's — the backend
 *  returns no `source`). Bounded to the newest ATTRIBUTION_CAP ids. */
function recordAttribution(goalId: string): void {
  const existing = getAppSettings().goalAutoGeneratedIds
  if (existing.some((r) => r.id === goalId)) return
  const next = [...existing, { id: goalId, createdAt: Date.now() }].slice(-ATTRIBUTION_CAP)
  setAppSettings({ goalAutoGeneratedIds: next })
}

/** Fire the "New Goal" toast. A MANUAL run (the Suggest button) is a functional
 *  answer to an explicit user action → bypasses the frequency throttle. An AUTO
 *  run is a proactive interruption → respects the user's notification prefs (so it
 *  stays silent at the default Off frequency, while the goal is still created and
 *  the Goals page still refreshes). Snooze is never bypassed either way. */
function notifyNewGoal(title: string, reasoning: string, manual: boolean): void {
  notifyProactive(
    GOALS_ASSISTANT_ID,
    {
      headline: 'New Goal',
      advice: title.length > 100 ? `${title.slice(0, 97)}…` : title,
      reasoning: reasoning || 'Generated from your recent context.',
      category: 'other',
      sourceApp: 'Omi',
      confidence: 1
    },
    { respectFrequency: !manual }
  )
}

/** Broadcast so any open Goals page re-fetches (mirrors `tasks:changed`). */
function broadcastGoalsChanged(): void {
  for (const w of BrowserWindow.getAllWindows()) {
    if (!w.isDestroyed()) w.webContents.send('goals:changed')
  }
}

/** Build the production side-effects. Pins the session + epoch at entry; a null
 *  session makes getContext a soft no-op (→ skipped 'no_session'). `manual` only
 *  affects the notification's throttle policy. */
export function realGenerateDeps(opts: { manual: boolean }): GenerateDeps {
  const session = getBackendSession()
  const epochAtEntry = getSessionEpoch()
  return {
    getContext: fetchGoalContext,
    generate: (prompt) => generateSuggestionText(session as BackendSession, prompt),
    createGoal: (body) => createGoalOnBackend(session as BackendSession, body),
    recordAttribution,
    // Documented no-op: the live backend has no action-item goal_id field. The
    // ids are still validated (runGoalGenerationWith) so a future backend link
    // endpoint drops straight in here.
    linkTasks: async () => {},
    notify: (title, reasoning) => notifyNewGoal(title, reasoning, opts.manual),
    broadcastChanged: broadcastGoalsChanged,
    epochAtEntry,
    currentEpoch: getSessionEpoch
  }
}

/** Production one-shot: assemble real deps + run. `manual` selects the toast
 *  throttle policy (see notifyNewGoal). */
export function runGoalGeneration(opts: { manual: boolean }): Promise<GenerateResult> {
  return runGoalGenerationWith(realGenerateDeps(opts))
}
