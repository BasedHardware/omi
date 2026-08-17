/**
 * Limitless pendant connection — Windows port of macOS
 * Connections/LimitlessDeviceConnection.swift. Protobuf commands go out on
 * the TX characteristic; the RX characteristic carries fragmented packets
 * that reassemble into real-time Opus audio or batch flash-page downloads,
 * plus heuristic button and device-status frames.
 */

import { LIMITLESS_UUIDS } from '../protocol/uuids'
import type { BleAudioCodec, OmiFeatureName } from '../protocol/deviceTypes'
import {
  DeviceOperationBroker,
  DeviceOperationBrokerError,
  UncorrelatedOperationGate,
  type DeviceOperationClock
} from '../session/deviceOperationBroker'
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
  decodeVarint,
  boundedFieldLength,
  parseBlePacket,
  parseFlashPageInfo,
  tryParseButtonStatus,
  tryParseDeviceStatus,
  FLASH_TIMESTAMP_SANITY_FLOOR_MS,
  LIMITLESS_MSG,
  type LimitlessStorageState
} from './limitlessProtocol'
import type { DeviceTransport } from '../transport/deviceTransport'
import type { BtDevice } from '../protocol/btDevice'

const POST_CONNECT_SETTLE_MS = 1_000
const INIT_GAP_MS = 1_000
const STORAGE_STATUS_TIMEOUT_MS = 3_000
const STORAGE_STATUS_KEY = 'limitless:storage-status'
const BUTTON_DOUBLE_PRESS = 3

export interface LimitlessFlashPage {
  opusFrames: Uint8Array[]
  timestampMs: number
  session: number | null
  seq: number | null
  index: number | null
  didStartSession: boolean
  didStopSession: boolean
  didStartRecording: boolean
  didStopRecording: boolean
}

export class LimitlessDeviceConnection extends BaseDeviceConnection {
  private readonly statusBroker: DeviceOperationBroker
  private readonly statusGate = new UncorrelatedOperationGate()
  private readonly audioSubject = new Subject<Uint8Array>()
  private readonly buttonSubject = new Subject<Uint8Array>()

  private messageIndex = 0
  private lastRequestId = 0
  private isInitialized = false
  private isBatchMode = false
  private fragmentBuffer = new Map<number, Map<number, Uint8Array>>()
  private highestIndex: number | null = null
  private storageState: LimitlessStorageState | null = null
  private flashPages: LimitlessFlashPage[] = []
  private firstFlashPageTimestampMs: number | null = null
  private lastLedBrightness: number | null = null

  constructor(args: {
    device: BtDevice
    transport: DeviceTransport
    clock?: DeviceOperationClock
  }) {
    super(args)
    this.statusBroker = new DeviceOperationBroker(this.clock)
  }

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
    this.isInitialized = true
  }

  protected override async teardownDevice(): Promise<void> {
    this.audioSubject.finish(null)
    this.buttonSubject.finish(null)
    this.isBatchMode = false
    this.statusBroker.cancelAll('disconnected')
    this.statusGate.reset()
  }

  protected override async performDeviceUnpair(): Promise<void> {
    await this.unpairWithoutReset()
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
    const status = tryParseDeviceStatus(data)
    if (status !== null) {
      this.storageState = status
      if (this.statusGate.takeHandleForCallback(STORAGE_STATUS_KEY) !== null) {
        this.statusBroker.succeed(STORAGE_STATUS_KEY, status)
      }
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
    }
    fragments.set(packet.seq, packet.payload)
    if (fragments.size < packet.numFrags) return

    const parts: Uint8Array[] = []
    for (let seq = 0; seq < packet.numFrags; seq += 1) {
      const fragment = fragments.get(seq)
      if (fragment !== undefined) parts.push(fragment)
    }
    this.fragmentBuffer.delete(packet.index)
    const assembled = concatenate(parts)
    if (this.isBatchMode) {
      this.handlePendantMessage(assembled)
    } else {
      this.handleRealTimePayload(assembled)
    }
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

  private handlePendantMessage(payload: Uint8Array): void {
    let pos = 0
    while (pos < payload.length) {
      const tag = decodeVarint(payload, pos)
      if (tag === null) return
      const fieldNum = tag.value >> 3
      const wireType = tag.value & 7
      pos = tag.next
      if (wireType === 2) {
        const length = decodeVarint(payload, pos)
        if (length === null) return
        const start = length.next
        const bounded = boundedFieldLength(length.value, start, payload.length)
        if (fieldNum === 2) {
          this.handleStorageBuffer(payload.subarray(start, start + bounded))
        }
        pos = start + Math.max(bounded, 1)
      } else if (wireType === 0) {
        const value = decodeVarint(payload, pos)
        if (value === null) return
        pos = value.next
      } else {
        return
      }
    }
  }

  private handleStorageBuffer(data: Uint8Array): void {
    let session: number | null = null
    let seq: number | null = null
    let index: number | null = null
    let flashPageData: Uint8Array | null = null
    let pos = 0
    while (pos < data.length) {
      const tag = decodeVarint(data, pos)
      if (tag === null) break
      const fieldNum = tag.value >> 3
      const wireType = tag.value & 7
      pos = tag.next
      if (wireType === 0) {
        const value = decodeVarint(data, pos)
        if (value === null) break
        pos = value.next
        if (fieldNum === 2) session = value.value
        else if (fieldNum === 4) seq = value.value
        else if (fieldNum === 5) index = value.value
      } else if (wireType === 2) {
        const length = decodeVarint(data, pos)
        if (length === null) break
        const start = length.next
        const bounded = boundedFieldLength(length.value, start, data.length)
        if (fieldNum === 6) flashPageData = data.subarray(start, start + bounded)
        pos = start + Math.max(bounded, 1)
      } else {
        break
      }
    }
    if (flashPageData === null) return
    const info = parseFlashPageInfo(flashPageData)
    const frames = extractOpusFramesFromFlashPage(flashPageData)
    if (frames.length === 0) return
    this.flashPages.push({
      opusFrames: frames,
      timestampMs: info.timestampMs ?? Date.now(),
      session,
      seq,
      index,
      didStartSession: info.didStartSession,
      didStopSession: info.didStopSession,
      didStartRecording: info.didStartRecording,
      didStopRecording: info.didStopRecording
    })
    if (
      this.firstFlashPageTimestampMs === null &&
      info.timestampMs !== null &&
      info.timestampMs > FLASH_TIMESTAMP_SANITY_FLOOR_MS
    ) {
      this.firstFlashPageTimestampMs = info.timestampMs
    }
  }

  // --- storage API -----------------------------------------------------------

  async getStorageStatus(): Promise<LimitlessStorageState | null> {
    if (!this.isInitialized) return null
    const handle = this.statusGate.register(STORAGE_STATUS_KEY)
    if (handle === null) return this.storageState
    try {
      return await this.statusBroker.perform<LimitlessStorageState>({
        key: STORAGE_STATUS_KEY,
        timeoutMs: STORAGE_STATUS_TIMEOUT_MS,
        onTerminal: (termination) => this.statusGate.terminal(handle, termination),
        start: () =>
          this.writeCommand(LIMITLESS_MSG.getDeviceStatus, commandBodies.getDeviceStatus())
      })
    } catch (error) {
      if (error instanceof DeviceOperationBrokerError && error.kind === 'timedOut') {
        return this.storageState
      }
      return null
    }
  }

  getFlashPageCount(): number {
    const oldest = this.storageState?.oldestFlashPage
    const newest = this.storageState?.newestFlashPage
    if (oldest === null || oldest === undefined || newest === null || newest === undefined) return 0
    return newest < oldest ? 0 : newest - oldest + 1
  }

  async enableBatchMode(): Promise<boolean> {
    this.fragmentBuffer.clear()
    this.flashPages = []
    this.isBatchMode = true
    try {
      await this.writeCommand(
        LIMITLESS_MSG.dataStream,
        commandBodies.downloadFlashPages(true, false)
      )
      return true
    } catch {
      this.isBatchMode = false
      return false
    }
  }

  async disableBatchMode(): Promise<boolean> {
    this.fragmentBuffer.clear()
    this.flashPages = []
    this.firstFlashPageTimestampMs = null
    try {
      await this.writeCommand(
        LIMITLESS_MSG.dataStream,
        commandBodies.downloadFlashPages(false, true)
      )
      return true
    } catch {
      return false
    } finally {
      this.isBatchMode = false
    }
  }

  async acknowledgeProcessedData(upToIndex: number): Promise<void> {
    await this.writeCommand(
      LIMITLESS_MSG.acknowledgeProcessedData,
      commandBodies.acknowledgeProcessedData(upToIndex)
    )
  }

  async unpairWithoutReset(): Promise<void> {
    await this.writeCommand(LIMITLESS_MSG.unpairBluetooth, commandBodies.unpairBluetooth(true))
  }

  get completedFlashPages(): readonly LimitlessFlashPage[] {
    return this.flashPages
  }

  get highestReceivedIndex(): number | null {
    return this.highestIndex
  }

  get firstPageTimestampMs(): number | null {
    return this.firstFlashPageTimestampMs
  }

  get batchModeEnabled(): boolean {
    return this.isBatchMode
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
