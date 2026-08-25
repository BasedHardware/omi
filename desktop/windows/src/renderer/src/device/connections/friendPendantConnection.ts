/**
 * Friend Pendant connection — Windows port of macOS
 * Connections/FriendPendantConnection.swift. The pendant streams LC3
 * unconditionally (no session command): 95-byte packets carry three 30-byte
 * LC3 frames plus a 5-byte footer. Battery is faked at 90 because the
 * hardware exposes none.
 */

import { FRIEND_PENDANT_UUIDS } from '../protocol/uuids'
import type { BleAudioCodec } from '../protocol/deviceTypes'
import {
  BaseDeviceConnection,
  finishedStream,
  type AccelerometerData,
  type StreamSubscriber,
  type StreamSubscription
} from './deviceConnection'
import { Subject } from './subject'

const PACKET_FOOTER_SIZE = 5
const LC3_FRAME_SIZE = 30
const FAKE_BATTERY_LEVEL = 90
const FAKE_BATTERY_INTERVAL_MS = 30_000
const POST_CONNECT_SETTLE_MS = 1_000

export class FriendPendantConnection extends BaseDeviceConnection {
  private audioSubject = new Subject<Uint8Array>()

  protected override async updateDeviceInfo(): Promise<void> {
    this.device.modelNumber = 'Friend Pendant'
    this.device.firmwareRevision = '1.0.0'
    this.device.hardwareRevision = 'Friend'
    this.device.manufacturerName = 'Friend'
  }

  protected override async prepareDeviceAfterConnect(): Promise<void> {
    await this.settle(POST_CONNECT_SETTLE_MS)
    this.ensureLifecycleIsActive()
    this.transport.subscribeCharacteristic(
      FRIEND_PENDANT_UUIDS.service,
      FRIEND_PENDANT_UUIDS.audioCharacteristic,
      {
        onData: (packet) => this.handleAudioPacket(packet),
        onFinish: (error) => this.audioSubject.finish(error)
      }
    )
  }

  protected override async teardownDevice(): Promise<void> {
    this.audioSubject.finish(null)
  }

  private handleAudioPacket(packet: Uint8Array): void {
    if (packet.length < PACKET_FOOTER_SIZE) return
    const payload = packet.subarray(0, packet.length - PACKET_FOOTER_SIZE)
    // Only exact frames are emitted; a short tail is dropped.
    for (let offset = 0; offset + LC3_FRAME_SIZE <= payload.length; offset += LC3_FRAME_SIZE) {
      this.audioSubject.next(payload.subarray(offset, offset + LC3_FRAME_SIZE))
    }
  }

  override async getAudioCodec(): Promise<BleAudioCodec> {
    return 'lc3FS1030'
  }

  override getAudioStream(subscriber: StreamSubscriber<Uint8Array>): StreamSubscription {
    return this.audioSubject.subscribe(subscriber)
  }

  // --- faked battery ---------------------------------------------------------

  override async getBatteryLevel(): Promise<number> {
    return FAKE_BATTERY_LEVEL
  }

  override getBatteryLevelStream(subscriber: StreamSubscriber<number>): StreamSubscription {
    const abort = new AbortController()
    subscriber.onValue(FAKE_BATTERY_LEVEL)
    void (async () => {
      for (;;) {
        const outcome = await this.clock.sleep(FAKE_BATTERY_INTERVAL_MS, abort.signal)
        if (outcome !== 'elapsed') return
        subscriber.onValue(FAKE_BATTERY_LEVEL)
      }
    })()
    return { cancel: () => abort.abort() }
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
