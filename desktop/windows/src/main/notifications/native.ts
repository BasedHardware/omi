import { Notification } from 'electron'
import { getWindowsNotificationSettings } from './settings'
import type {
  WindowsNotificationChannel,
  WindowsNotificationSettings,
  WindowsNotificationTestKind,
  WindowsNotificationTestResult
} from '../../shared/types'

type NativeNotificationPayload = {
  title: string
  body: string
  silent?: boolean
}

const TEST_COPY: Record<WindowsNotificationTestKind, NativeNotificationPayload> = {
  system: {
    title: 'Omi notifications',
    body: 'Windows system notifications are working.'
  },
  focus: {
    title: 'Focus notification',
    body: 'Omi will let you know when focus changes need attention.'
  },
  tasks: {
    title: 'Task notification',
    body: 'Omi will notify you when it extracts a task.'
  },
  insights: {
    title: 'Insight notification',
    body: 'Omi will surface timely insights here.'
  },
  memories: {
    title: 'Memory notification',
    body: 'Omi will notify you when a useful memory is extracted.'
  },
  dailySummary: {
    title: 'Daily summary',
    body: 'Omi will send your daily recap at the selected time.'
  }
}

function channelEnabled(
  settings: WindowsNotificationSettings,
  channel: WindowsNotificationChannel
): boolean {
  return settings[channel].enabled
}

export function sendWindowsNativeNotification(
  channel: WindowsNotificationTestKind,
  payload: NativeNotificationPayload
): WindowsNotificationTestResult {
  const settings = getWindowsNotificationSettings()
  if (!settings.nativeEnabled) {
    return {
      ok: false,
      code: 'disabled',
      reason: 'Windows system notifications are turned off in Omi settings.'
    }
  }
  if (channel !== 'system' && !channelEnabled(settings, channel)) {
    return {
      ok: false,
      code: 'disabled',
      reason: `The ${channel} notification category is turned off.`
    }
  }
  if (!Notification.isSupported()) {
    return {
      ok: false,
      code: 'unsupported',
      reason: 'Native notifications are not supported in this Electron runtime.'
    }
  }

  try {
    const notification = new Notification({
      title: payload.title || 'Omi',
      body: payload.body,
      silent: payload.silent
    })
    notification.on('failed', (_event, error) => {
      console.warn('[notifications] native notification failed:', error)
    })
    notification.show()
    return { ok: true }
  } catch (e) {
    return {
      ok: false,
      code: 'failed',
      reason: (e as Error).message || 'Failed to show native notification.'
    }
  }
}

export function sendWindowsNotificationTest(
  kind: WindowsNotificationTestKind = 'system'
): WindowsNotificationTestResult {
  return sendWindowsNativeNotification(kind, TEST_COPY[kind])
}
