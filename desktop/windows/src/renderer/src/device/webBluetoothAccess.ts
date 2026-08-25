/**
 * navigator.bluetooth adapter. Chromium answers requestDevice() through main's
 * 'select-bluetooth-device' handler, so a "chooser" here is really: ask for a
 * device, and main either auto-answers with the remembered id (reconnect) or
 * streams candidates to Settings and waits for the user's pick.
 */

import {
  ALL_OPTIONAL_SERVICE_UUIDS,
  BEE_UUIDS,
  FIELDY_UUIDS,
  FRAME_UUIDS,
  FRIEND_PENDANT_UUIDS,
  LIMITLESS_UUIDS,
  OMI_UUIDS,
  PLAUD_UUIDS
} from './protocol/uuids'
import { WebBluetoothPhysicalDriver, type BluetoothDeviceLike } from './transport/blePhysicalDriver'
import type { BluetoothAccess } from './deviceController'

interface BluetoothLike {
  requestDevice(options: {
    filters?: Array<{ services?: string[]; namePrefix?: string }>
    optionalServices?: string[]
    acceptAllDevices?: boolean
  }): Promise<BluetoothDeviceLike>
  getDevices?: () => Promise<BluetoothDeviceLike[]>
}

/** Every family's advertised service, so a supported device is always offered. */
const DEVICE_SERVICE_UUIDS: string[] = [
  OMI_UUIDS.mainService,
  BEE_UUIDS.service,
  FIELDY_UUIDS.service,
  FRIEND_PENDANT_UUIDS.service,
  LIMITLESS_UUIDS.service,
  FRAME_UUIDS.service,
  PLAUD_UUIDS.service
]

const advertisedServices = (device: BluetoothDeviceLike): string[] => {
  // WebBluetooth does not expose the advertisement after selection, so the
  // detection falls back to the device name plus the services we asked for.
  void device
  return []
}

export function createWebBluetoothAccess(
  bluetooth: BluetoothLike | undefined = (navigator as unknown as { bluetooth?: BluetoothLike })
    .bluetooth
): BluetoothAccess {
  return {
    requestDevice: async () => {
      if (bluetooth === undefined) {
        throw new Error('Bluetooth is not available on this system.')
      }
      // acceptAllDevices with optionalServices: main filters the candidate list
      // it shows, and a wearable whose advertisement omits its service UUID
      // (several do until connected) would be invisible behind a service filter.
      const device = await bluetooth.requestDevice({
        acceptAllDevices: true,
        optionalServices: [...ALL_OPTIONAL_SERVICE_UUIDS]
      })
      if (device === undefined || device === null) return null
      return {
        driver: new WebBluetoothPhysicalDriver(device),
        serviceUuids: advertisedServices(device)
      }
    },
    reacquire: async (deviceId: string) => {
      if (bluetooth?.getDevices === undefined) return null
      const granted = await bluetooth.getDevices()
      const match = granted.find((d) => d.id === deviceId)
      if (match === undefined) return null
      return {
        driver: new WebBluetoothPhysicalDriver(match),
        serviceUuids: advertisedServices(match)
      }
    }
  }
}

export { DEVICE_SERVICE_UUIDS }
