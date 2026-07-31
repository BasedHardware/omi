// The Gemini TOOL-LOOP wire layer for TaskAssistant — the transport only, no
// tool dispatch. It MIRRORS insight/gemini.ts's primitives (per PR-B decision #5:
// copy, don't refactor insight/) and re-parameterizes the four Task-loop values:
// a 300s per-call timeout (Insight uses 120s), thinkingBudget 1024, and a
// primary + fallback model pair (both gemini-2.5-flash on Windows — no tier).
//
// Task's loop is SINGLE-PHASE: the vision frame is present from iteration 0, and
// the model drives up to 8 iterations across 5 tools ending in extract_task. This
// file exposes exactly two send functions the Wave-2 dispatch loop calls:
//   (a) sendInitialTurn — the first turn (prompt text + the JPEG frame), forcing a
//       tool call (tool_config mode "ANY");
//   (b) sendToolResponseTurn — a subsequent turn: append the model's tool call and
//       our tool result (the exact model→user round-trip), then ask again in AUTO
//       mode (tool_config omitted).
// Deciding WHICH tool result to return for a given call — the dispatch — stays in
// the caller (Wave 2). This file never selects or executes a tool.
//
// Transport template is insight/gemini.ts, itself templated on focus/gemini.ts:
// Electron net.fetch through the Rust Gemini proxy (the key never touches the
// device), a per-call timeout composed with the session abort signal, and a
// [2s, 8s] transient-only retry with a fallback-model round.
//
// WIRE PROTOCOL (Mac's exact shape, unchanged from Insight):
//  - body keys snake_case (system_instruction, generation_config, tool_config,
//    function_calling_config, thinking_config, function_declarations);
//  - part keys camelCase for functionCall / functionResponse / thoughtSignature /
//    inlineData;
//  - tool_config present ONLY on the forcing (iter 0) turn (mode "ANY"); OMITTED
//    on every later turn — never an explicit "AUTO";
//  - the model's functionCall is echoed back as a role:"model" turn (its
//    thoughtSignature preserved), the tool result as a role:"user"
//    functionResponse turn (NOT role:"function");
//  - only toolCalls[0] is consumed by the caller; parallel calls are its concern.
import { net } from 'electron'
import { getAbortSignal, type BackendSession } from '../core/session'
import type { GeminiTool, ToolCall } from '../insight/models'

/** Task-loop model pair. Windows surfaces no tier, so both are Flash: the primary
 *  round runs, and the "fallback" is a same-family fresh retry round (Mac §4:
 *  "swap to the next model and retry fresh"). Unlike Insight — whose flash+flash
 *  pair is collapsed to one round by a dedup shortcut — Task keeps BOTH rounds so
 *  the documented fallback behavior actually runs; on a persistent transient error
 *  that is up to 2 rounds × 3 attempts. Keep the exact ids as strings. */
export const TASK_MODEL = 'gemini-2.5-flash'
export const TASK_FALLBACK_MODEL = 'gemini-2.5-flash'
export const TASK_THINKING_BUDGET = 1024
/** 300s per iteration (Mac GeminiClient.swift:973). Insight is 120s; Task is
 *  longer because its multi-tool vision loop can think for a while. */
export const TASK_REQUEST_TIMEOUT_MS = 300_000
/** 3 attempts per model round. Mac's backoff, exactly: 2s then 8s. */
const RETRY_DELAYS_MS = [2_000, 8_000]

/** Carries only the status — never a body (which can echo the prompt/frame). */
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
 *  'AbortError' (terminal). Same seam as insight/gemini.ts. */
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

export type Part =
  | { text: string }
  | { inlineData: { mimeType: string; data: string } }
  | { functionCall: { name: string; args: Record<string, unknown> }; thoughtSignature?: string }
  | { functionResponse: { name: string; response: { result: string } } }
export type Content = { role: 'user' | 'model'; parts: Part[] }

/** One decoded model turn: the function calls it made + any loose text. */
export type ToolTurn = { toolCalls: ToolCall[]; text: string }

/** Append one tool round-trip to the transcript: the model's call echoed as a
 *  role:"model" functionCall turn (thoughtSignature preserved, full args echoed),
 *  then the tool result as a role:"user" functionResponse turn. This is the exact
 *  wire shape Mac sends. The `result` string is whatever the caller's dispatch
 *  produced — this function neither runs nor interprets the tool. */
function appendToolRoundTrip(contents: Content[], call: ToolCall, result: string): void {
  contents.push({
    role: 'model',
    parts: [
      {
        functionCall: { name: call.name, args: call.args },
        thoughtSignature: call.thoughtSignature
      }
    ]
  })
  contents.push({
    role: 'user',
    parts: [{ functionResponse: { name: call.name, response: { result } } }]
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
    generation_config: { thinking_config: { thinking_budget: TASK_THINKING_BUDGET } },
    tools: [opts.tool]
  }
  // Present ONLY when forcing — omitted entirely otherwise (never explicit AUTO).
  if (opts.forceToolCall) body.tool_config = { function_calling_config: { mode: 'ANY' } }
  return body
}

async function callModel(model: string, opts: TurnOpts): Promise<ToolTurn> {
  return withTimeout(
    TASK_REQUEST_TIMEOUT_MS,
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

/** One tool-loop turn over the wire: retry the primary model on transient errors,
 *  then run a fresh fallback-model round. A non-transient error throws immediately
 *  (no retry, no fallback) — Mac's exact policy. */
async function sendToolTurn(opts: TurnOpts): Promise<ToolTurn> {
  let lastError: unknown
  for (const model of [TASK_MODEL, TASK_FALLBACK_MODEL]) {
    for (let i = 0; i <= RETRY_DELAYS_MS.length; i++) {
      try {
        return await callModel(model, opts)
      } catch (e) {
        lastError = e
        if (!isTransient(e)) throw e
        if (i < RETRY_DELAYS_MS.length) await sleep(RETRY_DELAYS_MS[i], opts.external)
      }
    }
    // Primary exhausted its retries on a transient error → try the fallback round.
  }
  throw lastError
}

// --- Public wire API (dispatch stays in the Wave-2 loop) ---------------------

type BaseWireOpts = {
  session: BackendSession
  systemPrompt: string
  tool: GeminiTool
  /** Session abort; defaults to the shared one. Pin it in the loop and re-check
   *  the epoch around every await — this only stops the in-flight HTTP. */
  external?: AbortSignal
}

/**
 * (a) The first turn. Builds the initial transcript — the prompt text plus the
 * JPEG frame present from iteration 0 — and sends it forcing a tool call
 * (tool_config mode "ANY"). Returns the model turn AND the transcript, which the
 * caller keeps mutating (via sendToolResponseTurn) across the loop.
 */
export async function sendInitialTurn(
  opts: BaseWireOpts & { prompt: string; imageBase64: string }
): Promise<{ turn: ToolTurn; contents: Content[] }> {
  const contents: Content[] = [
    {
      role: 'user',
      parts: [
        { text: opts.prompt },
        { inlineData: { mimeType: 'image/jpeg', data: opts.imageBase64 } }
      ]
    }
  ]
  const turn = await sendToolTurn({
    session: opts.session,
    systemPrompt: opts.systemPrompt,
    contents,
    tool: opts.tool,
    forceToolCall: true,
    external: opts.external ?? getAbortSignal()
  })
  return { turn, contents }
}

/**
 * (b) A subsequent turn. First appends the model's tool call and the caller's
 * tool result to the transcript (the exact model→user round-trip), then asks the
 * model again in AUTO mode (tool_config omitted). The caller owns `contents` and
 * has already decided `result` for this `call` — no dispatch happens here.
 */
export async function sendToolResponseTurn(
  opts: BaseWireOpts & { contents: Content[]; call: ToolCall; result: string }
): Promise<ToolTurn> {
  appendToolRoundTrip(opts.contents, opts.call, opts.result)
  return sendToolTurn({
    session: opts.session,
    systemPrompt: opts.systemPrompt,
    contents: opts.contents,
    tool: opts.tool,
    forceToolCall: false,
    external: opts.external ?? getAbortSignal()
  })
}
