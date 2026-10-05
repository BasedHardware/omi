// Routing seam for the RN local agent.
//
// `localAgent.ts` decides three things: task, reminder, or chat. Its own regexes
// are good at slot filling — stripping "add a task:" and leaving "pay the electric
// bill" — and poor at routing, because they only fire on a verb the user happened
// to type. "put the electric bill on my list" and "I need to remember to call the
// dentist" both fall through to chat.
//
// So this module owns only the *routing* decision and delegates extraction back to
// `interpretCommand()`. That split is deliberate:
//
//   router  -> which of {task, reminder, chat}
//   regexes -> the title, and "in N minutes"
//
// The router returns an action NAME and never a title, so composing them keeps
// each component doing the thing it is measurably good at.
//
// ## Why a 22M embedder rather than the 1B model `runAgent()` was built for
//
// Measured on a Samsung SM-A145F (Exynos 3830, 3.5 GB RAM): a 270M
// function-calling LiteRT-LM bundle routes at 22% with 72% refusals, 3120 ms and
// 983 MB peak RSS. MiniLM-L6-v2 over the same prompts: 67% held-out, 594 ms,
// 285 MB. The generator was failing at routing, not generation.
//
// This action set is also a better fit than it looks. The router's measured weak
// spot is antonym pairs — "switch the torch on" vs "off" sit at cosine 0.949,
// because sentence embeddings encode topic and not polarity. task / reminder /
// chat contains no such pair, so the known limitation does not apply here.
//
// Reference: google-ai-edge/litert-samples PR #383, issue #382.

import { interpretCommand, minutesFrom, type AgentAction } from './localAgent'

/** The routing decision, which is all this module owns. */
export type Route = 'create_task' | 'create_reminder' | 'chat'

/**
 * What a native router must provide. Implemented for real by an Android module
 * running LiteRT CompiledModel; stubbed in tests so the composition is testable
 * without a device.
 */
export interface RouteProvider {
  /** Resolves the utterance to one of `Route`, or null if it declined. */
  route(text: string): Promise<{ route: Route; margin: number; declined: boolean } | null>
}

export type RouteOutcome =
  | { source: 'router'; decision: AgentAction; margin: number }
  | { source: 'heuristic'; decision: AgentAction; reason: string }

/**
 * Routes with `provider`, then fills slots with the existing heuristics.
 *
 * Degradation is deliberate and ordered:
 *   1. provider declines (thin margin / out of domain) -> heuristic decides.
 *   2. provider throws or is absent -> heuristic decides.
 *   3. router says chat -> chat, even if a regex would have matched. A confident
 *      "this is just a question" must beat a keyword hit, or the router buys
 *      nothing over the regexes it is meant to replace.
 */
export async function routeWithProvider(
  text: string,
  provider?: RouteProvider | null
): Promise<RouteOutcome> {
  const fallback = (reason: string): RouteOutcome => ({
    source: 'heuristic',
    decision: interpretCommand(text),
    reason,
  })

  if (!provider) return fallback('no provider')

  let routed: { route: Route; margin: number; declined: boolean } | null = null
  try {
    routed = await provider.route(text)
  } catch {
    return fallback('provider threw')
  }
  if (!routed) return fallback('provider returned null')
  if (routed.declined) return fallback(`declined (margin ${routed.margin.toFixed(3)})`)

  // Slot filling is the regex layer's job, not the router's.
  const heuristic = interpretCommand(text)

  if (routed.route === 'chat') {
    return { source: 'router', decision: { kind: 'chat', text }, margin: routed.margin }
  }

  // The router committed to task-or-reminder. If the regexes could not find a
  // title, we have a routing decision with nothing to act on. Degrade to the
  // heuristic rather than invent a title: an empty title is a silent no-op the
  // user cannot debug.
  if (heuristic.kind === 'chat') {
    return {
      source: 'heuristic',
      decision: heuristic,
      reason: `router said ${routed.route} but no title could be extracted`,
    }
  }

  // Trust the router on which kind, the regexes on the payload. When they agree
  // there is nothing to reconcile; when they disagree the router wins, because
  // that is the part it was added to improve.
  return {
    source: 'router',
    decision:
      routed.route === 'create_reminder'
        ? { kind: 'create_reminder', title: titleOf(heuristic), minutesFromNow: minutesFrom(text) }
        : { kind: 'create_task', title: titleOf(heuristic) },
    margin: routed.margin,
  }
}

function titleOf(a: AgentAction): string {
  return a.kind === 'chat' ? '' : a.title
}

/**
 * Prototype bank for the native side. Kept here so the routing contract is
 * reviewable in one place: the native module reads these from the app, and a
 * change to intent vocabulary is a change to this list rather than to Kotlin.
 *
 * Unlike the Android probe, this set deliberately contains no antonym pair, so
 * the embedding router's polarity limitation does not apply.
 */
export const ROUTE_PROTOTYPES: Record<Route, string[]> = {
  create_task: [
    'Save this to my task list.',
    'Add a task to my list.',
    'Write down a task for me.',
    'Put this on my list.',
    'I need to do this later.',
    'Add this to my todos.',
    'Make a note of this as a task.',
    'Track this so it stays on my radar.',
  ],
  create_reminder: [
    'Set a reminder so I remember.',
    'Remind me about this in a bit.',
    'Ping me later about this.',
    'I want an alarm for this.',
    'Set a timer to remind me.',
    'Nudge me about this soon.',
    'Schedule a reminder for this.',
  ],
  chat: [
    'Ask a question and get an answer.',
    'Recall something from our conversations.',
    'Search my memories.',
    'What did we discuss about this?',
    'Answer a question about my notes.',
    'Tell me what I said earlier.',
  ],
}
/**
 * Out-of-domain phrasing, so the router has something to decline toward.
 *
 * Without this the decline class has no prototypes and the abstain threshold
 * cannot fire: an argmax over three routes will always pick one. Kept next to
 * ROUTE_PROTOTYPES so both banks are reviewed together.
 */
export const OUT_OF_DOMAIN_PROTOTYPES: string[] = [
  'what is the weather',
  'play some music',
  'who won the match',
  'how do i tie a knot',
  'what time is it',
  'translate this to french',
  'tell me a joke',
  'set an alarm for six in the morning',
]
