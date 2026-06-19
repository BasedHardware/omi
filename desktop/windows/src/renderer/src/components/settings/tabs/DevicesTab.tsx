import { useState, useEffect, useRef, useCallback } from 'react'
import { Bluetooth, Cpu, Mic, Info, Loader, CheckCircle, AlertCircle, Radio } from 'lucide-react'
import { SettingRow } from '../SettingRow'

// ── Minimal Web Bluetooth type stubs ────────────────────────────────────────
// TypeScript's dom lib doesn't include Web Bluetooth. These stubs cover only
// what we use: requestDevice, gatt.connect/disconnect, getPrimaryService,
// getCharacteristic, readValue, and the gattserverdisconnected event.
interface BleChar {
  readValue(): Promise<DataView>
}
interface BleService {
  getCharacteristic(c: string): Promise<BleChar>
}
interface BleServer {
  connected: boolean
  connect(): Promise<BleServer>
  disconnect(): void
  getPrimaryService(s: string): Promise<BleService>
}
interface BleDevice {
  id: string
  name?: string
  gatt?: BleServer
  addEventListener(type: 'gattserverdisconnected', cb: () => void): void
  removeEventListener(type: 'gattserverdisconnected', cb: () => void): void
}
interface BleApi {
  requestDevice(opts: unknown): Promise<BleDevice>
}

// Standard GATT short names (Web Bluetooth spec)
const BATTERY_SERVICE = 'battery_service'
const BATTERY_LEVEL = 'battery_level'
const DEVICE_INFO_SERVICE = 'device_information'
const MANUFACTURER_NAME = 'manufacturer_name_string'
const MODEL_NUMBER = 'model_number_string'

const LAST_DEVICE_KEY = 'omi.ble.lastDevice.v1'
type LastDevice = { name: string; id: string; seenAt: number }

function saveLastDevice(name: string, id: string): void {
  try {
    localStorage.setItem(LAST_DEVICE_KEY, JSON.stringify({ name, id, seenAt: Date.now() }))
  } catch { /* quota */ }
}

function loadLastDevice(): LastDevice | null {
  try {
    const raw = localStorage.getItem(LAST_DEVICE_KEY)
    return raw ? (JSON.parse(raw) as LastDevice) : null
  } catch {
    return null
  }
}

const SUPPORTED_DEVICES = [
  { name: 'Omi', description: 'Omi wearable AI device — voice capture, speaker, haptics', icon: '🎙️' },
  { name: 'OpenGlass', description: 'OpenGlass camera — video capture and visual context', icon: '👓' },
  { name: 'Frame', description: 'Brilliant Labs Frame AR glasses', icon: '🪄' },
  { name: 'Plaud', description: 'Plaud AI recording card', icon: '🃏' },
  { name: 'Bee', description: 'Bee AI wearable companion', icon: '🐝' }
]

type Phase =
  | 'idle'
  | 'scanning'
  | 'connecting'
  | 'reading'
  | 'connected'
  | 'disconnected'
  | 'cancelled'
  | 'error'
  | 'unavailable'

export function DevicesTab(): React.JSX.Element {
  const [btAvailable, setBtAvailable] = useState<boolean | null>(null)
  const [phase, setPhase] = useState<Phase>('idle')
  const [deviceName, setDeviceName] = useState('')
  const [deviceId, setDeviceId] = useState('')
  // battery: number = level 0-100; null = not yet read; -1 = service missing
  const [battery, setBattery] = useState<number | null>(null)
  const [manufacturer, setManufacturer] = useState<string | null>(null)
  const [model, setModel] = useState<string | null>(null)
  const [errorMsg, setErrorMsg] = useState('')
  const [unavailableReason, setUnavailableReason] = useState('')
  const [lastDevice, setLastDevice] = useState<LastDevice | null>(null)

  // Keep the live BluetoothDevice object in a ref — not state — so event
  // listener registration/removal doesn't cause extra renders.
  const deviceRef = useRef<BleDevice | null>(null)

  useEffect(() => {
    setBtAvailable(typeof navigator !== 'undefined' && 'bluetooth' in navigator)
    setLastDevice(loadLastDevice())
  }, [])

  const onDisconnected = useCallback(() => {
    setPhase('disconnected')
  }, [])

  const handleDisconnect = (): void => {
    deviceRef.current?.gatt?.disconnect()
    // gattserverdisconnected event fires synchronously → onDisconnected flips phase
  }

  const resetDeviceInfo = (): void => {
    setBattery(null)
    setManufacturer(null)
    setModel(null)
    setErrorMsg('')
    setUnavailableReason('')
  }

  const handleScan = async (): Promise<void> => {
    if (!btAvailable) return
    setPhase('scanning')
    resetDeviceInfo()

    const nav = navigator as unknown as { bluetooth?: BleApi }
    if (!nav.bluetooth) {
      setPhase('unavailable')
      setUnavailableReason('Web Bluetooth API not exposed in this environment')
      setBtAvailable(false)
      return
    }

    try {
      // Request any BLE device. optionalServices lets us read battery and device-info
      // services post-connection without restricting which devices appear in the picker.
      const device = await nav.bluetooth.requestDevice({
        acceptAllDevices: true,
        optionalServices: [BATTERY_SERVICE, DEVICE_INFO_SERVICE]
      })

      const name = device.name ?? 'Unknown BLE device'
      setDeviceName(name)
      setDeviceId(device.id)
      saveLastDevice(name, device.id)
      setLastDevice({ name, id: device.id, seenAt: Date.now() })

      // Swap in the new device listener
      const prev = deviceRef.current
      if (prev) prev.removeEventListener('gattserverdisconnected', onDisconnected)
      deviceRef.current = device
      device.addEventListener('gattserverdisconnected', onDisconnected)

      if (!device.gatt) {
        // Some environments expose a BluetoothDevice without GATT support
        setPhase('connected')
        return
      }

      setPhase('connecting')
      const server = await device.gatt.connect()
      setPhase('reading')

      // ── Battery Service (standard GATT 0x180F / 0x2A19) ────────────────
      // Confirmed present in iOS OmiBleManager.swift (CBUUID "2A19") and
      // Android OmiBleManager.kt (UUID "00002a19-..."). Any device exposing
      // standard battery GATT will return a 0–100 integer.
      try {
        const bSvc = await server.getPrimaryService(BATTERY_SERVICE)
        const bChar = await bSvc.getCharacteristic(BATTERY_LEVEL)
        const bVal = await bChar.readValue()
        setBattery(bVal.getUint8(0))
      } catch {
        setBattery(-1) // -1 = service not available on this device
      }

      // ── Device Information Service (standard GATT 0x180A) ───────────────
      try {
        const diSvc = await server.getPrimaryService(DEVICE_INFO_SERVICE)
        try {
          const mfrChar = await diSvc.getCharacteristic(MANUFACTURER_NAME)
          const mfrVal = await mfrChar.readValue()
          setManufacturer(new TextDecoder().decode(mfrVal.buffer as ArrayBufferLike))
        } catch { /* characteristic not exposed by this device */ }
        try {
          const mdlChar = await diSvc.getCharacteristic(MODEL_NUMBER)
          const mdlVal = await mdlChar.readValue()
          setModel(new TextDecoder().decode(mdlVal.buffer as ArrayBufferLike))
        } catch { /* characteristic not exposed by this device */ }
      } catch { /* device_information service absent */ }

      setPhase('connected')
    } catch (e: unknown) {
      const err = e as Error
      if (err.name === 'NotFoundError' || err.message?.includes('cancel')) {
        setPhase('cancelled')
      } else if (err.name === 'NotSupportedError') {
        setPhase('unavailable')
        setUnavailableReason('Bluetooth not supported on this system')
        setBtAvailable(false)
      } else {
        setPhase('error')
        setErrorMsg(err.message ?? 'Unknown Bluetooth error')
      }
    }
  }

  const isActive = phase === 'connected' || phase === 'reading' || phase === 'connecting'
  const isBusy = phase === 'scanning' || phase === 'connecting' || phase === 'reading'

  const subtitleText = (): string => {
    if (phase === 'idle') {
      return lastDevice
        ? `Last connected: ${lastDevice.name} — scan to reconnect.`
        : 'Discover and connect to a nearby Bluetooth LE device to read battery and device info.'
    }
    if (phase === 'scanning') return 'Opening Bluetooth device picker…'
    if (phase === 'connecting') return `Connecting to ${deviceName}…`
    if (phase === 'reading') return `Connected — reading battery and device info…`
    if (phase === 'connected') return `Connected to ${deviceName}`
    if (phase === 'disconnected') return `Disconnected from ${deviceName}. Scan to reconnect.`
    if (phase === 'cancelled') return 'Scan cancelled.'
    if (phase === 'error') return `Error: ${errorMsg}`
    if (phase === 'unavailable') return `Unavailable: ${unavailableReason}`
    return ''
  }

  return (
    <>
      {/* Bluetooth unavailable banner */}
      {btAvailable === false && (
        <div className="mb-6 flex items-start gap-3 rounded-xl border border-blue-500/20 bg-blue-500/[0.07] px-4 py-3.5">
          <Bluetooth className="mt-0.5 h-4 w-4 shrink-0 text-blue-400" />
          <div>
            <p className="text-sm font-medium text-text-primary">Bluetooth not available</p>
            <p className="mt-1 text-xs text-text-secondary">
              Web Bluetooth is not available in this environment. Use the{' '}
              <a
                href="#"
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

      {/* Scan + Connect row (only when BT API available) */}
      {btAvailable === true && (
        <SettingRow
          icon={Radio}
          title="Scan and connect"
          subtitle={subtitleText()}
          keywords="bluetooth scan ble device connect pair omi openglass battery info"
          control={
            <div className="flex items-center gap-2">
              {isBusy && <Loader className="h-4 w-4 animate-spin text-text-quaternary" />}
              {phase === 'connected' && <CheckCircle className="h-4 w-4 text-green-400" />}
              {(phase === 'error' || phase === 'unavailable') && (
                <AlertCircle className="h-4 w-4 text-orange-400" />
              )}
              {isActive && (
                <button onClick={handleDisconnect} className="btn-ghost text-red-400">
                  Disconnect
                </button>
              )}
              <button
                onClick={() => void handleScan()}
                disabled={isBusy}
                className="btn-ghost disabled:opacity-50"
              >
                {isBusy
                  ? 'Scanning…'
                  : isActive || phase === 'disconnected' || phase === 'cancelled'
                    ? 'Scan again'
                    : 'Scan'}
              </button>
            </div>
          }
        >
          {/* Device info card — shown while connecting, reading, or connected */}
          {isActive && (
            <div className="mt-2 space-y-1.5 rounded-lg border border-green-500/20 bg-green-500/[0.07] px-3 py-2.5">
              <div className="flex items-center justify-between">
                <p className="text-sm font-medium text-green-400">{deviceName}</p>
                {battery !== null && battery >= 0 && (
                  <span className="text-xs text-text-secondary">{battery}% battery</span>
                )}
                {battery === -1 && (
                  <span className="text-xs text-text-quaternary">Battery unavailable</span>
                )}
                {battery === null && phase === 'reading' && (
                  <span className="text-xs text-text-quaternary">Reading…</span>
                )}
              </div>
              {(manufacturer != null || model != null) && (
                <p className="text-xs text-text-secondary">
                  {[manufacturer, model].filter(Boolean).join(' · ')}
                </p>
              )}
              <p className="text-xs text-text-quaternary">
                ID: {deviceId.length > 20 ? `${deviceId.slice(0, 20)}…` : deviceId}
                {' · '}Full Omi pairing and OTA require the mobile app
              </p>
            </div>
          )}
        </SettingRow>
      )}

      {/* Supported device list */}
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
        subtitle="Full BLE pairing, firmware OTA, and live audio streaming from device are planned for a future Windows release. Standard GATT Battery and Device Information services are read now when available."
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
