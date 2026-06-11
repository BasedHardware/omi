import type { AutomationStep } from '../../../shared/types'

export { parseAutomationPlan } from '../../../main/automation/protocol'

// Strip the "a:"/"n:Type:" ref prefix down to a human label for the plan preview.
function refLabel(ref: string): string {
  if (ref.startsWith('a:')) return ref.slice(2)
  if (ref.startsWith('n:')) {
    const rest = ref.slice(2)
    const sep = rest.indexOf(':')
    return sep === -1 ? rest : rest.slice(sep + 1)
  }
  return ref
}

export function describeStep(step: AutomationStep): string {
  switch (step.type) {
    case 'focus_window':
      // windowRef is a numeric handle when we target the snapshotted window;
      // the card header already names the window, so keep this step generic.
      return /^\d+$/.test(step.windowRef) ? 'Bring the target window to the front' : `Focus window “${step.windowRef}”`
    case 'invoke_element':
      return `Click “${refLabel(step.elementRef)}”`
    case 'set_value':
      return `Type “${step.value}” into “${refLabel(step.elementRef)}”`
    case 'select_item':
      return `Select “${refLabel(step.elementRef)}”`
    case 'toggle':
      return `Toggle “${refLabel(step.elementRef)}” ${step.state ? 'on' : 'off'}`
    case 'send_keys':
      return `Type keys: ${step.keys}`
    case 'click':
      return step.elementRef ? `Click “${refLabel(step.elementRef)}”` : 'Click'
    case 'wait_for':
      return `Wait for “${refLabel(step.elementRef)}” (up to ${step.timeoutMs}ms)`
  }
}

export function describePlanSteps(steps: AutomationStep[]): string[] {
  return steps.map((s, i) => `${i + 1}. ${describeStep(s)}`)
}
