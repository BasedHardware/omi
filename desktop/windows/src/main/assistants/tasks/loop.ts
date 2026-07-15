// The TaskAssistant's single-phase multi-tool extraction loop — the heart of the
// pipeline. The vision frame is present from iteration 0; the model drives up to
// 8 model calls across the 5 tools (search_similar / search_keywords /
// no_task_found / extract_task / reject_task), and the loop returns every
// ExtractedTask it produced (multi-task per frame). Ported 1:1 from Mac's
// `sendImageToolLoop` dispatch (TaskAssistant.swift:1069-1333).
//
// This file owns the DISPATCH only — the transport (retry / fallback / timeout /
// the model→user functionResponse round-trip) lives in geminiWire.ts, which this
// loop calls via sendInitialTurn (the forced iter-0 turn carrying the JPEG) and
// sendToolResponseTurn (each subsequent turn, appending the model's call + our
// tool result). Only `toolCalls[0]` is consumed each turn (Mac's contract).
//
// Scope boundaries (per PR-B spec §4-§5): the loop does NOT apply the 0.75
// confidence gate (that runs at save time in create.ts) and does NOT save
// anything — it returns ExtractedTask[] and the assistant (Wave 3) saves each.
//
// The impure edges — the two wire send functions and the two search backends,
// plus the context assembler — are injectable so the whole dispatch is hermetic
// with scripted tool-call sequences; production omits `deps` and gets the real
// implementations.
import { getAbortSignal, type BackendSession } from '../core/session'
import type { GeminiTool, ToolCall } from '../insight/models'
import { sendInitialTurn, sendToolResponseTurn } from './geminiWire'
import { TASK_TOOLS } from './tools'
import { parseExtractTask, validateTaskTitle, wordCount, type ExtractedTask } from './models'
import { executeVectorSearch, executeKeywordSearch, encodeSearchResults } from './toolBackends'
import { assembleTaskContext } from './context'
import { buildUserPrompt, TASK_SYSTEM_PROMPT, TASK_CAPTURE_POLICY_TRAILER } from './prompt'

/** Mac `for iteration in 0..<8` — up to 8 model calls total (the forced initial
 *  turn + up to 7 response turns). TaskAssistant.swift:1069. */
export const TASK_MAX_ITERS = 8

/** Everything the loop needs about the frame being analyzed. `app`/`today`/
 *  `isMessaging` feed buildUserPrompt; `imageBase64` is the JPEG present from
 *  iteration 0. `session`/`external` are pinned by the assistant (Wave 3) and
 *  threaded to geminiWire so a session change aborts in-flight HTTP. `now` is
 *  injected only so the context goals-cache is testable. */
export type ExtractionLoopParams = {
  session: BackendSession
  app: string
  today: string
  isMessaging: boolean
  imageBase64: string
  external?: AbortSignal
  systemPrompt?: string
  now?: Date
}

/** The injectable impure edges. Production omits all of these (the real
 *  implementations bind); tests supply fakes to script a tool-call sequence and
 *  assert the exact functionResponse text sent back on each turn. */
export type ExtractionLoopDeps = {
  sendInitial: typeof sendInitialTurn
  sendResponse: typeof sendToolResponseTurn
  executeVectorSearch: (query: string) => Promise<Awaited<ReturnType<typeof executeVectorSearch>>>
  executeKeywordSearch: (query: string) => Promise<Awaited<ReturnType<typeof executeKeywordSearch>>>
  assembleContext: (now?: Date) => Promise<string>
}

/** Mac's REJECTED functionResponse (TA:1128-1132), verbatim — sent when a proposed
 *  `extract_task` title fails `validateTaskTitle`, asking the model to retry with
 *  more specifics (within the iteration budget). */
function buildRejectedResponse(error: string, title: string, words: number): string {
  return (
    `REJECTED: ${error}. ` +
    `Your title was: "${title}" (${words} words). ` +
    'Either rewrite with 6+ words including a specific person/project name and concrete action, ' +
    'or call no_task_found if you cannot be more specific.'
  )
}

/** Mac's "look again" functionResponse after a successful extract (TA:1204-1214),
 *  verbatim — a single frame can hold multiple distinct commitments, so we ask the
 *  model to keep going until it calls no_task_found. */
function buildExtractedResponse(title: string): string {
  return (
    `EXTRACTED: "${title}". ` +
    'Now look at the SAME screenshot again — is there ANOTHER distinct, unrelated commitment from a different request or different deliverable? ' +
    '(Same person asking for two different things counts as two tasks.) ' +
    'If yes, search_similar for the next one and extract it. ' +
    'If no other commitment remains, call no_task_found.'
  )
}

/** Mac's reject_task "look again" functionResponse (TA:1234-1243), verbatim —
 *  reject_task no longer kills the frame; the model may have rejected only one of
 *  several commitments, so we feed it back and let it look for others. */
const REJECT_LOOK_AGAIN_RESPONSE =
  'REJECTED that candidate (duplicate / already tracked). ' +
  'Look at the SAME screenshot again — is there ANOTHER distinct, unrelated commitment that is NOT a duplicate of any existing task? ' +
  'If yes, search_similar for it and extract it. ' +
  'If no other commitment remains, call no_task_found.'

/** One dispatch outcome for a consumed tool call. `terminal` breaks the loop and
 *  returns the accumulated results (no_task_found / unknown tool / no call).
 *  Otherwise `result` is the functionResponse string to round-trip so the model
 *  can continue. */
type Dispatch = { terminal: true } | { terminal: false; result: string }

/**
 * Dispatch one consumed tool call: run the search backends / parse-and-validate an
 * extraction / handle reject_task, mutating `results` for a successful extract and
 * returning either the functionResponse to send back or a terminal signal. Mirrors
 * Mac's `switch toolCall.name` (TA:1083-1319) exactly, including the terminal rules:
 *  - no_task_found        → terminal (return accumulated).
 *  - extract_task (valid) → push the task, send the "look again" response, continue.
 *  - extract_task (bad)   → send the REJECTED response, continue (retry in budget).
 *  - reject_task          → send the reject "look again" response, continue (NOT
 *                           terminal — per-candidate, multi-task frames).
 *  - search_*             → run the backend, send the JSON results, continue.
 *  - unknown              → terminal (Mac breaks the labeled loop; a bare break
 *                           would re-send the identical request up to 7 more times).
 */
async function dispatch(
  call: ToolCall,
  results: ExtractedTask[],
  deps: ExtractionLoopDeps
): Promise<Dispatch> {
  switch (call.name) {
    case 'no_task_found':
      // Terminal whether or not we already extracted (Mac returns accumulated).
      return { terminal: true }

    case 'extract_task': {
      const task = parseExtractTask(call.args)
      if (!task) {
        // Title failed validation. Recompute the specific error + word count for
        // the REJECTED message exactly as Mac does (TA:1106-1132).
        const title = typeof call.args['title'] === 'string' ? (call.args['title'] as string) : ''
        const words = wordCount(title)
        const error = validateTaskTitle(title, words) ?? 'Title is empty'
        return { terminal: false, result: buildRejectedResponse(error, title, words) }
      }
      results.push(task)
      return { terminal: false, result: buildExtractedResponse(task.title) }
    }

    case 'reject_task':
      return { terminal: false, result: REJECT_LOOK_AGAIN_RESPONSE }

    case 'search_similar': {
      const query = typeof call.args['query'] === 'string' ? (call.args['query'] as string) : ''
      const found = await deps.executeVectorSearch(query)
      return { terminal: false, result: encodeSearchResults(found) }
    }

    case 'search_keywords': {
      const query = typeof call.args['query'] === 'string' ? (call.args['query'] as string) : ''
      const found = await deps.executeKeywordSearch(query)
      return { terminal: false, result: encodeSearchResults(found) }
    }

    default:
      // Unknown tool → break the loop (Mac's `break toolLoop`).
      return { terminal: true }
  }
}

/**
 * Run the single-phase extraction loop over one frame. Composes the full user turn
 * (buildUserPrompt header + the assembled dedup/profile/goals context + the static
 * capture-policy trailer) and the JPEG, forces a tool call on iteration 0, then
 * dispatches up to 8 model calls, returning every ExtractedTask produced (possibly
 * empty). Never applies the confidence gate and never saves — that is the
 * assistant's job (Wave 3).
 *
 * Throws only on an unrecoverable transport error (geminiWire has already retried +
 * run the fallback model); the assistant treats that as "no tasks this cycle". A
 * session change fires `external`, which aborts in-flight HTTP and is also checked
 * at the top of each iteration for a clean early bail with the accumulated results.
 */
export async function runExtractionLoop(
  params: ExtractionLoopParams,
  deps: Partial<ExtractionLoopDeps> = {}
): Promise<ExtractedTask[]> {
  const d: ExtractionLoopDeps = {
    sendInitial: deps.sendInitial ?? sendInitialTurn,
    sendResponse: deps.sendResponse ?? sendToolResponseTurn,
    executeVectorSearch: deps.executeVectorSearch ?? executeVectorSearch,
    executeKeywordSearch: deps.executeKeywordSearch ?? executeKeywordSearch,
    assembleContext: deps.assembleContext ?? assembleTaskContext
  }

  const systemPrompt = params.systemPrompt ?? TASK_SYSTEM_PROMPT
  const external = params.external ?? getAbortSignal()
  const tool = TASK_TOOLS as GeminiTool
  const results: ExtractedTask[] = []

  // Full user turn: header + injected context + the static capture-policy trailer
  // (Mac composes these in TaskAssistant.swift:890-963). The context block already
  // ends each section with a blank line, so the trailer joins with the right spacing.
  const prompt =
    buildUserPrompt(params.app, params.today, params.isMessaging) +
    (await d.assembleContext(params.now)) +
    TASK_CAPTURE_POLICY_TRAILER

  // Iteration 0 — forced tool call, JPEG present. geminiWire keeps `contents`, which
  // we thread back through every response turn.
  const { turn, contents } = await d.sendInitial({
    session: params.session,
    systemPrompt,
    tool,
    external,
    prompt,
    imageBase64: params.imageBase64
  })
  let currentTurn = turn

  // callsMade counts model calls (the initial turn is #1). We may make at most
  // TASK_MAX_ITERS calls total, so at most TASK_MAX_ITERS-1 response turns.
  let callsMade = 1
  for (;;) {
    if (external?.aborted) break // session changed between turns → bail with what we have

    const call = currentTurn.toolCalls[0]
    if (!call) break // no tool call → stop (Mac: break)

    const outcome = await dispatch(call, results, d)
    if (outcome.terminal) break

    // A non-terminal call needs a follow-up turn. If the budget is spent, stop with
    // the accumulated results (Mac: the loop condition ends at iteration 8 — the
    // 8th call is dispatched, but no 9th call is made).
    if (callsMade >= TASK_MAX_ITERS) break

    currentTurn = await d.sendResponse({
      session: params.session,
      systemPrompt,
      tool,
      external,
      contents,
      call,
      result: outcome.result
    })
    callsMade++
  }

  return results
}
