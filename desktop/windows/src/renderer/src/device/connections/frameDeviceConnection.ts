/**
 * Frame (Brilliant Labs) connection — Windows port of macOS
 * Connections/FrameDeviceConnection.swift. Basic BLE fallback only: the real
 * Frame protocol needs the Lua-based Frame SDK, so audio and camera are
 * documented no-ops and battery is the one live surface.
 */

import { BATTERY_UUIDS, DEVICE_INFO_UUIDS } from '../protocol/uuids'
import type { BleAudioCodec } from '../protocol/deviceTypes'
import {
  BaseDeviceConnection,
  finishedStream,
  type AccelerometerData,
  type OrientedImage,
  type StreamSubscriber,
  type StreamSubscription
} from './deviceConnection'

export class FrameDeviceConnection extends BaseDeviceConnection {
  private lastKnownBatteryLevel: number | null = null

  protected override async prepareDeviceAfterConnect(): Promise<void> {
    // Divergence from mac: the Swift source applies the hardcoded device info
    // in this hook as well as in updateDeviceInfo, and since connect() runs
    // updateDeviceInfo first, the second application overwrites the firmware
    // revision it had just read from the DIS. Applying the hardcodes only in
    // updateDeviceInfo keeps every value identical while letting that read
    // survive, which is the only reason the override exists.
    const level = await super.getBatteryLevel()
    this.lastKnownBatteryLevel = level >= 0 ? level : null
  }

  protected override async updateDeviceInfo(): Promise<void> {
    this.applyHardcodedDeviceInfo()
    try {
      const data = await this.transport.readCharacteristic(
        DEVICE_INFO_UUIDS.service,
        DEVICE_INFO_UUIDS.firmwareRevision
      )
      this.device.firmwareRevision = new TextDecoder().decode(data)
    } catch {
      // Firmware stays the hardcoded default.
    }
  }

  private applyHardcodedDeviceInfo(): void {
    this.device.modelNumber = 'Frame'
    this.device.firmwareRevision = 'Frame'
    this.device.hardwareRevision = 'Brilliant Labs Frame'
    this.device.manufacturerName = 'Brilliant Labs'
  }

  override async getBatteryLevel(): Promise<number> {
    const level = await super.getBatteryLevel()
    if (level >= 0) {
      this.lastKnownBatteryLevel = level
      return level
    }
    return this.lastKnownBatteryLevel ?? -1
  }

  override getBatteryLevelStream(subscriber: StreamSubscriber<number>): StreamSubscription {
    return this.transport.subscribeCharacteristic(BATTERY_UUIDS.service, BATTERY_UUIDS.level, {
      onData: (data) => {
        if (data.length === 0) return
        const level = data[0]
        if (level === this.lastKnownBatteryLevel) return
        this.lastKnownBatteryLevel = level
        subscriber.onValue(level)
      },
      onFinish: (error) => subscriber.onFinish(error)
    })
  }

  override async getAudioCodec(): Promise<BleAudioCodec> {
    return 'pcm8'
  }

  override getAudioStream(subscriber: StreamSubscriber<Uint8Array>): StreamSubscription {
    console.warn('[device] Frame audio streaming needs the Frame SDK; returning an empty stream')
    return finishedStream(subscriber)
  }

  // --- camera: hardware supports it; this fallback client does not -----------

  override async hasPhotoStreaming(): Promise<boolean> {
    return true
  }

  override async startPhotoCapture(): Promise<boolean> {
    console.warn('[device] Frame photo capture needs the Frame SDK')
    return false
  }

  override async stopPhotoCapture(): Promise<boolean> {
    return false
  }

  override getImageStream(subscriber: StreamSubscriber<OrientedImage>): StreamSubscription {
    return finishedStream(subscriber)
  }

  // --- everything else is explicitly unsupported -----------------------------

  override async getButtonState(): Promise<Uint8Array> {
    return new Uint8Array(0)
  }

  override getButtonStream(subscriber: StreamSubscriber<Uint8Array>): StreamSubscription {
    return finishedStream(subscriber)
  }

  override getAccelerometerStream(
    subscriber: StreamSubscriber<AccelerometerData>
  ): StreamSubscription {
    return finishedStream(subscriber)
  }

  override async getFeatures(): Promise<[]> {
    return []
  }

  override async getStorageList(): Promise<number[]> {
    return []
  }

  override getStorageStream(subscriber: StreamSubscriber<Uint8Array>): StreamSubscription {
    return finishedStream(subscriber)
  }

  override async playHaptic(_level: number): Promise<boolean> {
    return false
  }
}
