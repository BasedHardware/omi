// Wording for the device-storage row. Split out of DeviceTab so the tab file
// only exports its component (the fast-refresh rule).
import type { DeviceStorageState } from '../../../../../shared/types'

export const NO_STORAGE: DeviceStorageState = {
  phase: 'unknown',
  items: 0,
  estimatedSeconds: 0,
  recovered: 0,
  message: null
}

/** Rounded duration for a size hint. Never shown as an exact length: it comes
 *  from the codec's nominal frame size, not from decoding the audio. */
export function approximateDuration(seconds: number): string {
  if (seconds < 60) return 'under a minute'
  const minutes = Math.round(seconds / 60)
  if (minutes < 60) return `about ${minutes} minute${minutes === 1 ? '' : 's'}`
  const hours = Math.round(seconds / 360) / 10
  return `about ${hours} hour${hours === 1 ? '' : 's'}`
}

/** What the storage row says under its title. */
export function storageSubtitle(storage: DeviceStorageState, connected: boolean): string {
  if (!connected) return 'Connect your device to check what it recorded while it was away.'
  switch (storage.phase) {
    case 'unknown':
      return 'Checking what your device recorded while it was away.'
    case 'unsupported':
      return 'This device does not keep recordings of its own.'
    case 'empty':
      return storage.message ?? 'Your device has nothing waiting.'
    case 'recovering':
      return storage.message ?? 'Recovering.'
    case 'failed':
      return storage.message ?? 'Recovery could not start.'
    case 'available':
      return (
        storage.message ??
        `Your device is holding ${approximateDuration(storage.estimatedSeconds)} of audio it recorded while it was away. Recovering copies it here and uploads it as conversations.`
      )
  }
}
