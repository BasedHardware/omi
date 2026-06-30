// Pure helpers for the Settings microphone picker and for applying the chosen
// input to getUserMedia. Dependency-free (no firebase/electron/DOM globals at
// import) so they're unit-testable under node Vitest.

export type MicOption = { deviceId: string; label: string }

/**
 * Build the `audio` constraint for getUserMedia from a stored mic preference.
 * No selection (undefined / '') → `true` (let the OS pick its default). A
 * selection → pin that EXACT device so the user's chosen mic — not the OS
 * default — is the one that feeds transcription. (Callers fall back to `true`
 * if the exact device is gone; see omiListenClient.)
 */
export function micAudioConstraints(deviceId: string | undefined): MediaTrackConstraints | true {
  const id = (deviceId ?? '').trim()
  return id ? { deviceId: { exact: id } } : true
}

/**
 * Reduce enumerateDevices() output to the selectable audio inputs for the picker.
 * Filters to `audioinput`, drops the synthetic 'default'/'communications'
 * aggregate ids (they alias a real device and would show as duplicates — the
 * picker offers an explicit "System default" entry instead), and labels unnamed
 * devices (labels are blank until mic permission is granted).
 */
export function micOptions(devices: MediaDeviceInfo[]): MicOption[] {
  const inputs = devices.filter((d) => d.kind === 'audioinput' && d.deviceId)
  const real = inputs.filter(
    (d) => d.deviceId !== 'default' && d.deviceId !== 'communications'
  )
  // If only the aggregate ids exist (rare), fall back to whatever we have so the
  // picker isn't empty.
  const list = real.length > 0 ? real : inputs
  return list.map((d, i) => ({ deviceId: d.deviceId, label: d.label || `Microphone ${i + 1}` }))
}

/**
 * True when a previously-saved selection is no longer among the available inputs
 * (e.g. the mic was unplugged). The picker uses this to show the stale id as
 * "Unavailable" rather than silently rendering the OS default as if chosen.
 */
export function isSelectionAvailable(deviceId: string | undefined, options: MicOption[]): boolean {
  const id = (deviceId ?? '').trim()
  if (!id) return true // "System default" is always available.
  return options.some((o) => o.deviceId === id)
}
