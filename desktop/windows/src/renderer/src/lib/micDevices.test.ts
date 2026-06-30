import { describe, it, expect } from 'vitest'
import { micAudioConstraints, micOptions, isSelectionAvailable } from './micDevices'

// Minimal MediaDeviceInfo-shaped fixtures (only the fields the helpers read).
function dev(kind: MediaDeviceKind, deviceId: string, label = ''): MediaDeviceInfo {
  return { kind, deviceId, label, groupId: 'g', toJSON: () => ({}) } as MediaDeviceInfo
}

describe('micAudioConstraints', () => {
  it('returns true (OS default) when no device is selected', () => {
    expect(micAudioConstraints(undefined)).toBe(true)
    expect(micAudioConstraints('')).toBe(true)
    expect(micAudioConstraints('   ')).toBe(true)
  })

  it('pins the exact device when one is selected', () => {
    expect(micAudioConstraints('mic-abc')).toEqual({ deviceId: { exact: 'mic-abc' } })
  })
})

describe('micOptions', () => {
  it('keeps only real audio inputs and drops aggregate ids', () => {
    const devices = [
      dev('audioinput', 'default', 'Default - Headset'),
      dev('audioinput', 'communications', 'Communications - Headset'),
      dev('audioinput', 'real-1', 'Headset Mic'),
      dev('audioinput', 'real-2', 'Webcam Mic'),
      dev('audiooutput', 'spk-1', 'Speakers'),
      dev('videoinput', 'cam-1', 'Webcam')
    ]
    expect(micOptions(devices)).toEqual([
      { deviceId: 'real-1', label: 'Headset Mic' },
      { deviceId: 'real-2', label: 'Webcam Mic' }
    ])
  })

  it('labels unnamed devices (pre-permission) by index', () => {
    const devices = [dev('audioinput', 'real-1', ''), dev('audioinput', 'real-2', '')]
    expect(micOptions(devices)).toEqual([
      { deviceId: 'real-1', label: 'Microphone 1' },
      { deviceId: 'real-2', label: 'Microphone 2' }
    ])
  })

  it('falls back to aggregate ids if no real devices exist', () => {
    const devices = [dev('audioinput', 'default', 'Default')]
    expect(micOptions(devices)).toEqual([{ deviceId: 'default', label: 'Default' }])
  })

  it('returns empty when there are no audio inputs', () => {
    expect(micOptions([dev('audiooutput', 'spk-1', 'Speakers')])).toEqual([])
  })
})

describe('isSelectionAvailable', () => {
  const options = [
    { deviceId: 'real-1', label: 'Headset Mic' },
    { deviceId: 'real-2', label: 'Webcam Mic' }
  ]

  it('treats "System default" (no selection) as always available', () => {
    expect(isSelectionAvailable(undefined, options)).toBe(true)
    expect(isSelectionAvailable('', options)).toBe(true)
  })

  it('is true when the selected device is present', () => {
    expect(isSelectionAvailable('real-2', options)).toBe(true)
  })

  it('is false when the selected device is gone (unplugged)', () => {
    expect(isSelectionAvailable('real-3', options)).toBe(false)
    expect(isSelectionAvailable('real-1', [])).toBe(false)
  })
})
