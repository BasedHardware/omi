// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { render, cleanup, fireEvent, screen, waitFor } from '@testing-library/react'
import { DeviceTab } from './DeviceTab'
import { SettingsSearchProvider } from '../SettingsSearchProvider'
import type { DeviceEvent, DeviceSettings } from '../../../../../shared/types'

const deviceGetSettings = vi.fn()
const deviceSetSettings = vi.fn()
const deviceCommand = vi.fn()
const deviceSelect = vi.fn()
const onDeviceEvent = vi.fn()

let emit: (event: DeviceEvent) => void = () => undefined

const PAIRED = { id: 'dev-1', name: 'Omi CV1', type: 'omi' as const }

const SETTINGS = (over: Partial<DeviceSettings> = {}): DeviceSettings => ({
  pairedDevice: null,
  autoReconnect: true,
  deviceListenEnabled: false,
  ...over
})

const renderTab = async (): Promise<void> => {
  render(
    <SettingsSearchProvider>
      <DeviceTab />
    </SettingsSearchProvider>
  )
  await waitFor(() => expect(deviceGetSettings).toHaveBeenCalled())
}

beforeEach(() => {
  deviceGetSettings.mockReset().mockResolvedValue(SETTINGS())
  deviceSetSettings.mockReset().mockImplementation(async (patch) => SETTINGS(patch))
  deviceCommand.mockReset()
  deviceSelect.mockReset().mockResolvedValue(undefined)
  onDeviceEvent.mockReset().mockImplementation((cb: (e: DeviceEvent) => void) => {
    emit = cb
    return () => undefined
  })
  ;(globalThis as unknown as { window: { omi: unknown } }).window.omi = {
    deviceGetSettings,
    deviceSetSettings,
    deviceCommand,
    deviceSelect,
    onDeviceEvent
  }
})

afterEach(() => cleanup())

describe('DeviceTab', () => {
  it('offers pairing when nothing is paired', async () => {
    await renderTab()
    expect(screen.getByRole('button', { name: 'Pair device' })).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Forget' })).toBeNull()
  })

  it('pairing streams candidates and sends the pick back to unblock the chooser', async () => {
    await renderTab()
    fireEvent.click(screen.getByRole('button', { name: 'Pair device' }))
    expect(deviceCommand).toHaveBeenCalledWith({ type: 'device-pair' })
    expect(screen.getByText(/Looking for nearby devices/)).toBeTruthy()

    emit({
      type: 'device-candidates',
      candidates: [
        { deviceId: 'aa', deviceName: 'Omi CV1' },
        { deviceId: 'bb', deviceName: '' }
      ]
    })
    await screen.findByText('Omi CV1')
    // A device advertising no name still has to be selectable.
    expect(screen.getByText('Unnamed device')).toBeTruthy()

    fireEvent.click(screen.getByText('Omi CV1'))
    expect(deviceSelect).toHaveBeenCalledWith('aa')
  })

  it('cancelling the picker answers the chooser so the scan does not hang', async () => {
    await renderTab()
    fireEvent.click(screen.getByRole('button', { name: 'Pair device' }))
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(deviceSelect).toHaveBeenCalledWith(null)
  })

  it('ignores candidate events that arrive outside a pairing attempt', async () => {
    await renderTab()
    emit({ type: 'device-candidates', candidates: [{ deviceId: 'aa', deviceName: 'Omi CV1' }] })
    // A reconnect scan must not pop a device picker at the user.
    expect(screen.queryByText('Omi CV1')).toBeNull()
  })

  it('shows connection state, battery, and the forget action once paired', async () => {
    deviceGetSettings.mockResolvedValue(SETTINGS({ pairedDevice: PAIRED }))
    await renderTab()
    expect(screen.getByText(/Omi CV1 — Not connected/)).toBeTruthy()

    emit({ type: 'device-state', state: 'connected', device: PAIRED })
    await screen.findByText(/Omi CV1 — Connected/)
    expect(screen.queryByRole('button', { name: 'Connect' })).toBeNull()

    emit({ type: 'device-battery', level: 64 })
    await screen.findByText('64% remaining.')

    fireEvent.click(screen.getByRole('button', { name: 'Forget' }))
    expect(deviceCommand).toHaveBeenCalledWith({ type: 'device-forget' })
  })

  it('offers Connect while a paired device is disconnected', async () => {
    deviceGetSettings.mockResolvedValue(SETTINGS({ pairedDevice: PAIRED }))
    await renderTab()
    fireEvent.click(screen.getByRole('button', { name: 'Connect' }))
    expect(deviceCommand).toHaveBeenCalledWith({ type: 'device-connect', deviceId: 'dev-1' })
  })

  it('persists the reconnect and transcription toggles', async () => {
    await renderTab()
    fireEvent.click(screen.getByLabelText('Reconnect automatically'))
    await waitFor(() => expect(deviceSetSettings).toHaveBeenCalledWith({ autoReconnect: false }))

    fireEvent.click(screen.getByLabelText('Transcribe device audio'))
    await waitFor(() =>
      expect(deviceSetSettings).toHaveBeenCalledWith({ deviceListenEnabled: true })
    )
  })

  it('surfaces a degraded-audio warning and clears it on recovery', async () => {
    await renderTab()
    emit({ type: 'device-audio-degraded', degraded: true })
    await screen.findByText(/decoding poorly/)
    emit({ type: 'device-audio-degraded', degraded: false })
    await waitFor(() => expect(screen.queryByText(/decoding poorly/)).toBeNull())
  })

  it('clears the pairing row when the device is forgotten', async () => {
    deviceGetSettings.mockResolvedValue(SETTINGS({ pairedDevice: PAIRED }))
    await renderTab()
    emit({ type: 'device-forgotten' })
    await screen.findByRole('button', { name: 'Pair device' })
  })
})
