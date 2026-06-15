import type { AutomationPlan, AutomationStep, UiaNode, UiSnapshot } from '../../../shared/types'
import { parseAutomationPlan } from './automationPlan'

export type CallLLM = (prompt: string) => Promise<string>

// Cheap, FREE pre-filter: only spend a UI snapshot + LLM call when the message
// even hints at acting on an app. Conservative on purpose — false negatives just
// fall through to ordinary chat, and a false positive only costs one snapshot.
const ACTION_KEYWORDS = [
  'send',
  'open',
  'click',
  'type',
  'reply',
  'create',
  'close',
  'fill',
  'submit',
  'search for',
  'navigate'
]

// Guidance QUESTIONS, not commands: the user is asking Omi where/what/how to act
// ("where should I click?", "what do I type here?", "how do I send this?"), not
// telling it to do the action. These must fall through to normal chat — where the
// always-on screen OCR can actually answer them — instead of hitting the planner,
// which can only turn imperatives into UI actions and errors out on a question.
// A leading wh-word (or "should I / do I") never starts an imperative command, so
// this cleanly separates "advise me about X" from "do X".
const GUIDANCE_QUESTION = /^\s*(where|what|which|how|why|when|who)\b|\b(should i|do i)\b/i

export function looksLikeAction(text: string): boolean {
  const lower = text.toLowerCase()
  if (GUIDANCE_QUESTION.test(lower)) return false
  return ACTION_KEYWORDS.some((k) => lower.includes(k))
}

// True when a chat reply is actually a raw automation-plan JSON leaking from the
// conversational backend. The Omi /v2/messages endpoint answers action-intent
// messages with plan-shaped JSON; when a message reaches chat WITHOUT going
// through our planner (e.g. a keyword-less follow-up like "again"), that JSON
// would otherwise render raw in the thread. Callers use this to suppress it.
export function looksLikeRawPlan(text: string): boolean {
  const s = text.trim()
  return s.startsWith('{') && /"steps"\s*:/.test(s) && /"targetWindow"\s*:/.test(s)
}

function snapshotForPrompt(snapshot: Extract<UiSnapshot, { ok: true }>): string {
  // Flatten the tree to ref/type/name lines — compact and LLM-referenceable.
  const lines: string[] = [`Window: ${snapshot.window.title} (${snapshot.window.processName})`]
  const walk = (els: typeof snapshot.elements): void => {
    for (const el of els) {
      if (el.patterns.length > 0 || el.name) {
        lines.push(`${el.ref} [${el.controlType}] "${el.name}" {${el.patterns.join(',')}}`)
      }
      if (el.children) walk(el.children)
    }
  }
  walk(snapshot.elements)
  return lines.join('\n')
}

// One combined round-trip: given the request + live UI, the model either
// declines (CHAT) or emits a plan. Folding the old separate intent-classifier
// call into this halves the LLM calls per action attempt — important because the
// desktop backend rate-limits aggressively and two back-to-back calls doubled
// the chance of a 429 that silently dropped the action.
const PLAN_PROMPT = (text: string, uiText: string, windowTitle: string): string =>
  [
    'You operate a Windows app on the user’s behalf via UI Automation.',
    'First decide: is this request an action you can perform on the UI below',
    '(clicking, typing, sending, opening something in this app)?',
    'If it is NOT — a question, casual chat, or not doable on this UI — reply with',
    'exactly the single word: CHAT',
    'Otherwise output ONLY a single raw JSON object — no prose, no fences:',
    '{"id":"<short>","summary":"<one sentence>","targetWindow":"<window title>",',
    ' "steps":[ ...ordered steps... ]}',
    'Each step is one of:',
    '  {"type":"focus_window","windowRef":"<title>"}',
    '  {"type":"invoke_element","elementRef":"<ref>"}',
    '  {"type":"set_value","elementRef":"<ref>","value":"<text>"}',
    '  {"type":"select_item","elementRef":"<ref>"}',
    '  {"type":"toggle","elementRef":"<ref>","state":true|false}',
    '  {"type":"send_keys","keys":"<text, named keys like {ENTER}{TAB} only — NO modifier chords>"}',
    '  {"type":"click","elementRef":"<ref>"}',
    '  {"type":"wait_for","elementRef":"<ref>","timeoutMs":<n>}',
    'Reference elements ONLY by the exact ref strings shown. Do not invent refs.',
    'To enter text, use set_value directly on a {value} element — do NOT click or',
    'invoke it first. Use invoke_element only on {invoke} elements (buttons/links).',
    `targetWindow must be "${windowTitle}".`,
    '',
    'UI elements:',
    uiText,
    '',
    `User request: ${text}`
  ].join('\n')

export type PlanResult =
  | { ok: true; plan: AutomationPlan }
  // 'chat' = not an action (or no valid plan) → fall through to normal chat.
  // 'error' = we wanted to plan but couldn't reach/parse the planner (e.g. the
  // backend 429'd or the snapshot failed) → the caller should SAY so rather than
  // silently answering an action request as chat.
  | { ok: false; kind: 'chat' | 'error'; reason: string }

export interface PlannerDeps {
  getSnapshot: () => Promise<UiSnapshot>
  callLLM: CallLLM
}

export async function planActions(text: string, deps: PlannerDeps): Promise<PlanResult> {
  let snapshot: UiSnapshot
  try {
    snapshot = await deps.getSnapshot()
  } catch (e) {
    return { ok: false, kind: 'error', reason: `snapshot threw: ${(e as Error).message}` }
  }
  if (!snapshot.ok) return { ok: false, kind: 'error', reason: `snapshot failed: ${snapshot.message}` }

  let raw: string
  try {
    raw = await deps.callLLM(PLAN_PROMPT(text, snapshotForPrompt(snapshot), snapshot.window.title))
  } catch (e) {
    return { ok: false, kind: 'error', reason: `planner call failed: ${(e as Error).message}` }
  }
  if (/^\s*CHAT\b/i.test(raw)) return { ok: false, kind: 'chat', reason: 'model declined (CHAT)' }
  const plan = parseAutomationPlan(raw)
  if (!plan) {
    // Distinguish a botched PLAN from a prose decline. Plan-shaped JSON (it has
    // "steps") that failed to validate is a failed action attempt → error: do
    // NOT fall through to chat, because the conversational backend answers an
    // action request with its OWN plan-shaped JSON, leaking raw JSON into the
    // thread. Plain prose with no plan shape means the model is just declining
    // or chatting → chat.
    const attemptedPlan = /"steps"\s*:/.test(raw)
    return {
      ok: false,
      kind: attemptedPlan ? 'error' : 'chat',
      reason: attemptedPlan ? 'planner returned an invalid plan' : 'no plan produced'
    }
  }
  // Validate every step against the snapshot the plan was built from.
  const patternsByRef = collectPatterns(snapshot.elements)
  const fixed: AutomationStep[] = []
  for (const step of plan.steps) {
    const ref = (step as { elementRef?: string }).elementRef
    // Hallucinated ref — every elementRef must be one the snapshot exposed, or
    // it can't resolve at execute time.
    if (typeof ref === 'string' && ref.length > 0 && !patternsByRef.has(ref)) {
      return { ok: false, kind: 'error', reason: `planner referenced unknown element "${ref}"` }
    }
    const pats = ref ? patternsByRef.get(ref) ?? [] : []
    // invoke_element needs the Invoke pattern, but the model often "clicks" a
    // text box (value pattern, no invoke) before typing — which throws
    // "Invoke not supported" at execute time. A real mouse click (the `click`
    // step → el.Click()) works on ANY element, so fall back to it: the action
    // then succeeds instead of failing.
    if (step.type === 'invoke_element' && !pats.includes('invoke')) {
      fixed.push({ type: 'click', elementRef: ref as string })
      continue
    }
    // set_value/select_item/toggle can't be salvaged without their pattern.
    const required: Record<string, string> = {
      set_value: 'value',
      select_item: 'selectionItem',
      toggle: 'toggle'
    }
    const need = required[step.type]
    if (need && !pats.includes(need)) {
      return {
        ok: false,
        kind: 'error',
        reason: `planner step "${step.type}" targets an element without the "${need}" capability`
      }
    }
    fixed.push(step)
  }
  // Guarantee the target window is frontmost before any element step. Element
  // refs resolve against the FOREGROUND window at execute time, and the instant
  // the user clicks Approve, Omi is foreground — so a plan that lacks a leading
  // focus step (the model includes one only inconsistently) would resolve refs
  // against Omi and fail "element not found". Focus the EXACT window we
  // snapshotted, by handle (more reliable than the model's title), dropping any
  // model-supplied focus step.
  const focusStep: AutomationStep = { type: 'focus_window', windowRef: snapshot.window.handle }
  const rest = fixed[0]?.type === 'focus_window' ? fixed.slice(1) : fixed
  return { ok: true, plan: { ...plan, steps: [focusStep, ...rest] } }
}

// Map of element ref → its UIA patterns, for validating planned steps.
function collectPatterns(elements: UiaNode[]): Map<string, string[]> {
  const map = new Map<string, string[]>()
  const walk = (els: UiaNode[]): void => {
    for (const el of els) {
      map.set(el.ref, el.patterns)
      if (el.children) walk(el.children)
    }
  }
  walk(elements)
  return map
}
