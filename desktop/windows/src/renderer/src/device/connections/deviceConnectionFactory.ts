/**
 * Family dispatch — Windows port of macOS
 * Connections/DeviceConnectionFactory.swift. Apple Watch has no BLE client
 * (the mac source leaves it TODO) and resolves to null.
 */

import type { BtDevice } from '../protocol/btDevice'
import type { DeviceTransport } from '../transport/deviceTransport'
import type { DeviceOperationClock } from '../session/deviceOperationBroker'
import type { DeviceConnection } from './deviceConnection'
import { OmiDeviceConnection } from './omiDeviceConnection'
import { PlaudDeviceConnection } from './plaudDeviceConnection'
import { BeeDeviceConnection } from './beeDeviceConnection'
import { FieldyDeviceConnection } from './fieldyDeviceConnection'
import { FriendPendantConnection } from './friendPendantConnection'
import { LimitlessDeviceConnection } from './limitlessDeviceConnection'
import { FrameDeviceConnection } from './frameDeviceConnection'

export const createDeviceConnection = (args: {
  device: BtDevice
  transport: DeviceTransport
  clock?: DeviceOperationClock
}): DeviceConnection | null => {
  switch (args.device.type) {
    case 'omi':
    case 'openglass':
      return new OmiDeviceConnection(args)
    case 'plaud':
      return new PlaudDeviceConnection(args)
    case 'bee':
      return new BeeDeviceConnection(args)
    case 'fieldy':
      return new FieldyDeviceConnection(args)
    case 'friendPendant':
      return new FriendPendantConnection(args)
    case 'limitless':
      return new LimitlessDeviceConnection(args)
    case 'frame':
      return new FrameDeviceConnection(args)
    case 'appleWatch':
      return null
  }
}
