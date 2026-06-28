// Payment guard — Cortex's agent runs PC-control actions autonomously in the
// background, but anything that looks like a payment / checkout / purchase must
// stop and ask the user to step in. Pure + testable so the rule is auditable.
import type { AutomationPlan, AutomationStep } from './types'

// Keywords that signal a money-moving / checkout context. Matched case-insensitively
// against the plan summary, target window title, typed values and element refs.
const PAYMENT_PATTERNS: RegExp[] = [
  /\bpay(ment|ments|ing)?\b/i,
  /\bcheckout\b/i,
  /\bbuy now\b/i,
  /\bplace (the )?order\b/i,
  /\bcomplete (the )?(purchase|order)\b/i,
  /\bpurchase\b/i,
  /\bsubscribe\b/i,
  /\bcard number\b/i,
  /\bcredit card\b/i,
  /\bcvv\b|\bcvc\b/i,
  /\bexpiry\b/i,
  /\bbilling\b/i,
  /\bpaypal\b/i,
  /\bapple pay\b|\bgoogle pay\b/i,
  /\bwire transfer\b|\bbank transfer\b/i,
  /\bconfirm (and )?pay\b/i,
  /\b\$\d|\€\d|\£\d/ // a price right next to a digit
]

function stepText(step: AutomationStep): string {
  const parts: string[] = [step.type]
  const s = step as Record<string, unknown>
  for (const k of ['value', 'keys', 'elementRef', 'windowRef']) {
    if (typeof s[k] === 'string') parts.push(s[k] as string)
  }
  return parts.join(' ')
}

/** Aggregate searchable text for a plan (summary, target window, all steps). */
export function planText(plan: AutomationPlan): string {
  return [plan.summary ?? '', plan.targetWindow ?? '', ...plan.steps.map(stepText)].join(' \n ')
}

/**
 * True when a plan is payment-sensitive and must require explicit user
 * confirmation before running (overriding autonomous background execution).
 */
export function isPaymentSensitive(plan: AutomationPlan): boolean {
  const text = planText(plan)
  return PAYMENT_PATTERNS.some((re) => re.test(text))
}
