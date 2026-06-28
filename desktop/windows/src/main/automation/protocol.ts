import type { AutomationPlan, AutomationStep } from '../../shared/types'

// Helper stdio opcodes (request frame: [uint32 LE len][1 byte opcode][JSON]).
export const OP_SNAPSHOT = 1
export const OP_STEP = 2
export const OP_HELLO = 3

// Bumped whenever the wire shape changes; bridge asserts a match on spawn.
export const PROTOCOL_VERSION = 1

// Snapshot prune caps — mirrored as constants in the C# helper.
export const MAX_SNAPSHOT_NODES = 400
export const MAX_SNAPSHOT_DEPTH = 12

const STEP_TYPES = new Set<AutomationStep['type']>([
  'focus_window',
  'invoke_element',
  'set_value',
  'select_item',
  'toggle',
  'send_keys',
  'click',
  'wait_for'
])

// Stable element address. AutomationId is preferred (stable, app-assigned);
// otherwise controlType + visible name. Resolved live at execute time.
export function encodeRef(el: { automationId: string; controlType: string; name: string }): string {
  if (el.automationId) return `a:${el.automationId}`
  return `n:${el.controlType}:${el.name}`
}

export type DecodedRef =
  | { kind: 'automationId'; value: string }
  | { kind: 'nameType'; controlType: string; name: string }

export function decodeRef(ref: string): DecodedRef | null {
  if (ref.startsWith('a:')) return { kind: 'automationId', value: ref.slice(2) }
  if (ref.startsWith('n:')) {
    const rest = ref.slice(2)
    const sep = rest.indexOf(':')
    if (sep === -1) return null
    return { kind: 'nameType', controlType: rest.slice(0, sep), name: rest.slice(sep + 1) }
  }
  return null
}

// Extract the first balanced JSON object from arbitrary model text (tolerates
// prose, ```fences```, and trailing chars). Mirrors localAgentProtocol's parser.
function firstJsonObject(text: string): string | null {
  const start = text.indexOf('{')
  if (start === -1) return null
  let depth = 0
  let inStr = false
  let esc = false
  for (let i = start; i < text.length; i++) {
    const ch = text[i]
    if (inStr) {
      if (esc) esc = false
      else if (ch === '\\') esc = true
      else if (ch === '"') inStr = false
      continue
    }
    if (ch === '"') inStr = true
    else if (ch === '{') depth++
    else if (ch === '}') {
      depth--
      if (depth === 0) return text.slice(start, i + 1)
    }
  }
  return null
}

// Canonical step type keyed by its underscore-stripped, lowercased form. Models
// routinely emit "focuswindow"/"setValue" instead of "focus_window"/"set_value";
// normalizing here turns an otherwise-valid plan into a usable one rather than
// silently rejecting it.
const CANONICAL_STEP_TYPE = new Map<string, AutomationStep['type']>(
  [...STEP_TYPES].map((t) => [t.replace(/_/g, ''), t])
)

function canonicalStepType(t: unknown): AutomationStep['type'] | null {
  if (typeof t !== 'string') return null
  return CANONICAL_STEP_TYPE.get(t.replace(/_/g, '').toLowerCase()) ?? null
}

// Validate + normalize one step. Returns the step with a canonical `type`, or
// null if the type is unrecognized even after normalization.
function coerceStep(s: unknown): AutomationStep | null {
  if (!s || typeof s !== 'object') return null
  const type = canonicalStepType((s as { type?: unknown }).type)
  if (!type) return null
  return { ...(s as Record<string, unknown>), type } as AutomationStep
}

// Parse a plan from model output. Returns null on anything malformed: no JSON,
// missing fields, empty steps, or any unknown step type. Structural validation
// only — capability/allowlist checks live in capabilities.ts, ref existence in
// the planner (it alone holds the snapshot).
export function parseAutomationPlan(text: string): AutomationPlan | null {
  const json = firstJsonObject(text)
  if (!json) return null
  let obj: unknown
  try {
    obj = JSON.parse(json)
  } catch {
    return null
  }
  const o = obj as Partial<AutomationPlan>
  if (typeof o.id !== 'string' || typeof o.summary !== 'string') return null
  if (typeof o.targetWindow !== 'string') return null
  if (!Array.isArray(o.steps) || o.steps.length === 0) return null
  const steps: AutomationStep[] = []
  for (const raw of o.steps) {
    const step = coerceStep(raw)
    if (!step) return null
    steps.push(step)
  }
  return { id: o.id, summary: o.summary, targetWindow: o.targetWindow, steps }
}
