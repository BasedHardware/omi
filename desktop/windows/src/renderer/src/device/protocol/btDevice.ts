/**
 * Discovered-device model and type detection — Windows port of macOS
 * BtDevice.swift. Detection order is a firmware contract: first match wins,
 * and reordering changes which family claims ambiguous advertisements.
 */

import {
  type DeviceType,
  deviceDisplayName,
  deviceDefaultFirmwareRevision,
  deviceDefaultHardwareRevision,
  deviceManufacturerName
} from './deviceTypes'
import {
  BEE_UUIDS,
  FIELDY_UUIDS,
  FRAME_UUIDS,
  FRIEND_PENDANT_UUIDS,
  LIMITLESS_UUIDS,
  OMI_UUIDS,
  PLAUD_MANUFACTURER_ID
} from './uuids'

export interface BtDevice {
  /** Platform device id (WebBluetooth BluetoothDevice.id — per-origin stable). */
  id: string
  name: string
  type: DeviceType
  rssi: number
  modelNumber: string | null
  firmwareRevision: string | null
  hardwareRevision: string | null
  manufacturerName: string | null
}

export function makeBtDevice(args: {
  id: string
  name: string | null
  type: DeviceType
  rssi?: number
}): BtDevice {
  return {
    id: args.id,
    name: args.name && args.name.length > 0 ? args.name : deviceDisplayName(args.type),
    type: args.type,
    rssi: args.rssi ?? 0,
    modelNumber: null,
    firmwareRevision: null,
    hardwareRevision: null,
    manufacturerName: null
  }
}

/** Short display id: last 6 chars of the last dash component when it is long
 *  enough, else the first 6 chars of the id (mac BtDevice.shortId). */
export function shortDeviceId(id: string): string {
  const stripped = id.replace(/:/g, '')
  const parts = stripped.split('-')
  const last = parts[parts.length - 1] ?? ''
  if (last.length >= 6) return last.slice(-6)
  return stripped.slice(0, 6)
}

export function displayModelNumber(device: BtDevice): string {
  return device.modelNumber ?? deviceDisplayName(device.type)
}

export function displayFirmwareRevision(device: BtDevice): string {
  return device.firmwareRevision ?? deviceDefaultFirmwareRevision(device.type)
}

export function displayHardwareRevision(device: BtDevice): string {
  return device.hardwareRevision ?? deviceDefaultHardwareRevision(device.type)
}

export function displayManufacturerName(device: BtDevice): string {
  return device.manufacturerName ?? deviceManufacturerName(device.type)
}

export interface AdvertisementInput {
  /** Advertised (or chooser-provided) device name; null when absent. */
  name: string | null
  /** Advertised service UUIDs, lowercased. */
  serviceUuids: readonly string[]
  /** Manufacturer data keyed by company id (little-endian id already parsed). */
  manufacturerData?: ReadonlyMap<number, Uint8Array>
}

/** PLAUD advertisement detection (mac BtDevice.isPlaudDevice): company id 93;
 *  the known NotePin payload `04 56 cf 00` is explicitly recognized, and any
 *  other non-empty payload under id 93 is accepted. */
export function isPlaudAdvertisement(manufacturerData?: ReadonlyMap<number, Uint8Array>): boolean {
  const payload = manufacturerData?.get(PLAUD_MANUFACTURER_ID)
  if (payload === undefined) return false
  if (
    payload.length >= 4 &&
    payload[0] === 0x04 &&
    payload[1] === 0x56 &&
    payload[2] === 0xcf &&
    payload[3] === 0x00
  ) {
    return true
  }
  return payload.length > 0
}

/** Detection order (first match wins): Bee, PLAUD, Fieldy, FriendPendant,
 *  Limitless, Omi, Frame; unsupported -> null. OpenGlass is resolved only
 *  after connect via the image characteristic probe. */
export function detectDeviceType(input: AdvertisementInput): DeviceType | null {
  const name = (input.name ?? '').toLowerCase()
  const services = new Set(input.serviceUuids.map((s) => s.toLowerCase()))

  if (name.includes('bee') || services.has(BEE_UUIDS.service)) return 'bee'
  if (isPlaudAdvertisement(input.manufacturerData) || name.startsWith('plaud')) return 'plaud'
  if (name === 'compass' || name === 'fieldy' || services.has(FIELDY_UUIDS.service)) return 'fieldy'
  if (name.startsWith('friend_') || services.has(FRIEND_PENDANT_UUIDS.service)) {
    return 'friendPendant'
  }
  if (
    name.includes('limitless') ||
    name.includes('pendant') ||
    services.has(LIMITLESS_UUIDS.service)
  ) {
    return 'limitless'
  }
  if (services.has(OMI_UUIDS.mainService)) return 'omi'
  if (services.has(FRAME_UUIDS.service)) return 'frame'
  return null
}

/** WebBluetooth requestDevice filters mirroring the detection rules: service
 *  signatures for the service-detected families plus name prefixes for the
 *  name-detected ones. The chooser cannot express "contains", so prefix
 *  filters cover the common firmware names and the unfiltered fallback is the
 *  chooser's acceptAllDevices path handled by the caller. */
export function chooserFilters(): Array<{ services?: string[]; namePrefix?: string }> {
  return [
    { services: [OMI_UUIDS.mainService] },
    { services: [BEE_UUIDS.service] },
    { services: [FIELDY_UUIDS.service] },
    { services: [FRIEND_PENDANT_UUIDS.service] },
    { services: [LIMITLESS_UUIDS.service] },
    { services: [FRAME_UUIDS.service] },
    { namePrefix: 'PLAUD' },
    { namePrefix: 'plaud' },
    { namePrefix: 'Omi' },
    { namePrefix: 'omi' },
    { namePrefix: 'Friend' },
    { namePrefix: 'friend_' },
    { namePrefix: 'Compass' },
    { namePrefix: 'Fieldy' },
    { namePrefix: 'Bee' },
    { namePrefix: 'Limitless' },
    { namePrefix: 'Pendant' }
  ]
}
