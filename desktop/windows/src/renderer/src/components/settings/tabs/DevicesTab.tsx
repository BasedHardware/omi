import { Bluetooth, Cpu, Mic, Info } from 'lucide-react'
import { SettingRow } from '../SettingRow'

// Device families that macOS supports, from DeviceType.swift.
// Listed for parity visibility — Windows cannot pair via Bluetooth yet.
const SUPPORTED_DEVICES = [
  {
    name: 'Omi',
    description: 'Omi wearable AI device — voice capture, speaker, haptics',
    icon: '🎙️'
  },
  {
    name: 'OpenGlass',
    description: 'OpenGlass camera — video capture and visual context',
    icon: '👓'
  },
  {
    name: 'Frame',
    description: 'Brilliant Labs Frame AR glasses',
    icon: '🪄'
  },
  {
    name: 'Plaud',
    description: 'Plaud AI recording card',
    icon: '🃏'
  },
  {
    name: 'Bee',
    description: 'Bee AI wearable companion',
    icon: '🐝'
  }
]

export function DevicesTab(): React.JSX.Element {
  return (
    <>
      {/* Status banner */}
      <div className="mb-6 flex items-start gap-3 rounded-xl border border-blue-500/20 bg-blue-500/[0.07] px-4 py-3.5">
        <Bluetooth className="mt-0.5 h-4 w-4 shrink-0 text-blue-400" />
        <div>
          <p className="text-sm font-medium text-text-primary">
            Bluetooth device pairing is not yet available on Windows
          </p>
          <p className="mt-1 text-xs text-text-secondary">
            The Windows app currently connects through your phone or macOS device. Native Windows
            Bluetooth pairing requires a BLE bridge module — it is on the roadmap. Use the{' '}
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

      {/* How to sync */}
      <SettingRow
        icon={Mic}
        title="Voice capture on Windows"
        subtitle="This app uses your PC's microphone directly — press the overlay shortcut or the 'New' button in Conversations to record. No hardware device is required on Windows."
        keywords="microphone record capture overlay"
      />

      {/* Roadmap info */}
      <SettingRow
        icon={Cpu}
        title="Hardware integration roadmap"
        subtitle="Native Windows Bluetooth support is planned. When available, it will enable direct BLE pairing, live audio streaming from Omi hardware, battery monitoring, and firmware updates."
        keywords="roadmap ble bluetooth windows native coming soon"
      />

      {/* Docs link */}
      <SettingRow
        icon={Info}
        title="Device setup documentation"
        keywords="docs setup pair guide"
        subtitle="Learn how to set up your Omi device and keep it synced across platforms."
        control={
          <button
            onClick={() => window.open('https://docs.omi.me')}
            className="btn-ghost"
          >
            Docs
          </button>
        }
      />
    </>
  )
}
