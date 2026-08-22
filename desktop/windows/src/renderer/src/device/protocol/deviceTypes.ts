/**
 * Wearable device model foundations — Windows port of macOS DeviceType.swift
 * (itself ported from the Flutter app, the protocol authority). Enum raw
 * values, display metadata, codec table values, and feature bits are
 * identity-level contracts shared with the device firmware and the backend;
 * every value here is verbatim from the mac source.
 */

export type DeviceType =
  | 'omi'
  | 'openglass'
  | 'frame'
  | 'appleWatch'
  | 'plaud'
  | 'bee'
  | 'fieldy'
  | 'friendPendant'
  | 'limitless'

export const DEVICE_TYPES: readonly DeviceType[] = [
  'omi',
  'openglass',
  'frame',
  'appleWatch',
  'plaud',
  'bee',
  'fieldy',
  'friendPendant',
  'limitless'
]

export function deviceDisplayName(type: DeviceType): string {
  switch (type) {
    case 'omi':
      return 'omi'
    case 'openglass':
      return 'OpenGlass'
    case 'frame':
      return 'Frame'
    case 'appleWatch':
      return 'Apple Watch'
    case 'plaud':
      return 'PLAUD'
    case 'bee':
      return 'Bee'
    case 'fieldy':
      return 'Fieldy'
    case 'friendPendant':
      return 'Friend Pendant'
    case 'limitless':
      return 'Limitless'
  }
}

export function deviceManufacturerName(type: DeviceType): string {
  switch (type) {
    case 'omi':
    case 'openglass':
      return 'Based Hardware'
    case 'frame':
      return 'Brilliant Labs'
    case 'appleWatch':
      return 'Apple'
    case 'plaud':
      return 'PLAUD'
    case 'bee':
      return 'Bee'
    case 'fieldy':
      return 'Fieldy'
    case 'friendPendant':
      return 'Friend'
    case 'limitless':
      return 'Limitless'
  }
}

export function deviceDefaultHardwareRevision(type: DeviceType): string {
  switch (type) {
    case 'omi':
    case 'openglass':
      return 'Seeed Xiao BLE Sense'
    case 'frame':
      return 'Brilliant Labs Frame'
    case 'appleWatch':
      return 'Unknown'
    case 'fieldy':
      return 'Fieldy Hardware'
    case 'limitless':
      return 'Unknown'
    default:
      return '1.0.0'
  }
}

export function deviceDefaultFirmwareRevision(type: DeviceType): string {
  return type === 'omi' || type === 'openglass' ? '1.0.2' : '1.0.0'
}

/** Third-party devices whose firmware must not be updated through vendor apps. */
export function requiresFirmwareWarning(type: DeviceType): boolean {
  return (
    type === 'plaud' ||
    type === 'bee' ||
    type === 'fieldy' ||
    type === 'friendPendant' ||
    type === 'limitless'
  )
}

export function firmwareWarningMessage(type: DeviceType): string | null {
  if (!requiresFirmwareWarning(type)) return null
  const appName =
    type === 'plaud'
      ? 'PLAUD'
      : type === 'bee'
        ? 'Bee'
        : type === 'fieldy'
          ? 'Compass'
          : type === 'friendPendant'
            ? 'Friend'
            : 'Limitless'
  return `Your device's current firmware works great with Omi.\n\nWe recommend keeping your current firmware and not updating through the ${appName} app, as newer versions may affect compatibility.`
}

/** Analytics vendor slugs (mac DeviceType.analyticsVendorSlug). */
export function analyticsVendorSlug(type: DeviceType): string {
  switch (type) {
    case 'omi':
    case 'openglass':
      return 'omi'
    case 'limitless':
      return 'limitless'
    case 'plaud':
      return 'plaud'
    case 'bee':
      return 'bee'
    case 'appleWatch':
      return 'apple'
    case 'fieldy':
      return 'fieldlabs'
    case 'friendPendant':
      return 'friend'
    case 'frame':
      return 'unknown'
  }
}

// --- audio codec table ------------------------------------------------------

export type BleAudioCodec =
  | 'pcm16'
  | 'pcm8'
  | 'mulaw16'
  | 'mulaw8'
  | 'opus'
  | 'opusFS320'
  | 'aac'
  | 'lc3FS1030'
  | 'unknown'

/** Firmware codec ids (the byte read from the codec characteristic). */
export const CODEC_RAW_IDS: Record<BleAudioCodec, number> = {
  pcm16: 0,
  pcm8: 1,
  mulaw16: 10,
  mulaw8: 11,
  opus: 20,
  opusFS320: 21,
  aac: 22,
  lc3FS1030: 23,
  unknown: -1
}

/** Wire names (used by the WAL layer and diagnostics; never on /v4/listen —
 *  BLE audio is decoded client-side and always ships as linear16). */
export const CODEC_WIRE_NAMES: Record<BleAudioCodec, string> = {
  pcm16: 'pcm16',
  pcm8: 'pcm8',
  mulaw16: 'mulaw16',
  mulaw8: 'mulaw8',
  opus: 'opus',
  opusFS320: 'opus_fs320',
  aac: 'aac',
  lc3FS1030: 'lc3_fs1030',
  unknown: 'unknown'
}

export const CODEC_SAMPLE_RATE = 16_000

export function codecFramesPerSecond(codec: BleAudioCodec): number {
  return codec === 'opusFS320' ? 50 : 100
}

/** Encoded frame length used for packet-reassembly completion. */
export function codecFrameLengthInBytes(codec: BleAudioCodec): number {
  return codec === 'opusFS320' ? 160 : 80
}

/** PCM samples per frame. */
export function codecFrameSize(codec: BleAudioCodec): number {
  return codec === 'opusFS320' ? 320 : 160
}

export function codecBitDepth(codec: BleAudioCodec): number {
  return codec === 'pcm8' || codec === 'mulaw8' ? 8 : 16
}

export function isOpusCodec(codec: BleAudioCodec): boolean {
  return codec === 'opus' || codec === 'opusFS320'
}

/** Codec-characteristic byte mapping (mac DeviceConnection.getAudioCodec):
 *  1 -> pcm8, 20 -> opus, 21 -> opusFS320, anything else -> pcm8. */
export function codecFromCharacteristicByte(byte: number): BleAudioCodec {
  switch (byte) {
    case 1:
      return 'pcm8'
    case 20:
      return 'opus'
    case 21:
      return 'opusFS320'
    default:
      return 'pcm8'
  }
}

export function codecFromWireName(name: string): BleAudioCodec {
  const lowered = name.toLowerCase()
  for (const [codec, wire] of Object.entries(CODEC_WIRE_NAMES)) {
    if (wire === lowered) return codec as BleAudioCodec
  }
  return 'unknown'
}

export function codecDisplayName(codec: BleAudioCodec): string {
  switch (codec) {
    case 'pcm16':
      return 'PCM (16kHz)'
    case 'pcm8':
      return 'PCM (8kHz)'
    case 'mulaw16':
      return 'µ-law (16-bit)'
    case 'mulaw8':
      return 'µ-law (8-bit)'
    case 'opus':
      return 'OPUS'
    case 'opusFS320':
      return 'OPUS (320)'
    case 'aac':
      return 'AAC'
    case 'lc3FS1030':
      return 'LC3 (10ms/30B)'
    case 'unknown':
      return 'Unknown'
  }
}

/** Default codec per family before/without the characteristic read
 *  (mac BleAudioProcessor.forDevice). */
export function defaultCodecForDevice(type: DeviceType): BleAudioCodec {
  switch (type) {
    case 'omi':
    case 'openglass':
      return 'opus'
    case 'plaud':
    case 'limitless':
    case 'fieldy':
      return 'opusFS320'
    case 'bee':
      return 'aac'
    case 'friendPendant':
      return 'lc3FS1030'
    case 'frame':
    case 'appleWatch':
      return 'pcm16'
  }
}

// --- feature bitmask --------------------------------------------------------

/** Omi features characteristic: 4-byte little-endian bitmask. */
export const OMI_FEATURE_BITS = {
  speaker: 1 << 0,
  accelerometer: 1 << 1,
  button: 1 << 2,
  battery: 1 << 3,
  usb: 1 << 4,
  haptic: 1 << 5,
  offlineStorage: 1 << 6,
  ledDimming: 1 << 7,
  micGain: 1 << 8,
  wifi: 1 << 9
} as const

export type OmiFeatureName = keyof typeof OMI_FEATURE_BITS

export function hasFeature(mask: number, feature: OmiFeatureName): boolean {
  return (mask & OMI_FEATURE_BITS[feature]) !== 0
}

// --- image orientation ------------------------------------------------------

export type ImageOrientationDegrees = 0 | 90 | 180 | 270

/** Raw orientation byte 0-3 -> degrees; invalid -> 0. */
export function imageOrientationFromByte(value: number): ImageOrientationDegrees {
  switch (value) {
    case 1:
      return 90
    case 2:
      return 180
    case 3:
      return 270
    default:
      return 0
  }
}

// --- wifi sync --------------------------------------------------------------

export type WifiSyncErrorCode =
  | 'success'
  | 'invalidPacketLength'
  | 'invalidSetupLength'
  | 'ssidLengthInvalid'
  | 'passwordLengthInvalid'
  | 'sessionAlreadyRunning'
  | 'wifiHardwareNotAvailable'
  | 'unknownCommand'

export function wifiSyncErrorFromCode(code: number): WifiSyncErrorCode {
  switch (code) {
    case 0x00:
      return 'success'
    case 0x01:
      return 'invalidPacketLength'
    case 0x02:
      return 'invalidSetupLength'
    case 0x03:
      return 'ssidLengthInvalid'
    case 0x04:
      return 'passwordLengthInvalid'
    case 0x05:
      return 'sessionAlreadyRunning'
    case 0xfe:
      return 'wifiHardwareNotAvailable'
    default:
      return 'unknownCommand'
  }
}

/** SSID 1-32, password 8-63 — validated on both character and UTF-8 byte
 *  length (mac WifiCredentialsValidator). */
export function validateWifiCredentials(ssid: string, password: string): WifiSyncErrorCode {
  const ssidBytes = new TextEncoder().encode(ssid).length
  if (ssid.length < 1 || ssid.length > 32 || ssidBytes < 1 || ssidBytes > 32) {
    return 'ssidLengthInvalid'
  }
  const passwordBytes = new TextEncoder().encode(password).length
  if (password.length < 8 || password.length > 63 || passwordBytes < 8 || passwordBytes > 63) {
    return 'passwordLengthInvalid'
  }
  return 'success'
}
