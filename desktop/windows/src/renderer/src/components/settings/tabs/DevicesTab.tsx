import { useState, useEffect } from 'react'
import { Bluetooth, Cpu, Mic, Info, Loader, CheckCircle, AlertCircle, Radio } from 'lucide-react'
import { SettingRow } from '../SettingRow'

const SUPPORTED_DEVICES = [
  { name: 'Omi', description: 'Omi wearable AI device — voice capture, speaker, haptics', icon: '🎙️' },
  { name: 'OpenGlass', description: 'OpenGlass camera — video capture and visual context', icon: '👓' },
  { name: 'Frame', description: 'Brilliant Labs Frame AR glasses', icon: '🪄' },
  { name: 'Plaud', description: 'Plaud AI recording card', icon: '🃏' },
  { name: 'Bee', description: 'Bee AI wearable companion', icon: '🐝' }
]

type ScanState =
  | { phase: 'idle' }
  | { phase: 'scanning' }
  | { phase: 'found'; deviceName: string; deviceId: string }
  | { phase: 'cancelled' }
  | { phase: 'error'; message: string }
  | { phase: 'unavailable'; reason: string }

export function DevicesTab(): React.JSX.Element {
  const [btAvailable, setBtAvailable] = useState<boolean | null>(null)
  const [scan, setScan] = useState<ScanState>({ phase: 'idle' })

  useEffect(() => {
    // Check Web Bluetooth API availability at runtime
    if (typeof navigator !== 'undefined' && 'bluetooth' in navigator) {
      setBtAvailable(true)
    } else {
      setBtAvailable(false)
    }
  }, [])

  const handleScan = async (): Promise<void> => {
    if (!btAvailable) return
    setScan({ phase: 'scanning' })
    try {
      // Request any nearby BLE device — Electron routes this through the main
      // process `select-bluetooth-device` handler (native dialog). Returns a
      // BluetoothDevice with name + id. Full Omi pairing requires mobile app.
      type BleApi = { requestDevice: (opts: unknown) => Promise<{ name?: string; id: string }> }
      const nav = navigator as unknown as { bluetooth?: BleApi }
      if (!nav.bluetooth) {
        setScan({ phase: 'unavailable', reason: 'Web Bluetooth API not exposed' })
        setBtAvailable(false)
        return
      }
      const device = await nav.bluetooth.requestDevice({
        // acceptAllDevices discovers any nearby BLE peripheral.
        // Omi-specific service UUIDs are undocumented; discovery-only is honest.
        acceptAllDevices: true,
        optionalServices: []
      })
      setScan({
        phase: 'found',
        deviceName: device.name ?? 'Unknown BLE device',
        deviceId: device.id
      })
    } catch (e: unknown) {
      const err = e as Error
      if (err.name === 'NotFoundError' || err.message?.includes('cancel')) {
        // User dismissed the picker — not an error
        setScan({ phase: 'cancelled' })
      } else if (err.name === 'NotSupportedError') {
        setScan({ phase: 'unavailable', reason: 'Bluetooth not supported on this system' })
        setBtAvailable(false)
      } else {
        setScan({ phase: 'error', message: err.message ?? 'Unknown Bluetooth error' })
      }
    }
  }

  return (
    <>
      {/* Bluetooth availability banner */}
      {btAvailable === false && (
        <div className="mb-6 flex items-start gap-3 rounded-xl border border-blue-500/20 bg-blue-500/[0.07] px-4 py-3.5">
          <Bluetooth className="mt-0.5 h-4 w-4 shrink-0 text-blue-400" />
          <div>
            <p className="text-sm font-medium text-text-primary">
              Bluetooth discovery not available
            </p>
            <p className="mt-1 text-xs text-text-secondary">
              Web Bluetooth is not available in this environment. Use the{' '}
              <a
                href="https://www.omi.me"
                onClick={(e) => {
                  e.preventDefault()
                  window.open('https://www.omi.me')
                }}
                className="text-blue-400 underline"
              >
                Omi mobile app
              </a>{' '}
              to pair and configure your device.
            </p>
          </div>
        </div>
      )}

      {/* BLE Scan (only when API available) */}
      {btAvailable === true && (
        <SettingRow
          icon={Radio}
          title="Scan for nearby devices"
          subtitle={
            scan.phase === 'idle'
              ? 'Discover nearby Bluetooth LE devices. Full Omi firmware pairing requires the mobile app — this shows which devices are in range.'
              : scan.phase === 'scanning'
                ? 'Opening Bluetooth device picker…'
                : scan.phase === 'found'
                  ? `Discovered: ${scan.deviceName}`
                  : scan.phase === 'cancelled'
                    ? 'Scan cancelled.'
                    : scan.phase === 'error'
                      ? `Scan error: ${scan.message}`
                      : scan.phase === 'unavailable'
                        ? `Bluetooth unavailable: ${scan.reason}`
                        : ''
          }
          keywords="bluetooth scan ble device discover pair omi openglass"
          control={
            <div className="flex items-center gap-2">
              {scan.phase === 'scanning' && (
                <Loader className="h-4 w-4 animate-spin text-text-quaternary" />
              )}
              {scan.phase === 'found' && (
                <CheckCircle className="h-4 w-4 text-green-400" />
              )}
              {(scan.phase === 'error' || scan.phase === 'unavailable') && (
                <AlertCircle className="h-4 w-4 text-orange-400" />
              )}
              <button
                onClick={() => void handleScan()}
                disabled={scan.phase === 'scanning'}
                className="btn-ghost disabled:opacity-50"
              >
                {scan.phase === 'scanning'
                  ? 'Scanning…'
                  : scan.phase === 'found' || scan.phase === 'cancelled'
                    ? 'Scan again'
                    : 'Scan'}
              </button>
            </div>
          }
        >
          {scan.phase === 'found' && (
            <div className="mt-2 rounded-lg border border-green-500/20 bg-green-500/[0.07] px-3 py-2">
              <p className="text-xs font-medium text-green-400">{scan.deviceName}</p>
              <p className="mt-0.5 text-xs text-text-quaternary">
                ID: {scan.deviceId.slice(0, 16)}…
                {' · '}
                Discovery only — full Omi pairing requires the mobile app
              </p>
            </div>
          )}
        </SettingRow>
      )}

      {/* Supported device types */}
      <SettingRow
        icon={Bluetooth}
        title="Supported devices"
        subtitle="The following Omi-compatible devices can be paired via the mobile app and will sync conversation data to this Windows app automatically."
        keywords="bluetooth ble device pair omi openglass frame plaud bee hardware"
      >
        <div className="mt-2 space-y-1.5">
          {SUPPORTED_DEVICES.map((d) => (
            <div
              key={d.name}
              className="flex items-center gap-3 rounded-lg border border-white/[0.06] bg-white/[0.03] px-3 py-2.5"
            >
              <span className="shrink-0 text-lg" role="img" aria-label={d.name}>
                {d.icon}
              </span>
              <div className="min-w-0">
                <p className="text-sm font-medium text-text-primary">{d.name}</p>
                <p className="text-xs text-text-tertiary">{d.description}</p>
              </div>
            </div>
          ))}
        </div>
      </SettingRow>

      <SettingRow
        icon={Mic}
        title="Voice capture on Windows"
        subtitle="This app uses your PC's microphone directly — press the overlay shortcut or the 'New' button in Conversations to record. No hardware device is required on Windows."
        keywords="microphone record capture overlay"
      />

      <SettingRow
        icon={Cpu}
        title="Hardware integration roadmap"
        subtitle="Full BLE pairing (firmware updates, battery monitoring, live audio streaming) is planned for a future Windows release."
        keywords="roadmap ble bluetooth windows native coming soon"
      />

      <SettingRow
        icon={Info}
        title="Device setup documentation"
        keywords="docs setup pair guide"
        subtitle="Learn how to set up your Omi device and keep it synced across platforms."
        control={
          <button onClick={() => window.open('https://docs.omi.me')} className="btn-ghost">
            Docs
          </button>
        }
      />
    </>
  )
}
