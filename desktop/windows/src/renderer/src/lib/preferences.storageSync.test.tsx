// @vitest-environment jsdom
import { describe, it, expect } from 'vitest'
import { getPreferences, onPreferencesChange } from './preferences'

const KEY = 'omi-windows-prefs-v1'

// localStorage is shared across same-origin windows, but setPreferences only
// notifies its own window. The `storage` event (fired in OTHER windows) is how the
// capture window learns of a continuousRecording flip made in the main window.

describe('preferences cross-window storage sync', () => {
  it('refreshes the cache and notifies subscribers on a matching storage event', () => {
    // Simulate another window having written a new value to localStorage.
    localStorage.setItem(KEY, JSON.stringify({ ...getPreferences(), continuousRecording: true }))
    let notified: { continuousRecording?: boolean } | null = null
    const unsub = onPreferencesChange((p) => (notified = p))
    window.dispatchEvent(new StorageEvent('storage', { key: KEY }))
    expect(getPreferences().continuousRecording).toBe(true)
    expect(notified).not.toBeNull()
    expect(notified!.continuousRecording).toBe(true)
    unsub()
  })

  it('ignores storage events for unrelated keys', () => {
    const before = getPreferences().continuousRecording
    window.dispatchEvent(new StorageEvent('storage', { key: 'some-other-key' }))
    expect(getPreferences().continuousRecording).toBe(before)
  })
})
