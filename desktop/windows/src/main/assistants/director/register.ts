/**
 * Director registration — idempotent, mirroring focus/register.ts: hooks the
 * assistant into the shared coordinator loop and reconciles visit state left
 * over from a previous process.
 */

import { registerAssistant } from '../core/coordinator'
import { contextDirectorDb } from '../../ipc/db'
import { reconcileInterruptedVisitsOn } from '../../ipc/contextBucketStore'
import { getDirectorAssistant } from './directorAssistant'
import { notificationSettingsSyncHttp, wireDirectorSessionReset } from './service'
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
  registerAssistant(getDirectorAssistant())
}
