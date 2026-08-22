import { describe, it, expect } from 'vitest'
import {
  DEVICE_TYPES,
  deviceDisplayName,
  deviceManufacturerName,
  deviceDefaultFirmwareRevision,
  deviceDefaultHardwareRevision,
  requiresFirmwareWarning,
  firmwareWarningMessage,
  analyticsVendorSlug,
  CODEC_RAW_IDS,
  CODEC_WIRE_NAMES,
  CODEC_SAMPLE_RATE,
  codecFramesPerSecond,
  codecFrameLengthInBytes,
  codecFrameSize,
  codecBitDepth,
  codecFromCharacteristicByte,
  codecFromWireName,
  defaultCodecForDevice,
  OMI_FEATURE_BITS,
  hasFeature,
  imageOrientationFromByte,
  wifiSyncErrorFromCode,
  validateWifiCredentials
} from './deviceTypes'

describe('device metadata', () => {
  it('carries the mac-exact display and manufacturer names', () => {
    expect(DEVICE_TYPES.length).toBe(9)
    expect(deviceDisplayName('omi')).toBe('omi')
    expect(deviceDisplayName('friendPendant')).toBe('Friend Pendant')
    expect(deviceManufacturerName('omi')).toBe('Based Hardware')
    expect(deviceManufacturerName('frame')).toBe('Brilliant Labs')
    expect(deviceDefaultHardwareRevision('omi')).toBe('Seeed Xiao BLE Sense')
    expect(deviceDefaultFirmwareRevision('omi')).toBe('1.0.2')
    expect(deviceDefaultFirmwareRevision('bee')).toBe('1.0.0')
    expect(analyticsVendorSlug('fieldy')).toBe('fieldlabs')
    expect(analyticsVendorSlug('openglass')).toBe('omi')
  })

  it('warns on third-party firmware only, with the templated copy', () => {
    expect(requiresFirmwareWarning('omi')).toBe(false)
    expect(requiresFirmwareWarning('plaud')).toBe(true)
    expect(firmwareWarningMessage('omi')).toBeNull()
    expect(firmwareWarningMessage('fieldy')).toContain('not updating through the Compass app')
  })
})

describe('codec table', () => {
  it('pins the raw ids and wire names', () => {
    expect(CODEC_RAW_IDS.pcm16).toBe(0)
    expect(CODEC_RAW_IDS.opus).toBe(20)
    expect(CODEC_RAW_IDS.opusFS320).toBe(21)
    expect(CODEC_RAW_IDS.lc3FS1030).toBe(23)
    expect(CODEC_RAW_IDS.unknown).toBe(-1)
    expect(CODEC_WIRE_NAMES.opusFS320).toBe('opus_fs320')
    expect(CODEC_WIRE_NAMES.lc3FS1030).toBe('lc3_fs1030')
  })

  it('sample rate is always 16000; fps/frame sizes split on opusFS320', () => {
    expect(CODEC_SAMPLE_RATE).toBe(16_000)
    expect(codecFramesPerSecond('opus')).toBe(100)
    expect(codecFramesPerSecond('opusFS320')).toBe(50)
    expect(codecFrameLengthInBytes('opus')).toBe(80)
    expect(codecFrameLengthInBytes('opusFS320')).toBe(160)
    expect(codecFrameSize('opusFS320')).toBe(320)
    expect(codecBitDepth('pcm8')).toBe(8)
    expect(codecBitDepth('opus')).toBe(16)
  })

  it('characteristic byte mapping: 1/20/21 with pcm8 default', () => {
    expect(codecFromCharacteristicByte(1)).toBe('pcm8')
    expect(codecFromCharacteristicByte(20)).toBe('opus')
    expect(codecFromCharacteristicByte(21)).toBe('opusFS320')
    expect(codecFromCharacteristicByte(0)).toBe('pcm8')
    expect(codecFromCharacteristicByte(99)).toBe('pcm8')
  })

  it('wire-name parse and per-family defaults', () => {
    expect(codecFromWireName('OPUS_FS320')).toBe('opusFS320')
    expect(codecFromWireName('nonsense')).toBe('unknown')
    expect(defaultCodecForDevice('omi')).toBe('opus')
    expect(defaultCodecForDevice('bee')).toBe('aac')
    expect(defaultCodecForDevice('friendPendant')).toBe('lc3FS1030')
    expect(defaultCodecForDevice('frame')).toBe('pcm16')
  })
})

describe('features and orientation', () => {
  it('feature bits are positional 0-9 in the mac order', () => {
    expect(OMI_FEATURE_BITS.speaker).toBe(1)
    expect(OMI_FEATURE_BITS.battery).toBe(8)
    expect(OMI_FEATURE_BITS.offlineStorage).toBe(64)
    expect(OMI_FEATURE_BITS.wifi).toBe(512)
    expect(hasFeature(0b1000000, 'offlineStorage')).toBe(true)
    expect(hasFeature(0b1000000, 'wifi')).toBe(false)
  })

  it('orientation bytes map 0-3 to degrees with an invalid fallback', () => {
    expect(imageOrientationFromByte(0)).toBe(0)
    expect(imageOrientationFromByte(1)).toBe(90)
    expect(imageOrientationFromByte(2)).toBe(180)
    expect(imageOrientationFromByte(3)).toBe(270)
    expect(imageOrientationFromByte(9)).toBe(0)
  })
})

describe('wifi sync', () => {
  it('maps error codes with unknown fallback', () => {
    expect(wifiSyncErrorFromCode(0x00)).toBe('success')
    expect(wifiSyncErrorFromCode(0x05)).toBe('sessionAlreadyRunning')
    expect(wifiSyncErrorFromCode(0xfe)).toBe('wifiHardwareNotAvailable')
    expect(wifiSyncErrorFromCode(0x77)).toBe('unknownCommand')
  })

  it('validates ssid 1-32 and password 8-63 on chars and bytes', () => {
    expect(validateWifiCredentials('home', 'password1')).toBe('success')
    expect(validateWifiCredentials('', 'password1')).toBe('ssidLengthInvalid')
    expect(validateWifiCredentials('x'.repeat(33), 'password1')).toBe('ssidLengthInvalid')
    expect(validateWifiCredentials('home', 'short')).toBe('passwordLengthInvalid')
    expect(validateWifiCredentials('home', 'x'.repeat(64))).toBe('passwordLengthInvalid')
    // Multi-byte characters can exceed the byte budget below the char budget.
    expect(validateWifiCredentials('日本語の家のネットワーク名前', 'password1')).toBe(
      'ssidLengthInvalid'
    )
  })
})
