/**
 * GATT UUID registry — Windows port of macOS DeviceUUIDs.swift. Every UUID is
 * a firmware contract; values are verbatim, lowercased for WebBluetooth
 * (which compares UUIDs as lowercase strings).
 */

export const OMI_UUIDS = {
  mainService: '19b10000-e8f2-537e-4f6c-d104768a1214',
  audioDataStream: '19b10001-e8f2-537e-4f6c-d104768a1214',
  audioCodec: '19b10002-e8f2-537e-4f6c-d104768a1214',
  imageDataStream: '19b10005-e8f2-537e-4f6c-d104768a1214',
  imageCaptureControl: '19b10006-e8f2-537e-4f6c-d104768a1214',
  settingsService: '19b10010-e8f2-537e-4f6c-d104768a1214',
  settingsDimRatio: '19b10011-e8f2-537e-4f6c-d104768a1214',
  settingsMicGain: '19b10012-e8f2-537e-4f6c-d104768a1214',
  featuresService: '19b10020-e8f2-537e-4f6c-d104768a1214',
  featuresCharacteristic: '19b10021-e8f2-537e-4f6c-d104768a1214'
} as const

export const BUTTON_UUIDS = {
  service: '23ba7924-0000-1000-7450-346eac492e92',
  trigger: '23ba7925-0000-1000-7450-346eac492e92'
} as const

export const STORAGE_UUIDS = {
  service: '30295780-4301-eabd-2904-2849adfeae43',
  dataStream: '30295781-4301-eabd-2904-2849adfeae43',
  readControl: '30295782-4301-eabd-2904-2849adfeae43',
  wifi: '30295783-4301-eabd-2904-2849adfeae43'
} as const

export const ACCELEROMETER_UUIDS = {
  service: '32403790-0000-1000-7450-bf445e5829a2',
  dataStream: '32403791-0000-1000-7450-bf445e5829a2'
} as const

/** Standard GATT battery service (16-bit UUIDs expanded to full form). */
export const BATTERY_UUIDS = {
  service: '0000180f-0000-1000-8000-00805f9b34fb',
  level: '00002a19-0000-1000-8000-00805f9b34fb'
} as const

export const SPEAKER_UUIDS = {
  service: 'cab1ab95-2ea5-4f4d-bb56-874b72cfc984',
  dataStream: 'cab1ab96-2ea5-4f4d-bb56-874b72cfc984'
} as const

/** Standard Device Information Service. */
export const DEVICE_INFO_UUIDS = {
  service: '0000180a-0000-1000-8000-00805f9b34fb',
  modelNumber: '00002a24-0000-1000-8000-00805f9b34fb',
  firmwareRevision: '00002a26-0000-1000-8000-00805f9b34fb',
  hardwareRevision: '00002a27-0000-1000-8000-00805f9b34fb',
  manufacturerName: '00002a29-0000-1000-8000-00805f9b34fb'
} as const

export const FRAME_UUIDS = {
  service: '7a230001-5475-a6a4-654c-8431f6ad49c4'
} as const

export const PLAUD_UUIDS = {
  service: '00001910-0000-1000-8000-00805f9b34fb',
  writeCharacteristic: '00002bb1-0000-1000-8000-00805f9b34fb',
  notifyCharacteristic: '00002bb0-0000-1000-8000-00805f9b34fb'
} as const

/** PLAUD advertises Bluetooth SIG company id 93 (0x005D) in manufacturer data. */
export const PLAUD_MANUFACTURER_ID = 93

export const BEE_UUIDS = {
  service: '03d5d5c4-a86c-11ee-9d89-8f2089a49e7e',
  control: '05e1f93c-d8d0-5ed8-dd88-379e4c1a3e3e',
  audio: 'b189a505-a86c-11ee-a5fb-8f2089a49e7e'
} as const

export const FIELDY_UUIDS = {
  service: '4fafc201-1fb5-459e-8fcc-c5c9c331914b',
  controlAndAudio: '82a48422-3ca9-4156-ae67-4170f58666e0'
} as const

export const FRIEND_PENDANT_UUIDS = {
  service: '1a3fd0e7-b1f3-ac9e-2e49-b647b2c4f8da',
  audioCharacteristic: '01000000-1111-1111-1111-111111111111'
} as const

export const LIMITLESS_UUIDS = {
  service: '632de001-604c-446b-a80f-7963e950f3fb',
  txCharacteristic: '632de002-604c-446b-a80f-7963e950f3fb',
  rxCharacteristic: '632de003-604c-446b-a80f-7963e950f3fb'
} as const

/** Every service a supported wearable might expose — the WebBluetooth
 *  requestDevice optionalServices list (access must be declared up front). */
export const ALL_OPTIONAL_SERVICE_UUIDS: readonly string[] = [
  OMI_UUIDS.mainService,
  OMI_UUIDS.settingsService,
  OMI_UUIDS.featuresService,
  BUTTON_UUIDS.service,
  STORAGE_UUIDS.service,
  ACCELEROMETER_UUIDS.service,
  BATTERY_UUIDS.service,
  SPEAKER_UUIDS.service,
  DEVICE_INFO_UUIDS.service,
  FRAME_UUIDS.service,
  PLAUD_UUIDS.service,
  BEE_UUIDS.service,
  FIELDY_UUIDS.service,
  FRIEND_PENDANT_UUIDS.service,
  LIMITLESS_UUIDS.service
]
