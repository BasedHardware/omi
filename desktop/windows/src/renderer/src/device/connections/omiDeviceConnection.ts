/**
 * Omi / OpenGlass connection — Windows port of macOS
 * Connections/OmiDeviceConnection.swift. Omi is the first-party device and
 * the only family exercising the full base surface (storage, accelerometer,
 * haptics, features); this class adds the camera commands, image stream,
 * LED/mic settings, and wifi sync.
 */

import { wifiSyncErrorFromCode, validateWifiCredentials } from '../protocol/deviceTypes'
import { OMI_UUIDS, STORAGE_UUIDS } from '../protocol/uuids'
import {
  BaseDeviceConnection,
  DeviceConnectionError,
  finishedStream,
  type OrientedImage,
  type StreamSubscriber,
  type StreamSubscription,
  type WifiSyncResult
} from './deviceConnection'
import { OmiImageReassembler } from './omiImageReassembler'

const PHOTO_START_INTERVAL_5S = 0x05
const PHOTO_STOP = 0x00
const PHOTO_SINGLE = 0xff
const WIFI_SETUP = 0x01
const WIFI_START = 0x02
const WIFI_SHUTDOWN = 0x03
const WIFI_SETUP_RESPONSE_TIMEOUT_MS = 5_000

export class OmiDeviceConnection extends BaseDeviceConnection {
  protected override async prepareDeviceAfterConnect(): Promise<void> {
    // An omi with a readable image characteristic is an OpenGlass.
    if (this.device.type === 'omi' && (await this.hasPhotoStreaming())) {
      this.device = { ...this.device, type: 'openglass' }
    }
  }

  override async hasPhotoStreaming(): Promise<boolean> {
    try {
      await this.transport.readCharacteristic(OMI_UUIDS.mainService, OMI_UUIDS.imageDataStream)
      return true
    } catch {
      return false
    }
  }

  // --- camera ----------------------------------------------------------------

  override async startPhotoCapture(): Promise<boolean> {
    return this.writeCameraControl(PHOTO_START_INTERVAL_5S)
  }

  override async stopPhotoCapture(): Promise<boolean> {
    return this.writeCameraControl(PHOTO_STOP)
  }

  async takePhoto(): Promise<boolean> {
    return this.writeCameraControl(PHOTO_SINGLE)
  }

  private async writeCameraControl(command: number): Promise<boolean> {
    try {
      await this.transport.writeCharacteristic({
        serviceUuid: OMI_UUIDS.mainService,
        characteristicUuid: OMI_UUIDS.imageCaptureControl,
        data: Uint8Array.from([command]),
        withResponse: true
      })
      return true
    } catch {
      return false
    }
  }

  override getImageStream(subscriber: StreamSubscriber<OrientedImage>): StreamSubscription {
    const reassembler = new OmiImageReassembler(() => this.device.firmwareRevision ?? '1.0.0')
    return this.transport.subscribeCharacteristic(
      OMI_UUIDS.mainService,
      OMI_UUIDS.imageDataStream,
      {
        onData: (chunk) => {
          const image = reassembler.push(chunk)
          if (image !== null) subscriber.onValue(image)
        },
        onFinish: (error) => subscriber.onFinish(error)
      }
    )
  }

  // --- settings --------------------------------------------------------------

  override async setLedDimRatio(ratio: number): Promise<boolean> {
    return this.writeSetting(OMI_UUIDS.settingsDimRatio, ratio)
  }

  override async getLedDimRatio(): Promise<number | null> {
    return this.readSetting(OMI_UUIDS.settingsDimRatio)
  }

  override async setMicGain(gain: number): Promise<boolean> {
    return this.writeSetting(OMI_UUIDS.settingsMicGain, gain)
  }

  override async getMicGain(): Promise<number | null> {
    return this.readSetting(OMI_UUIDS.settingsMicGain)
  }

  private async writeSetting(characteristicUuid: string, value: number): Promise<boolean> {
    const clamped = Math.max(0, Math.min(100, Math.round(value)))
    try {
      await this.transport.writeCharacteristic({
        serviceUuid: OMI_UUIDS.settingsService,
        characteristicUuid,
        data: Uint8Array.from([clamped]),
        withResponse: true
      })
      return true
    } catch {
      return false
    }
  }

  private async readSetting(characteristicUuid: string): Promise<number | null> {
    try {
      const data = await this.transport.readCharacteristic(
        OMI_UUIDS.settingsService,
        characteristicUuid
      )
      return data.length > 0 ? data[0] : null
    } catch {
      return null
    }
  }

  // --- wifi sync -------------------------------------------------------------

  override async isWifiSyncSupported(): Promise<boolean> {
    const features = await this.getFeatures()
    return features.includes('wifi')
  }

  override async setupWifiSync(ssid: string, password: string): Promise<WifiSyncResult> {
    const validation = validateWifiCredentials(ssid, password)
    if (validation !== 'success') return { code: validation }

    const encoder = new TextEncoder()
    const ssidBytes = encoder.encode(ssid)
    const passwordBytes = encoder.encode(password)
    const command = new Uint8Array(1 + 1 + ssidBytes.length + 1 + passwordBytes.length)
    command[0] = WIFI_SETUP
    command[1] = ssidBytes.length
    command.set(ssidBytes, 2)
    command[2 + ssidBytes.length] = passwordBytes.length
    command.set(passwordBytes, 3 + ssidBytes.length)

    // The device responds via notification, so the subscription must exist
    // before the command is written.
    let settle: (result: WifiSyncResult) => void
    let fail: (error: Error) => void
    const response = new Promise<WifiSyncResult>((resolve, reject) => {
      settle = resolve
      fail = reject
    })
    let done = false
    const timeoutAbort = new AbortController()
    const subscription = this.transport.subscribeCharacteristic(
      STORAGE_UUIDS.service,
      STORAGE_UUIDS.wifi,
      {
        onData: (data) => {
          if (done || data.length === 0) return
          done = true
          settle({ code: wifiSyncErrorFromCode(data[0]) })
        },
        onFinish: (error) => {
          if (done) return
          done = true
          if (error !== null) {
            fail(DeviceConnectionError.connectionFailed(error.message))
          } else {
            fail(DeviceConnectionError.operationFailed('WiFi setup response timed out'))
          }
        }
      }
    )
    void this.clock.sleep(WIFI_SETUP_RESPONSE_TIMEOUT_MS, timeoutAbort.signal).then((outcome) => {
      if (outcome !== 'elapsed' || done) return
      done = true
      fail(DeviceConnectionError.operationFailed('WiFi setup response timed out'))
    })

    try {
      await this.transport.writeCharacteristic({
        serviceUuid: STORAGE_UUIDS.service,
        characteristicUuid: STORAGE_UUIDS.wifi,
        data: command,
        withResponse: true
      })
      return await response
    } finally {
      timeoutAbort.abort()
      subscription.cancel()
    }
  }

  override async startWifiSync(): Promise<boolean> {
    return this.writeWifiControl(WIFI_START)
  }

  override async stopWifiSync(): Promise<boolean> {
    return this.writeWifiControl(WIFI_SHUTDOWN)
  }

  private async writeWifiControl(command: number): Promise<boolean> {
    try {
      await this.transport.writeCharacteristic({
        serviceUuid: STORAGE_UUIDS.service,
        characteristicUuid: STORAGE_UUIDS.wifi,
        data: Uint8Array.from([command]),
        withResponse: true
      })
      return true
    } catch {
      return false
    }
  }

  override getWifiSyncStatusStream(subscriber: StreamSubscriber<number>): StreamSubscription {
    if (this.transport.state !== 'connected') {
      return finishedStream(subscriber)
    }
    return this.transport.subscribeCharacteristic(STORAGE_UUIDS.service, STORAGE_UUIDS.wifi, {
      onData: (data) => {
        if (data.length > 0) subscriber.onValue(data[0])
      },
      onFinish: (error) => subscriber.onFinish(error)
    })
  }
}
