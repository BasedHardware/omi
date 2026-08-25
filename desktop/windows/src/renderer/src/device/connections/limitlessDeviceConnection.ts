/**
 * Limitless pendant connection — Windows port of macOS
 * Connections/LimitlessDeviceConnection.swift. Protobuf commands go out on
 * the TX characteristic; the RX characteristic carries fragmented packets that
 * reassemble into real-time Opus audio, plus heuristic button and
 * device-status frames.
 *
 * The pendant's stored flash-page drain (batch mode) is deliberately not here:
 * nothing on Windows consumes recorded pages yet, so it lands with the offline
 * sync work that has a consumer for it rather than shipping unreachable.
 */

import { LIMITLESS_UUIDS } from '../protocol/uuids'
import type { BleAudioCodec, OmiFeatureName } from '../protocol/deviceTypes'
import {
  BaseDeviceConnection,
  finishedStream,
  type AccelerometerData,
  type StreamSubscriber,
  type StreamSubscription
} from './deviceConnection'
import { Subject } from './subject'
import {
  commandBodies,
  encodeCommand,
  extractOpusFrames,
  extractOpusFramesFromFlashPage,
  parseBlePacket,
  tryParseButtonStatus,
  LIMITLESS_MSG
} from './limitlessProtocol'

const POST_CONNECT_SETTLE_MS = 1_000
const INIT_GAP_MS = 1_000
const BUTTON_DOUBLE_PRESS = 3
/** Reassembly is in-order in practice; this only bounds the leak from packets
 *  whose fragments never complete. */
const MAX_PENDING_FRAGMENT_INDEXES = 64

export class LimitlessDeviceConnection extends BaseDeviceConnection {
  private readonly audioSubject = new Subject<Uint8Array>()
  private readonly buttonSubject = new Subject<Uint8Array>()

  private messageIndex = 0
  private lastRequestId = 0
  private fragmentBuffer = new Map<number, Map<number, Uint8Array>>()
  private highestIndex: number | null = null
  private lastLedBrightness: number | null = null

  protected override async updateDeviceInfo(): Promise<void> {
    this.device.modelNumber = 'Limitless Pendant'
    this.device.firmwareRevision = '1.0.0'
    this.device.hardwareRevision = 'Unknown'
    this.device.manufacturerName = 'Limitless'
  }

  protected override async prepareDeviceAfterConnect(): Promise<void> {
    await this.settle(POST_CONNECT_SETTLE_MS)
    this.ensureLifecycleIsActive()
    this.transport.subscribeCharacteristic(
      LIMITLESS_UUIDS.service,
      LIMITLESS_UUIDS.rxCharacteristic,
      {
        onData: (data) => this.handleRxNotification(data),
        onFinish: (error) => {
          this.audioSubject.finish(error)
          this.buttonSubject.finish(error)
        }
      }
    )
    await this.settle(INIT_GAP_MS)
    this.ensureLifecycleIsActive()
    await this.initialize()
  }

  private async initialize(): Promise<void> {
    await this.writeCommand(LIMITLESS_MSG.timeSync, commandBodies.timeSync(Date.now()))
    await this.settle(INIT_GAP_MS)
    this.ensureLifecycleIsActive()
    await this.writeCommand(LIMITLESS_MSG.dataStream, commandBodies.enableDataStream(true))
    await this.settle(INIT_GAP_MS)
  }

  protected override async teardownDevice(): Promise<void> {
    this.audioSubject.finish(null)
    this.buttonSubject.finish(null)
  }

  protected override async performDeviceUnpair(): Promise<void> {
    await this.writeCommand(LIMITLESS_MSG.unpairBluetooth, commandBodies.unpairBluetooth(true))
  }

  // --- outbound --------------------------------------------------------------

  private async writeCommand(msgNum: number, body: Uint8Array): Promise<void> {
    this.lastRequestId += 1
    const frame = encodeCommand(this.messageIndex, this.lastRequestId, msgNum, body)
    this.messageIndex += 1
    await this.transport.writeCharacteristic({
      serviceUuid: LIMITLESS_UUIDS.service,
      characteristicUuid: LIMITLESS_UUIDS.txCharacteristic,
      data: frame,
      withResponse: true
    })
  }

  // --- inbound ---------------------------------------------------------------

  private handleRxNotification(data: Uint8Array): void {
    const buttonEvent = tryParseButtonStatus(data)
    if (buttonEvent === BUTTON_DOUBLE_PRESS) {
      // Only double press emits, mapped to state 2 as 4 LE bytes; short and
      // long presses are deliberately swallowed.
      this.buttonSubject.next(Uint8Array.from([0x02, 0x00, 0x00, 0x00]))
    }
    const packet = parseBlePacket(data)
    if (packet === null) return
    if (this.highestIndex === null || packet.index > this.highestIndex) {
      this.highestIndex = packet.index
    }
    let fragments = this.fragmentBuffer.get(packet.index)
    if (fragments === undefined) {
      fragments = new Map()
      this.fragmentBuffer.set(packet.index, fragments)
      // An index whose fragments never all arrive would otherwise sit here for
      // the life of the session; evict the oldest incomplete ones.
      while (this.fragmentBuffer.size > MAX_PENDING_FRAGMENT_INDEXES) {
        const oldest = this.fragmentBuffer.keys().next()
        if (oldest.done === true) break
        this.fragmentBuffer.delete(oldest.value)
      }
    }
    fragments.set(packet.seq, packet.payload)
    if (fragments.size < packet.numFrags) return

    const parts: Uint8Array[] = []
    for (let seq = 0; seq < packet.numFrags; seq += 1) {
      const fragment = fragments.get(seq)
      if (fragment !== undefined) parts.push(fragment)
    }
    this.fragmentBuffer.delete(packet.index)
    this.handleRealTimePayload(concatenate(parts))
  }

  private handleRealTimePayload(payload: Uint8Array): void {
    let frames = extractOpusFramesFromFlashPage(payload)
    if (frames.length === 0) {
      frames = extractOpusFrames(payload)
    }
    for (const frame of frames) {
      this.audioSubject.next(frame)
    }
  }

  // --- audio / buttons / features --------------------------------------------

  override async getAudioCodec(): Promise<BleAudioCodec> {
    return 'opusFS320'
  }

  override getAudioStream(subscriber: StreamSubscriber<Uint8Array>): StreamSubscription {
    return this.audioSubject.subscribe(subscriber)
  }

  override async getButtonState(): Promise<Uint8Array> {
    return new Uint8Array(0)
  }

  override getButtonStream(subscriber: StreamSubscriber<Uint8Array>): StreamSubscription {
    return this.buttonSubject.subscribe(subscriber)
  }

  override async getFeatures(): Promise<OmiFeatureName[]> {
    return ['ledDimming']
  }

  override async setLedDimRatio(ratio: number): Promise<boolean> {
    const clamped = Math.max(0, Math.min(100, Math.round(ratio)))
    try {
      await this.writeCommand(
        LIMITLESS_MSG.setLedBrightness,
        commandBodies.setLedBrightness(clamped)
      )
      this.lastLedBrightness = clamped
      return true
    } catch {
      return false
    }
  }

  override async getLedDimRatio(): Promise<number | null> {
    // The pendant has no readback; the last written value is the truth.
    return this.lastLedBrightness
  }

  override getAccelerometerStream(
    subscriber: StreamSubscriber<AccelerometerData>
  ): StreamSubscription {
    return finishedStream(subscriber)
  }
}

const concatenate = (parts: Uint8Array[]): Uint8Array => {
  const total = parts.reduce((sum, p) => sum + p.length, 0)
  const out = new Uint8Array(total)
  let offset = 0
  for (const part of parts) {
    out.set(part, offset)
    offset += part.length
  }
  return out
}
