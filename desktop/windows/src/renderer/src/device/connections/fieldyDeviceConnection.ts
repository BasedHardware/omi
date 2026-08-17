/**
 * Fieldy / Compass connection — Windows port of macOS
 * Connections/FieldyDeviceConnection.swift. One characteristic carries both
 * control and audio; the device streams 40-byte Opus frames on subscribe with
 * no session commands.
 */

import { FIELDY_UUIDS } from '../protocol/uuids'
import type { BleAudioCodec } from '../protocol/deviceTypes'
import {
  BaseDeviceConnection,
  finishedStream,
  type AccelerometerData,
  type StreamSubscriber,
  type StreamSubscription
} from './deviceConnection'

const OPUS_FRAME_SIZE = 40
const EXPECTED_TOC_BYTE = 0xb8
const POST_CONNECT_SETTLE_MS = 1_000

export class FieldyDeviceConnection extends BaseDeviceConnection {
  protected override async prepareDeviceAfterConnect(): Promise<void> {
    await this.settle(POST_CONNECT_SETTLE_MS)
    this.ensureLifecycleIsActive()
  }

  protected override async updateDeviceInfo(): Promise<void> {
    await super.updateDeviceInfo()
    this.device.modelNumber = this.device.modelNumber ?? 'Fieldy'
    this.device.firmwareRevision = this.device.firmwareRevision ?? '1.0.0'
    this.device.hardwareRevision = this.device.hardwareRevision ?? 'Fieldy Hardware'
    this.device.manufacturerName = this.device.manufacturerName ?? 'Fieldy'
  }

  override async getAudioCodec(): Promise<BleAudioCodec> {
    return 'opusFS320'
  }

  override getAudioStream(subscriber: StreamSubscriber<Uint8Array>): StreamSubscription {
    return this.transport.subscribeCharacteristic(
      FIELDY_UUIDS.service,
      FIELDY_UUIDS.controlAndAudio,
      {
        onData: (packet) => {
          // Typically 6 x 40-byte Opus frames per notification.
          let offset = 0
          while (offset + OPUS_FRAME_SIZE <= packet.length) {
            const frame = packet.subarray(offset, offset + OPUS_FRAME_SIZE)
            if (frame[0] !== EXPECTED_TOC_BYTE) {
              // Unexpected TOC is logged but the frame still flows.
              console.warn(`[device] fieldy frame with unexpected TOC 0x${frame[0].toString(16)}`)
            }
            subscriber.onValue(frame)
            offset += OPUS_FRAME_SIZE
          }
          // A trailing partial chunk passes only when it looks like a frame.
          if (offset < packet.length) {
            const tail = packet.subarray(offset)
            if (tail[0] === EXPECTED_TOC_BYTE) subscriber.onValue(tail)
          }
        },
        onFinish: (error) => subscriber.onFinish(error)
      }
    )
  }

  // --- unsupported surfaces --------------------------------------------------

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
}
