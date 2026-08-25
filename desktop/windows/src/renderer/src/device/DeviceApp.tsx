import { useEffect, useRef } from 'react'
import { auth } from '../lib/firebase'
import { DeviceController } from './deviceController'
import { createWebBluetoothAccess } from './webBluetoothAccess'
import { DeviceListenSession } from './lane/deviceListenSession'
import { createBridgeLaneTransport } from './lane/bridgeLaneTransport'
import type { DeviceSettings } from '../../../shared/types'

// Root of the hidden device window (renderer #/device). No visible UI: it hosts
// the wearable stack — WebBluetooth transport, BLE audio decode, and the listen
// lane — and talks to the rest of the app only over the device bridge.
//
// Like the capture window it self-heals its Firebase auth, because the listen
// socket is opened with this window's token: when the main window reports an
// auth transition this window disagrees with, it reloads so the persisted
// session (and therefore the socket auth) is fresh.
export function DeviceApp(): React.JSX.Element {
  const controllerRef = useRef<DeviceController | null>(null)
  const reloadTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    let disposed = false
    let unsubscribe: (() => void) | null = null

    void (async () => {
      const settings: DeviceSettings = (await window.omi?.deviceGetSettings?.()) ?? {
        pairedDevice: null,
        autoReconnect: true,
        deviceListenEnabled: false
      }
      if (disposed) return
      let current = settings

      const controller = new DeviceController({
        bluetooth: createWebBluetoothAccess(),
        emit: (event) => window.omi?.deviceEmit?.(event),
        settings: () => current,
        saveSettings: async (patch) => {
          const next = await window.omi?.deviceSetSettings?.(patch)
          if (next) current = next
        },
        createLane: () =>
          new DeviceListenSession(createBridgeLaneTransport(), {
            onStateChange: (state) =>
              window.omi?.deviceEmit?.({ type: 'device-listen-state', state })
          })
      })
      controllerRef.current = controller

      unsubscribe =
        window.omi?.onDeviceCommand?.((cmd) => {
          if (cmd.type === 'device-settings') current = cmd.settings
          void controller.handleCommand(cmd)
        }) ?? null

      // Main holds commands until this fires, so it must come after the
      // command subscription is live.
      window.omi?.deviceEmit?.({ type: 'device-ready' })

      // A window that starts with a device already paired reconnects on its
      // own; the user paired it once and expects it to just work.
      if (current.pairedDevice !== null) {
        void controller.handleCommand({
          type: 'device-connect',
          deviceId: current.pairedDevice.id
        })
      }
    })()

    return () => {
      disposed = true
      unsubscribe?.()
      controllerRef.current?.dispose()
      controllerRef.current = null
    }
  }, [])

  useEffect(() => {
    return window.omi?.onDeviceCommand?.((cmd) => {
      if (cmd.type !== 'auth-changed') return
      const localUid = auth.currentUser?.uid ?? null
      // Compare uids, not just signed-in-ness: an account switch leaves both
      // sides signed in but must still refresh this window's socket auth.
      if (localUid === (cmd as { uid?: string | null }).uid) {
        if (reloadTimer.current) {
          clearTimeout(reloadTimer.current)
          reloadTimer.current = null
        }
        return
      }
      if (reloadTimer.current) return
      reloadTimer.current = setTimeout(() => {
        reloadTimer.current = null
        if (auth.currentUser?.uid === (cmd as { uid?: string | null }).uid) return
        window.location.reload()
      }, 1000)
    })
  }, [])

  return <></>
}
