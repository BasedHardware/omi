// Wearable device settings tab. Mac reference: the DeviceProvider surface —
// though macOS never shipped a pairing pane, so this is where Windows goes
// past parity: pairing, live status, battery, auto-reconnect, and streaming
// device audio into transcription all live here.
//
// Machinery: the hidden device window owns WebBluetooth and the BLE stack; this
// tab only sends bridge commands and renders the events that come back. Pairing
// is a two-step handshake because Chromium answers device selection in main —
// "Pair" starts a scan, main streams the candidate list here, and the user's
// pick is sent back to unblock requestDevice().
import { useCallback, useEffect, useRef, useState } from 'react'
import { Bluetooth, BatteryMedium, RefreshCw, AudioLines, HardDriveDownload } from 'lucide-react'
import type {
  DeviceSettings,
  DeviceStorageState,
  WearableConnectionState,
  WearableDeviceCandidate,
  WearableDeviceInfo
} from '../../../../../shared/types'
import { toast } from '../../../lib/toast'
import { NO_STORAGE, storageSubtitle } from './deviceStorageFormat'
import { SettingRow } from '../SettingRow'
import { Toggle } from '../Toggle'

const STATE_LABELS: Record<WearableConnectionState, string> = {
  idle: 'Not connected',
  scanning: 'Looking for devices',
  connecting: 'Connecting',
  connected: 'Connected',
  reconnecting: 'Reconnecting',
  error: 'Disconnected'
}

const DEFAULT_SETTINGS: DeviceSettings = {
  pairedDevice: null,
  autoReconnect: true,
  deviceListenEnabled: false
}

export function DeviceTab(): React.JSX.Element {
  const [settings, setSettings] = useState<DeviceSettings>(DEFAULT_SETTINGS)
  const [state, setState] = useState<WearableConnectionState>('idle')
  const [connected, setConnected] = useState<WearableDeviceInfo | null>(null)
  const [candidates, setCandidates] = useState<WearableDeviceCandidate[] | null>(null)
  const [battery, setBattery] = useState<number | null>(null)
  const [degraded, setDegraded] = useState(false)
  const [storage, setStorage] = useState<DeviceStorageState>(NO_STORAGE)
  const pairing = useRef(false)

  useEffect(() => {
    void window.omi?.deviceGetSettings?.().then((s) => s && setSettings(s))
    // The hidden host may have connected long before Settings was opened, so
    // ask it to republish; subscribing alone would show a connected device as
    // disconnected until something changed.
    window.omi?.deviceCommand?.({ type: 'device-request-state' })
    return window.omi?.onDeviceEvent?.((event) => {
      switch (event.type) {
        case 'device-state':
          setState(event.state)
          setConnected(event.device)
          // The chooser list is only meaningful while a scan is open.
          if (event.state !== 'scanning') setCandidates(null)
          return
        case 'device-candidates':
          if (pairing.current) setCandidates(event.candidates)
          return
        case 'device-paired':
          pairing.current = false
          setCandidates(null)
          setSettings((prev) => ({ ...prev, pairedDevice: event.device }))
          toast(`Paired with ${event.device.name}`)
          return
        case 'device-forgotten':
          setSettings((prev) => ({ ...prev, pairedDevice: null }))
          setBattery(null)
          setStorage(NO_STORAGE)
          return
        case 'device-battery':
          setBattery(event.level)
          return
        case 'device-audio-degraded':
          setDegraded(event.degraded)
          return
        case 'device-storage':
          setStorage(event.storage)
          return
        case 'device-error':
          pairing.current = false
          toast(event.message, { tone: 'warn' })
      }
    })
  }, [])

  const patch = useCallback(async (next: Partial<DeviceSettings>): Promise<void> => {
    // Optimistic: main sanitizes and returns the authoritative value.
    setSettings((prev) => ({ ...prev, ...next }))
    const saved = await window.omi?.deviceSetSettings?.(next)
    if (saved) setSettings(saved)
  }, [])

  const startPairing = (): void => {
    pairing.current = true
    setCandidates([])
    window.omi?.deviceCommand?.({ type: 'device-pair' })
  }

  const pick = (deviceId: string | null): void => {
    setCandidates(null)
    if (deviceId === null) pairing.current = false
    void window.omi?.deviceSelect?.(deviceId)
  }

  const paired = settings.pairedDevice
  const isConnected = state === 'connected'

  return (
    <>
      <SettingRow
        icon={Bluetooth}
        dot={isConnected ? 'on' : paired ? 'off' : undefined}
        title="Omi device"
        subtitle={
          paired
            ? `${paired.name} — ${STATE_LABELS[state]}${
                connected && connected.id !== paired.id ? ` (${connected.name})` : ''
              }`
            : 'Pair an Omi, Bee, Limitless, PLAUD, Fieldy, Friend or Frame wearable to capture conversations without your laptop microphone.'
        }
        keywords="bluetooth ble wearable pendant pair device omi bee limitless plaud fieldy friend frame necklace"
        control={
          paired ? (
            <div className="flex items-center gap-2">
              {!isConnected && (
                <button
                  type="button"
                  onClick={() =>
                    window.omi?.deviceCommand?.({ type: 'device-connect', deviceId: paired.id })
                  }
                  className="rounded-md bg-white/10 px-3 py-1.5 text-sm text-white hover:bg-white/15"
                >
                  Connect
                </button>
              )}
              <button
                type="button"
                onClick={() => window.omi?.deviceCommand?.({ type: 'device-forget' })}
                className="rounded-md bg-white/10 px-3 py-1.5 text-sm text-white hover:bg-white/15"
              >
                Forget
              </button>
            </div>
          ) : (
            <button
              type="button"
              onClick={startPairing}
              disabled={state === 'scanning'}
              className="rounded-md bg-white/10 px-3 py-1.5 text-sm text-white hover:bg-white/15 disabled:opacity-50"
            >
              {state === 'scanning' ? 'Scanning…' : 'Pair device'}
            </button>
          )
        }
      >
        {candidates !== null && (
          <div className="mt-3 space-y-1">
            {candidates.length === 0 ? (
              <p className="text-sm text-text-tertiary">
                Looking for nearby devices. Make sure yours is on and close by.
              </p>
            ) : (
              candidates.map((candidate) => (
                <button
                  key={candidate.deviceId}
                  type="button"
                  onClick={() => pick(candidate.deviceId)}
                  className="flex w-full items-center justify-between rounded-md bg-white/[0.06] px-3 py-2 text-left text-sm text-white hover:bg-white/10"
                >
                  <span>{candidate.deviceName || 'Unnamed device'}</span>
                  <span className="text-xs text-text-tertiary">Select</span>
                </button>
              ))
            )}
            <button
              type="button"
              onClick={() => pick(null)}
              className="mt-1 text-xs text-text-tertiary hover:text-white"
            >
              Cancel
            </button>
          </div>
        )}
      </SettingRow>

      {paired && (
        <SettingRow
          icon={BatteryMedium}
          title="Battery"
          subtitle={
            battery === null
              ? 'Connect the device to read its battery level.'
              : `${battery}% remaining.`
          }
          keywords="battery charge level device wearable"
        />
      )}

      {paired && storage.phase !== 'unsupported' && (
        <SettingRow
          icon={HardDriveDownload}
          dot={storage.phase === 'available' ? 'on' : undefined}
          title="Recordings on your device"
          subtitle={storageSubtitle(storage, isConnected)}
          keywords="storage sdcard offline recordings recover sync device memory ring buffer"
          control={
            isConnected && storage.phase === 'recovering' ? (
              <button
                type="button"
                onClick={() => window.omi?.deviceCommand?.({ type: 'device-storage-cancel' })}
                className="rounded-md bg-white/10 px-3 py-1.5 text-sm text-white hover:bg-white/15"
              >
                Stop
              </button>
            ) : isConnected && storage.phase === 'available' ? (
              <button
                type="button"
                onClick={() => window.omi?.deviceCommand?.({ type: 'device-storage-recover' })}
                className="rounded-md bg-white/10 px-3 py-1.5 text-sm text-white hover:bg-white/15"
              >
                Recover
              </button>
            ) : undefined
          }
          note={
            storage.phase === 'recovering' ? (
              <span className="text-text-tertiary">
                Keep your device close by until this finishes. Nothing is removed from it until the
                audio is safely stored here.
              </span>
            ) : undefined
          }
        />
      )}

      <SettingRow
        icon={RefreshCw}
        dot={settings.autoReconnect ? 'on' : 'off'}
        title="Reconnect automatically"
        subtitle="Reconnect to your paired device whenever it comes back in range."
        keywords="reconnect automatic bluetooth range device"
        control={
          <Toggle
            on={settings.autoReconnect}
            onChange={(next) => void patch({ autoReconnect: next })}
            label="Reconnect automatically"
          />
        }
      />

      <SettingRow
        icon={AudioLines}
        dot={settings.deviceListenEnabled ? 'on' : 'off'}
        title="Transcribe device audio"
        subtitle="Stream audio from your wearable into conversations. Your laptop microphone keeps working for everything else."
        keywords="transcribe listen device audio conversation wearable streaming"
        note={
          degraded ? (
            <span className="text-amber-300">
              Audio is decoding poorly right now, so transcripts may be incomplete.
            </span>
          ) : undefined
        }
        control={
          <Toggle
            on={settings.deviceListenEnabled}
            onChange={(next) => void patch({ deviceListenEnabled: next })}
            label="Transcribe device audio"
          />
        }
      />
    </>
  )
}
