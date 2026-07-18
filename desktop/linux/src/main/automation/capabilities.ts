import type { AutomationPlan, AutomationStep } from '../../shared/types'

export type ValidationResult = { ok: true } | { ok: false; reason: string }

// Raw-coordinate clicking is brittle and unsafe; off by default in v1.
const ALLOW_RAW_COORDINATE_CLICK = false

// Windows whose UI must never be driven (security prompts, lock screen, our own
// windows). Matched case-insensitively as a substring of the target title.
const BLOCKLISTED_WINDOW_SUBSTRINGS = [
  'windows security',
  'user account control',
  'sign in',
  'lock screen',
  'credential',
  'task manager',
  'omi for windows'
]

// Upper bound for wait_for. Kept BELOW the bridge's per-request timeout
// (REQUEST_TIMEOUT_MS = 8000) so a long wait can't silently trip the bridge
// into recycling the helper mid-wait.
const MAX_WAIT_FOR_MS = 7000

// send_keys grammar: printable text plus a small whitelist of named keys in
// {BRACES}. Modifier-chord syntax (^ % + #) is forbidden outright so no step
// can fire OS-level chords like Win+R or Alt+F4.
const ALLOWED_NAMED_KEYS = new Set([
  'ENTER',
  'TAB',
  'ESC',
  'BACKSPACE',
  'DELETE',
  'UP',
  'DOWN',
  'LEFT',
  'RIGHT',
  'HOME',
  'END',
  'SPACE'
])
const FORBIDDEN_MODIFIER_CHARS = ['^', '%', '+', '#']

function validateSendKeys(keys: string): ValidationResult {
  keys = keys.normalize('NFKC')
  for (const c of FORBIDDEN_MODIFIER_CHARS) {
    if (keys.includes(c)) return { ok: false, reason: `modifier chord "${c}" not allowed` }
  }
  // Validate every {NAMED} token.
  const tokenRe = /\{([^}]*)\}/g
  let m: RegExpExecArray | null
  while ((m = tokenRe.exec(keys)) !== null) {
    if (!ALLOWED_NAMED_KEYS.has(m[1])) {
      return { ok: false, reason: `named key {${m[1]}} not allowed` }
    }
  }
  // Reject an unmatched '{' or '}'.
  if ((keys.match(/\{/g)?.length ?? 0) !== (keys.match(/\}/g)?.length ?? 0)) {
    return { ok: false, reason: 'unbalanced braces in send_keys' }
  }
  return { ok: true }
}

function nonEmpty(s: string | undefined, field: string): ValidationResult {
  return s && s.trim().length > 0 ? { ok: true } : { ok: false, reason: `${field} is empty` }
}

export function validateStep(step: AutomationStep): ValidationResult {
  switch (step.type) {
    case 'focus_window':
      return nonEmpty(step.windowRef, 'windowRef')
    case 'invoke_element':
    case 'select_item':
      return nonEmpty(step.elementRef, 'elementRef')
    case 'toggle':
      return nonEmpty(step.elementRef, 'elementRef')
    case 'set_value': {
      const r = nonEmpty(step.elementRef, 'elementRef')
      if (!r.ok) return r
      return nonEmpty(step.value, 'value')
    }
    case 'wait_for':
      if (!step.elementRef || !step.elementRef.trim())
        return { ok: false, reason: 'elementRef is empty' }
      return step.timeoutMs > 0 && step.timeoutMs <= MAX_WAIT_FOR_MS
        ? { ok: true }
        : { ok: false, reason: 'timeoutMs out of range' }
    case 'send_keys':
      return validateSendKeys(step.keys)
    case 'click':
      if (step.elementRef && step.elementRef.trim()) return { ok: true }
      if (step.point && ALLOW_RAW_COORDINATE_CLICK) return { ok: true }
      return { ok: false, reason: 'click requires elementRef (raw-point click disabled)' }
    default:
      return { ok: false, reason: `unknown step type ${(step as { type: string }).type}` }
  }
}

export function validatePlan(plan: AutomationPlan): ValidationResult {
  const t = nonEmpty(plan.targetWindow, 'targetWindow')
  if (!t.ok) return t
  const target = plan.targetWindow.toLowerCase()
  for (const sub of BLOCKLISTED_WINDOW_SUBSTRINGS) {
    if (target.includes(sub)) return { ok: false, reason: `target window "${plan.targetWindow}" is blocklisted` }
  }
  for (let i = 0; i < plan.steps.length; i++) {
    const r = validateStep(plan.steps[i])
    if (!r.ok) return { ok: false, reason: `step ${i}: ${r.reason}` }
  }
  return { ok: true }
}
