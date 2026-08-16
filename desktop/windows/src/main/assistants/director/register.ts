/**
 * Director registration — idempotent, mirroring focus/register.ts: hooks the
 * assistant into the shared coordinator loop and reconciles visit state left
 * over from a previous process.
 */

import { powerMonitor } from 'electron'
import { registerAssistant } from '../core/coordinator'
import { contextDirectorDb } from '../../ipc/db'
import { reconcileInterruptedVisitsOn } from '../../ipc/contextBucketStore'
import { getDirectorAssistant } from './directorAssistant'
import {
  currentTrackedFrame,
  directorPipelineEnabled,
  directorVisits,
  notificationSettingsSyncHttp,
  wireDirectorSessionReset
} from './service'
import { wireNotificationSettingsSync } from './settingsSyncWiring'

let registered = false

export function registerDirectorAssistant(): void {
  if (registered) return
  registered = true
  wireDirectorSessionReset()
  wireNotificationSettingsSync(notificationSettingsSyncHttp)
  try {
    reconcileInterruptedVisitsOn(contextDirectorDb(), Date.now())
  } catch (e) {
    console.warn('[director] startup visit reconcile failed:', e)
  }
  // Sleep/lock interrupts the active visit; wake/unlock reopens the
  // still-frontmost context (mac's interrupt/rearm pair). The interrupt is
  // guarded against events older than the visit inside the coordinator, and
  // both are no-ops while the pipeline is off (no active visit exists).
  const interrupt = (): void => {
    void directorVisits.interruptForSleep(Date.now())
  }
  const rearm = (): void => {
    if (!directorPipelineEnabled()) return
    const frame = currentTrackedFrame()
    if (frame === null) return
    void directorVisits.rearmAfterSystemResume({
      toApp: frame.appName,
      toWindowTitle: frame.windowTitle,
      handles: [],
      processName: null,
      departingFrameId: frame.frameId
    })
  }
  powerMonitor.on('suspend', interrupt)
  powerMonitor.on('lock-screen', interrupt)
  powerMonitor.on('resume', rearm)
  powerMonitor.on('unlock-screen', rearm)
  registerAssistant(getDirectorAssistant())
}
