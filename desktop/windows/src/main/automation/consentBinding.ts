import type { AutomationPlan, UiSnapshotWindow } from '../../shared/types'

/** Replace every renderer-asserted window identity with the native snapshot. */
export function bindPlanToWindow(plan: AutomationPlan, window: UiSnapshotWindow): AutomationPlan {
  const steps = plan.steps.map((step) =>
    step.type === 'focus_window' ? { ...step, windowRef: window.handle } : step
  )
  if (!steps.some((step) => step.type === 'focus_window')) {
    steps.unshift({ type: 'focus_window', windowRef: window.handle })
  }
  return {
    ...plan,
    targetWindow: window.title || window.processName,
    steps
  }
}

export function sameWindowIdentity(approved: UiSnapshotWindow, current: UiSnapshotWindow): boolean {
  return (
    approved.handle === current.handle &&
    approved.processName.toLowerCase() === current.processName.toLowerCase()
  )
}
