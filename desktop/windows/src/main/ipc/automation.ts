import { ipcMain, dialog, BrowserWindow } from 'electron'
import { automationBridge } from '../automation/bridge'
import { getAutomationTargetHandle } from '../automation/foregroundTarget'
import { bindPlanToWindow, sameWindowIdentity } from '../automation/consentBinding'
import type { AutomationPlan, AutomationStep, UiSnapshot } from '../../shared/types'

// Result of the native-dialog confirm flow. `canceled` distinguishes a user
// "Cancel" from an execution failure.
export type ConfirmRunResult = { ok: boolean; canceled?: boolean; message?: string }

// Human-readable, consent-relevant summary of a step for the native dialog.
// Built in MAIN from the real plan (not renderer-supplied text) so what the user
// approves is what runs. Element refs aren't human-friendly, so clicks are
// described generically; the typed value / keys (what matters for consent) shown.
function describeStepForDialog(step: AutomationStep, i: number): string {
  const n = `${i + 1}. `
  switch (step.type) {
    case 'focus_window':
      return `${n}Bring the target window to the front`
    case 'set_value':
      return `${n}Type “${step.value}”`
    case 'send_keys':
      return `${n}Press keys: ${step.keys}`
    case 'invoke_element':
    case 'click':
      return `${n}Click an element`
    case 'select_item':
      return `${n}Select an item`
    case 'toggle':
      return `${n}Turn a setting ${step.state ? 'on' : 'off'}`
    case 'wait_for':
      return `${n}Wait for an element`
    default:
      return `${n}${(step as { type: string }).type}`
  }
}

export function registerAutomationHandlers(): void {
  ipcMain.handle('automation:snapshot', async (_e, windowHandle?: string): Promise<UiSnapshot> => {
    return automationBridge.snapshot(windowHandle)
  })

  // The last non-Omi foreground window the planner should target (null → caller
  // falls back to the live foreground window).
  ipcMain.handle('automation:targetWindow', async (): Promise<string | null> => {
    return getAutomationTargetHandle()
  })

  // The only run path is the consent-gated automation:confirmRun below. The
  // former dialog-less 'automation:run' IPC was removed: it was exposed to the
  // renderer but had no legitimate caller, and let web content drive Windows UI
  // input with no approval. Per-step progress events aren't needed by the
  // confirm flow (it resolves once on completion).

  // Consent gate as a NATIVE Windows dialog (works identically from the main
  // window and the floating overlay, since it lives here in main). Shows the plan
  // and only runs it on explicit approval.
  ipcMain.handle(
    'automation:confirmRun',
    async (e, plan: AutomationPlan): Promise<ConfirmRunResult> => {
      const targetHandle = getAutomationTargetHandle()
      if (!targetHandle) return { ok: false, message: 'No trusted target window is available.' }
      const approvedSnapshot = await automationBridge.snapshot(targetHandle)
      if (!approvedSnapshot.ok) {
        return { ok: false, message: 'The target window could not be verified.' }
      }
      const boundPlan = bindPlanToWindow(plan, approvedSnapshot.window)
      const parent = BrowserWindow.fromWebContents(e.sender)
      const detail = [
        `In “${boundPlan.targetWindow}” (${approvedSnapshot.window.processName}):`,
        '',
        ...boundPlan.steps.map((s, i) => describeStepForDialog(s, i))
      ].join('\n')
      const opts = {
        type: 'question' as const,
        title: 'Omi — approve action',
        message: boundPlan.summary || `Omi wants to do something in “${boundPlan.targetWindow}”`,
        detail,
        buttons: ['Approve & run', 'Cancel'],
        defaultId: 0,
        cancelId: 1,
        noLink: true
      }
      const { response } = parent
        ? await dialog.showMessageBox(parent, opts)
        : await dialog.showMessageBox(opts)
      if (response !== 0) return { ok: false, canceled: true }
      const currentSnapshot = await automationBridge.snapshot(targetHandle)
      if (
        !currentSnapshot.ok ||
        !sameWindowIdentity(approvedSnapshot.window, currentSnapshot.window)
      ) {
        return { ok: false, message: 'The target window changed after approval.' }
      }
      const result = await automationBridge.run(boundPlan, () => {})
      return { ok: result.ok, message: result.message }
    }
  )
}
