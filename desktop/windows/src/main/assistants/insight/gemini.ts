// The two-phase Gemini TOOL-LOOP client — net-new for Insight. Focus sends one
// vision call with a responseSchema; Insight instead drives Gemini's native
// function calling across up to 7 (Phase 1, text-only SQL investigation) + 5
// (Phase 2, one vision call + optional SQL cross-reference) iterations.
//
// Transport template is focus/gemini.ts: Electron net.fetch through the Rust
// proxy (the Gemini key never touches the device), a per-call timeout composed
// with the session abort signal, and a [2s, 8s] transient-only retry. Insight
// adds Mac's two extras: a 120s per-iteration hard timeout and a fallback model.
//
// WIRE PROTOCOL (Mac's exact shape, gt-insight-toolloop.md):
//  - body keys snake_case (system_instruction, generation_config, tool_config,
//    function_calling_config, thinking_config, function_declarations);
//  - part keys camelCase for functionCall / functionResponse / thoughtSignature /
//    inlineData;
//  - tool_config present ONLY on the forcing iteration (mode "ANY"); OMITTED on
//    every later iteration — never an explicit "AUTO";
//  - the model's functionCall is echoed back as a role:"model" turn, the tool
//    result as a role:"user" functionResponse turn (NOT role:"function");
//  - only toolCalls[0] is consumed; parallel calls after the first are dropped.
import { net } from 'electron'
import { getAbortSignal, type BackendSession } from '../core/session'
import {
  PHASE1_TOOL,
  PHASE2_TOOL,
  parseProvideAdvice,
  parseScreenshotId,
  type ExtractedInsight,
  type GeminiTool,
  type ToolCall
} from './models'

export const MODEL = 'gemini-2.5-flash'
export const FALLBACK_MODEL = 'gemini-2.5-flash'
export const THINKING_BUDGET = 1024
const REQUEST_TIMEOUT_MS = 120_000
/** 3 attempts total per model. Mac's backoff, exactly: 2s then 8s. */
const RETRY_DELAYS_MS = [2_000, 8_000]
const PHASE1_MAX_ITERS = 7
const PHASE2_MAX_ITERS = 5

/** Carries only the status — never a body (which can echo the prompt/SQL). */
export class GeminiHttpError extends Error {
  constructor(readonly status: number) {
    super(`gemini proxy HTTP ${status}`)
    this.name = 'GeminiHttpError'
  }
}

/** 5xx/429/timeout/network are retryable; a session sign-out (AbortError) is
 *  terminal — the token is dead. A 4xx fails identically every time. */
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

/** Per-request timeout composed with the external (session) abort. A timeout
 *  surfaces as a retryable 'TimeoutError'; the external signal stays an
 *  'AbortError' (terminal). Same seam as focus/gemini.ts. */
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

// --- Wire content shapes -----------------------------------------------------

type Part =
  | { text: string }
  | { inlineData: { mimeType: string; data: string } }
  | { functionCall: { name: string; args: Record<string, unknown> }; thoughtSignature?: string }
  | { functionResponse: { name: string; response: { result: string } } }
type Content = { role: 'user' | 'model'; parts: Part[] }

/** One decoded model turn: the function calls it made + any loose text. */
export type ToolTurn = { toolCalls: ToolCall[]; text: string }

/** Append one execute_sql round-trip to a phase's transcript: the model's call
 *  echoed as a role:"model" functionCall turn (thoughtSignature preserved), then
 *  the tool result as a role:"user" functionResponse turn. Identical in both
 *  phases — this is the exact wire shape Mac sends. Returns the tool result. */
function appendSqlRoundTrip(
  contents: Content[],
  call: ToolCall,
  execSql: (query: string) => string
): void {
  const query = typeof call.args.query === 'string' ? call.args.query : ''
  const result = execSql(query)
  contents.push({
    role: 'model',
    parts: [
      { functionCall: { name: 'execute_sql', args: { query } }, thoughtSignature: call.thoughtSignature }
    ]
  })
  contents.push({
    role: 'user',
    parts: [{ functionResponse: { name: 'execute_sql', response: { result } } }]
  })
}

function parseTurn(json: unknown): ToolTurn {
  const parts = (
    json as {
      candidates?: {
        content?: {
          parts?: {
            text?: string
            functionCall?: { name?: string; args?: Record<string, unknown> }
            thoughtSignature?: string
          }[]
        }
      }[]
    }
  )?.candidates?.[0]?.content?.parts
  if (!Array.isArray(parts)) return { toolCalls: [], text: '' }
  const toolCalls: ToolCall[] = []
  let text = ''
  for (const p of parts) {
    if (p.functionCall && typeof p.functionCall.name === 'string') {
      toolCalls.push({
        name: p.functionCall.name,
        args: p.functionCall.args ?? {},
        thoughtSignature: typeof p.thoughtSignature === 'string' ? p.thoughtSignature : undefined
      })
    } else if (typeof p.text === 'string') {
      text += p.text
    }
  }
  return { toolCalls, text }
}

type TurnOpts = {
  session: BackendSession
  systemPrompt: string
  contents: Content[]
  tool: GeminiTool
  forceToolCall: boolean
  external?: AbortSignal
}

function buildBody(opts: TurnOpts): Record<string, unknown> {
  const body: Record<string, unknown> = {
    contents: opts.contents,
    system_instruction: { parts: [{ text: opts.systemPrompt }] },
    generation_config: { thinking_config: { thinking_budget: THINKING_BUDGET } },
    tools: [opts.tool]
  }
  // Present ONLY when forcing — omitted entirely otherwise (never explicit AUTO).
  if (opts.forceToolCall) body.tool_config = { function_calling_config: { mode: 'ANY' } }
  return body
}

async function callModel(model: string, opts: TurnOpts): Promise<ToolTurn> {
  return withTimeout(
    REQUEST_TIMEOUT_MS,
    async (signal) => {
      const res = await net.fetch(
        `${opts.session.desktopApiBase}/v1/proxy/gemini/models/${model}:generateContent`,
        {
          method: 'POST',
          headers: {
            Authorization: `Bearer ${opts.session.token}`,
            'Content-Type': 'application/json'
          },
          body: JSON.stringify(buildBody(opts)),
          signal
        }
      )
      if (!res.ok) throw new GeminiHttpError(res.status)
      return parseTurn(await res.json())
    },
    opts.external
  )
}

/** One tool-loop iteration: retry the primary model on transient errors, then
 *  fall back to Flash if a distinct fallback exists. A non-transient error throws
 *  immediately (no retry, no fallback) — Mac's exact policy. */
async function sendToolTurn(opts: TurnOpts): Promise<ToolTurn> {
  const models = FALLBACK_MODEL && FALLBACK_MODEL !== MODEL ? [MODEL, FALLBACK_MODEL] : [MODEL]
  let lastError: unknown
  for (const model of models) {
    for (let i = 0; i <= RETRY_DELAYS_MS.length; i++) {
      try {
        return await callModel(model, opts)
      } catch (e) {
        lastError = e
        if (!isTransient(e)) throw e
        if (i < RETRY_DELAYS_MS.length) await sleep(RETRY_DELAYS_MS[i], opts.external)
      }
    }
    // Primary exhausted its retries on a transient error → try the fallback model.
  }
  throw lastError
}

// --- Two-phase orchestration -------------------------------------------------

export type PipelineDeps = {
  session: BackendSession
  systemPrompt: string
  phase1Prompt: string
  buildPhase2Prompt: (findings: string) => string
  /** execute_sql backend (sql.executeSql wrapper). Sync — better-sqlite3. */
  execSql: (query: string) => string
  /** request_screenshot backend: id → base64 JPEG, or null to abort Phase 2. */
  loadScreenshot: (id: number) => Promise<string | null>
}

export type PipelineResult = {
  insight: ExtractedInsight | null
  /** How many execute_sql calls ran across both phases (for logging counts). */
  sqlCount: number
}

/**
 * Run the full two-phase pipeline. Returns the insight to persist, or null (no
 * insight — no_advice, an exhausted phase, a missing screenshot). Throws only on
 * an unrecoverable transport error (after retries + fallback), which the caller
 * treats as "no insight this cycle", not a persisted failure.
 */
export async function runTwoPhasePipeline(deps: PipelineDeps): Promise<PipelineResult> {
  const external = getAbortSignal()
  let sqlCount = 0

  // --- Phase 1: text-only SQL investigation (≤7 iters) ---
  const p1: Content[] = [{ role: 'user', parts: [{ text: deps.phase1Prompt }] }]
  let chosenId: number | null = null
  let findings = ''

  for (let iter = 0; iter < PHASE1_MAX_ITERS; iter++) {
    const turn = await sendToolTurn({
      session: deps.session,
      systemPrompt: deps.systemPrompt,
      contents: p1,
      tool: PHASE1_TOOL,
      forceToolCall: iter === 0,
      external
    })
    const call = turn.toolCalls[0]
    if (!call) break // no tool call → end (both phases)

    if (call.name === 'execute_sql') {
      appendSqlRoundTrip(p1, call, deps.execSql)
      sqlCount++
      continue
    }
    if (call.name === 'request_screenshot') {
      const id = parseScreenshotId(call.args)
      if (id != null) {
        chosenId = id
        findings = typeof call.args.findings === 'string' ? call.args.findings : ''
        break
      }
      continue // unparseable id — waste an iteration, don't end (Mac)
    }
    if (call.name === 'no_advice') return { insight: null, sqlCount }
    // Unknown tool in Phase 1 → continue (Mac asymmetry: Phase 1 tolerates, Phase 2 ends).
  }

  if (chosenId == null) return { insight: null, sqlCount }

  // --- Phase 2: single vision call + optional SQL cross-reference (≤5 iters) ---
  const base64 = await deps.loadScreenshot(chosenId)
  if (!base64) return { insight: null, sqlCount }

  const p2: Content[] = [
    {
      role: 'user',
      parts: [
        { text: deps.buildPhase2Prompt(findings) },
        { inlineData: { mimeType: 'image/jpeg', data: base64 } }
      ]
    }
  ]

  for (let iter = 0; iter < PHASE2_MAX_ITERS; iter++) {
    const turn = await sendToolTurn({
      session: deps.session,
      systemPrompt: deps.systemPrompt,
      contents: p2,
      tool: PHASE2_TOOL,
      forceToolCall: iter === 0,
      external
    })
    const call = turn.toolCalls[0]
    if (!call) break // no tool call → end

    if (call.name === 'execute_sql') {
      appendSqlRoundTrip(p2, call, deps.execSql)
      sqlCount++
      continue
    }
    if (call.name === 'provide_advice') return { insight: parseProvideAdvice(call.args), sqlCount }
    if (call.name === 'no_advice') return { insight: null, sqlCount }
    break // Unknown tool in Phase 2 → end (Mac asymmetry).
  }

  return { insight: null, sqlCount }
}

// --- Early transport smoke ---------------------------------------------------

/** A minimal one-tool round-trip used by the dev `insight:transportSmoke` IPC to
 *  confirm the Rust proxy returns a `functionCall` through the response path AND
 *  accepts an echoed `functionResponse`. NOT part of the production pipeline. */
export async function transportSmoke(session: BackendSession): Promise<{
  firstCallName: string | null
  secondText: string
  secondCallName: string | null
}> {
  const external = getAbortSignal()
  const tool: GeminiTool = {
    function_declarations: [
      {
        name: 'echo',
        description: 'Echo a value back. Call this with the word "ping".',
        parameters: {
          type: 'object',
          properties: { value: { type: 'string', description: 'the value to echo' } },
          required: ['value']
        }
      }
    ]
  }
  const contents: Content[] = [
    { role: 'user', parts: [{ text: 'Call the echo tool with value "ping".' }] }
  ]
  const first = await sendToolTurn({
    session,
    systemPrompt: 'You are a test harness. Always call the provided tool.',
    contents,
    tool,
    forceToolCall: true,
    external
  })
  const firstCall = first.toolCalls[0] ?? null
  if (!firstCall) return { firstCallName: null, secondText: first.text, secondCallName: null }

  contents.push({
    role: 'model',
    parts: [
      {
        functionCall: { name: firstCall.name, args: firstCall.args },
        thoughtSignature: firstCall.thoughtSignature
      }
    ]
  })
  contents.push({
    role: 'user',
    parts: [{ functionResponse: { name: firstCall.name, response: { result: 'echoed: ping' } } }]
  })
  const second = await sendToolTurn({
    session,
    systemPrompt: 'You are a test harness. After the tool result, reply "done".',
    contents,
    tool,
    forceToolCall: false,
    external
  })
  return {
    firstCallName: firstCall.name,
    secondText: second.text,
    secondCallName: second.toolCalls[0]?.name ?? null
  }
}
