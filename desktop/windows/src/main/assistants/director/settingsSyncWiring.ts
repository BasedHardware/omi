/**
 * Production wiring for the notification-settings sync coordinator: the
 * appSettings-backed revision journal, the backend HTTP pair, the
 * local-mutation listener (with hydrate-loop protection), and the
 * session-poll reconcile at startup (the repo's bring-up idiom for services
 * that need a relayed session).
 *
 * Windows deviation from mac, deliberate: the PATCH always carries `enabled`.
 * Mac omits it when the master key was never locally written, protecting a
 * first-launch migration push from clobbering another client; Windows has no
 * migration push — the first PATCH only ever happens on a real user mutation,
 * which always carries a real local value.
 */

import { getAppSettings, onAppSettingsChanged, setAppSettings } from '../../appSettings'
import { getBackendSession } from '../core/session'
import { NotificationSettingsSyncCoordinator } from './notificationSettingsSync'

// Fetch indirection so tests can inject; production uses the director's
// authenticated api fetch (set below at wire time).
export interface SettingsSyncHttp {
  get(): Promise<{ enabled: boolean; frequency: number }>
  patch(body: {
    enabled?: boolean
    frequency: number
  }): Promise<{ enabled: boolean; frequency: number }>
}

let hydrating = false

function journalBegin(): number {
  const next = getAppSettings().notificationSettingsSyncRevision + 1
  setAppSettings({ notificationSettingsSyncRevision: next, notificationSettingsPendingSync: true })
  return next
}

export function createSettingsSyncCoordinator(
  http: SettingsSyncHttp
): NotificationSettingsSyncCoordinator {
  return new NotificationSettingsSyncCoordinator({
    signedIn: () => getBackendSession() !== null,
    readLocal: () => {
      const s = getAppSettings()
      return { enabled: s.notificationsEnabled, frequency: s.notificationFrequency }
    },
    writeLocal: (pair) => {
      hydrating = true
      try {
        setAppSettings({
          notificationsEnabled: pair.enabled,
          notificationFrequency: pair.frequency
        })
      } finally {
        hydrating = false
      }
    },
    journal: {
      revision: () => getAppSettings().notificationSettingsSyncRevision,
      pending: () => getAppSettings().notificationSettingsPendingSync,
      begin: journalBegin,
      complete: (revision) => {
        if (getAppSettings().notificationSettingsSyncRevision === revision) {
          setAppSettings({ notificationSettingsPendingSync: false })
        }
      }
    },
    http,
    setRetryTimer: (fn, ms) => setTimeout(fn, ms),
    clearRetryTimer: (handle) => clearTimeout(handle as NodeJS.Timeout)
  })
}

const SESSION_POLL_INTERVAL_MS = 5_000
const SESSION_POLL_MAX_TRIES = 60

let wired = false

/** Wire the mutation listener and the startup reconcile. Idempotent. */
export function wireNotificationSettingsSync(http: SettingsSyncHttp): void {
  if (wired) return
  wired = true
  const coordinator = createSettingsSyncCoordinator(http)

  let lastPair = {
    enabled: getAppSettings().notificationsEnabled,
    frequency: getAppSettings().notificationFrequency
  }
  onAppSettingsChanged((settings) => {
    if (hydrating) {
      lastPair = {
        enabled: settings.notificationsEnabled,
        frequency: settings.notificationFrequency
      }
      return
    }
    if (
      settings.notificationsEnabled === lastPair.enabled &&
      settings.notificationFrequency === lastPair.frequency
    ) {
      return
    }
    lastPair = { enabled: settings.notificationsEnabled, frequency: settings.notificationFrequency }
    const revision = journalBegin()
    void coordinator.enqueue(
      { enabled: settings.notificationsEnabled, frequency: settings.notificationFrequency },
      revision
    )
  })

  // Startup reconcile once a session is relayed (the tasks bring-up idiom).
  let tries = 0
  const poll = (): void => {
    if (getBackendSession() !== null) {
      void coordinator.reconcile()
      return
    }
    tries += 1
    if (tries < SESSION_POLL_MAX_TRIES) setTimeout(poll, SESSION_POLL_INTERVAL_MS)
  }
  poll()
}
