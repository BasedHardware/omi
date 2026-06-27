import { app } from 'electron'
import { getForegroundWindowInfo, subscribeForegroundChange } from '../usage/nativeForeground'
import { pickTarget } from './foregroundTargetLogic'

// The desktop-automation planner needs the window the user actually wants to act
// on — but by the time they type into Omi and hit Enter, OMI itself is the
// foreground window (and it's blocklisted). So we track the most recent
// foreground window whose owning process ISN'T Omi, and hand that to the
// snapshot. Without this the chat path can only ever see Omi's own UI.

let lastTargetHandle: string | null = null

function record(): void {
  try {
    lastTargetHandle = pickTarget(getForegroundWindowInfo(), app.getPath('exe'), lastTargetHandle)
  } catch {
    /* never let tracking throw */
  }
}

let unsubscribe: (() => void) | null = null
let pollTimer: NodeJS.Timeout | null = null

// Start tracking the last non-Omi foreground window. Event-driven via the
// foreground hook, with a coarse poll as a backstop. No-op off-Windows / if
// already running. Safe at startup.
export function startAutomationTargetTracker(): void {
  if (process.platform !== 'win32' || unsubscribe || pollTimer) return
  record()
  unsubscribe = subscribeForegroundChange(record)
  pollTimer = setInterval(record, 5_000)
}

export function stopAutomationTargetTracker(): void {
  if (unsubscribe) unsubscribe()
  if (pollTimer) clearInterval(pollTimer)
  unsubscribe = null
  pollTimer = null
}

// The handle (decimal string) the planner should snapshot, or null to fall back
// to the live foreground window.
export function getAutomationTargetHandle(): string | null {
  return lastTargetHandle
}
