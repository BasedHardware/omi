/**
 * PLAUD NotePin connection — Windows port of macOS
 * Connections/PlaudDeviceConnection.swift. One notify characteristic carries
 * both command responses and audio, demuxed by the leading type byte; the
 * recording session is started with retries on the first audio subscriber
 * and stopped on the last.
 */

import { PLAUD_UUIDS } from '../protocol/uuids'
import type { BleAudioCodec } from '../protocol/deviceTypes'
import {
  DeviceOperationBroker,
  DeviceOperationBrokerError,
  UncorrelatedOperationGate,
  type DeviceOperationClock
} from '../session/deviceOperationBroker'
import { DeviceCommandQueue } from '../session/deviceCommandQueue'
import { DeviceAudioStreamController } from '../session/deviceAudioStreamController'
import {
  BaseDeviceConnection,
  DeviceConnectionError,
  finishedStream,
  type AccelerometerData,
  type StreamSubscriber,
  type StreamSubscription
} from './deviceConnection'
import { FixedSizeRechunker } from './fixedSizeRechunker'
import type { DeviceTransport } from '../transport/deviceTransport'
import type { BtDevice } from '../protocol/btDevice'

const CMD_GET_BATTERY = 9
const CMD_START_RECORD = 20
const CMD_STOP_RECORD = 23
const CMD_SYNC_FILE_START = 28
const CMD_STOP_SYNC = 30

const PACKET_TYPE_COMMAND = 0x01
const PACKET_TYPE_AUDIO = 0x02
const COMMAND_TIMEOUT_MS = 10_000
const POST_CONNECT_SETTLE_MS = 2_000
const OUTPUT_CHUNK_SIZE = 80
const END_OF_STREAM_POSITION = 0xffff_ffff
const SYNC_END_SENTINEL = 0x7fff_ffff
const BATTERY_POLL_INTERVAL_MS = 60_000
const SETUP_MAX_RETRIES = 3
const SETUP_STOP_TO_START_GAP_MS = 500
const SETUP_START_TO_SYNC_GAP_MS = 1_000

const commandKey = (cmdId: number): string => `plaud-cmd:${cmdId}`

const toBytes32 = (value: number): Uint8Array =>
  Uint8Array.from([
    value & 0xff,
    (value >>> 8) & 0xff,
    (value >>> 16) & 0xff,
    (value >>> 24) & 0xff
  ])

const toBytes64 = (value: number): Uint8Array => {
  const big = BigInt(value)
  const out = new Uint8Array(8)
  for (let i = 0; i < 8; i += 1) {
    out[i] = Number((big >> BigInt(8 * i)) & 0xffn)
  }
  return out
}

const toInt32LE = (data: Uint8Array, offset: number): number => {
  const value =
    (data[offset] |
      (data[offset + 1] << 8) |
      (data[offset + 2] << 16) |
      (data[offset + 3] << 24)) >>>
    0
  return value > 0x7fff_ffff ? value - 0x1_0000_0000 : value
}

export interface PlaudBatteryState {
  level: number
  isCharging: boolean
}

export class PlaudDeviceConnection extends BaseDeviceConnection {
  private readonly commandQueue = new DeviceCommandQueue()
  private readonly commandBroker: DeviceOperationBroker
  private readonly commandGate = new UncorrelatedOperationGate()
  private readonly audioController: DeviceAudioStreamController
  private sessionId: number | null = null
  private setupAttempted = false

  constructor(args: {
    device: BtDevice
    transport: DeviceTransport
    clock?: DeviceOperationClock
  }) {
    super(args)
    this.commandBroker = new DeviceOperationBroker(this.clock)
    this.audioController = new DeviceAudioStreamController({
      start: () => this.setupRecordingSession(),
      stop: () => this.stopRecordingSession()
    })
  }

  protected override async prepareDeviceAfterConnect(): Promise<void> {
    await this.settle(POST_CONNECT_SETTLE_MS)
    this.ensureLifecycleIsActive()
    this.transport.subscribeCharacteristic(PLAUD_UUIDS.service, PLAUD_UUIDS.notifyCharacteristic, {
      onData: (data) => this.handleNotification(data),
      onFinish: (error) => {
        void this.audioController.finish(error)
      }
    })
  }

  protected override async teardownDevice(): Promise<void> {
    await this.audioController.finish(null)
    this.commandBroker.cancelAll('disconnected')
    this.commandGate.reset()
    await this.commandQueue.close()
  }

  // --- command channel -------------------------------------------------------

  /** Command frame: leading type byte 1, LE 16-bit id, payload. Timeout
   *  resolves null; a poisoned command identity throws. */
  private sendCommand(cmdId: number, payload: Uint8Array): Promise<Uint8Array | null> {
    return this.commandQueue.run(async () => {
      const key = commandKey(cmdId)
      const handle = this.commandGate.register(key)
      if (handle === null) {
        throw DeviceConnectionError.operationFailed(
          'A previous command response is ambiguous; reconnect the device'
        )
      }
      const frame = new Uint8Array(3 + payload.length)
      frame[0] = PACKET_TYPE_COMMAND
      frame[1] = cmdId & 0xff
      frame[2] = (cmdId >> 8) & 0xff
      frame.set(payload, 3)
      try {
        return await this.commandBroker.perform<Uint8Array>({
          key,
          timeoutMs: COMMAND_TIMEOUT_MS,
          onTerminal: (termination) => this.commandGate.terminal(handle, termination),
          start: () =>
            this.transport.writeCharacteristic({
              serviceUuid: PLAUD_UUIDS.service,
              characteristicUuid: PLAUD_UUIDS.writeCharacteristic,
              data: frame,
              withResponse: true
            })
        })
      } catch (error) {
        if (error instanceof DeviceOperationBrokerError && error.kind === 'timedOut') {
          return null
        }
        throw this.mapTransportError(error)
      }
    })
  }

  private handleNotification(data: Uint8Array): void {
    if (data.length === 0) return
    if (data[0] === PACKET_TYPE_AUDIO) {
      this.parseAudioChunk(data.subarray(1))
      return
    }
    if (data.length >= 3) {
      const cmdId = data[1] | (data[2] << 8)
      const key = commandKey(cmdId)
      if (this.commandGate.takeHandleForCallback(key) === null) return
      this.commandBroker.succeed(key, data.slice(3))
    }
  }

  private parseAudioChunk(payload: Uint8Array): void {
    // [0..3] session id (unused), [4..7] LE position, [8] length, [9..] Opus.
    if (payload.length < 9) return
    const position =
      (payload[4] | (payload[5] << 8) | (payload[6] << 16) | (payload[7] << 24)) >>> 0
    if (position === END_OF_STREAM_POSITION) return
    const length = payload[8]
    if (payload.length < 9 + length) return
    this.audioController.yieldFrame(payload.slice(9, 9 + length))
  }

  // --- recording session -----------------------------------------------------

  private async startRecord(): Promise<{ sessionId: number; startTime: number } | null> {
    const payload = new Uint8Array(12)
    payload.set(toBytes32(1), 0)
    const response = await this.sendCommand(CMD_START_RECORD, payload)
    if (response === null || response.length < 10) return null
    return { sessionId: toInt32LE(response, 0), startTime: toInt32LE(response, 4) }
  }

  private async stopRecord(sessionId: number): Promise<void> {
    const payload = new Uint8Array(8)
    payload.set(toBytes32(sessionId), 0)
    const response = await this.sendCommand(CMD_STOP_RECORD, payload)
    if (response === null) {
      throw DeviceConnectionError.operationFailed('PLAUD did not acknowledge STOP_RECORD')
    }
  }

  private async startSync(sessionId: number, start: number): Promise<boolean> {
    const payload = new Uint8Array(24)
    payload.set(toBytes64(sessionId), 0)
    payload.set(toBytes64(start), 8)
    payload.set(toBytes64(SYNC_END_SENTINEL), 16)
    const response = await this.sendCommand(CMD_SYNC_FILE_START, payload)
    return response !== null
  }

  private async stopSync(): Promise<void> {
    // Raw frame with no response correlation, still serialized on the queue.
    const frame = Uint8Array.from([
      PACKET_TYPE_COMMAND,
      CMD_STOP_SYNC & 0xff,
      (CMD_STOP_SYNC >> 8) & 0xff,
      0x01
    ])
    await this.commandQueue.run(() =>
      this.transport.writeCharacteristic({
        serviceUuid: PLAUD_UUIDS.service,
        characteristicUuid: PLAUD_UUIDS.writeCharacteristic,
        data: frame,
        withResponse: true
      })
    )
  }

  private async setupRecordingSession(): Promise<void> {
    this.setupAttempted = true
    let lastError: Error | null = null
    for (let attempt = 0; attempt < SETUP_MAX_RETRIES; attempt += 1) {
      if (attempt > 0) {
        await this.settle(attempt * 1_000)
      }
      try {
        await this.stopRecord(0)
        await this.settle(SETUP_STOP_TO_START_GAP_MS)
        const record = await this.startRecord()
        if (record === null) {
          lastError = DeviceConnectionError.operationFailed(
            'PLAUD did not acknowledge START_RECORD'
          )
          continue
        }
        this.sessionId = record.sessionId
        await this.settle(SETUP_START_TO_SYNC_GAP_MS)
        if (!(await this.startSync(record.sessionId, record.startTime))) {
          lastError = DeviceConnectionError.operationFailed(
            'PLAUD did not acknowledge SYNC_FILE_START'
          )
          continue
        }
        return
      } catch (error) {
        lastError = error instanceof Error ? error : new Error(String(error))
      }
    }
    throw lastError ?? DeviceConnectionError.operationFailed('PLAUD recording session setup failed')
  }

  private async stopRecordingSession(): Promise<void> {
    if (!this.setupAttempted) return
    const failures: string[] = []
    try {
      await this.stopSync()
    } catch (error) {
      failures.push(error instanceof Error ? error.message : String(error))
    }
    try {
      await this.stopRecord(this.sessionId ?? 0)
    } catch (error) {
      failures.push(error instanceof Error ? error.message : String(error))
    }
    if (failures.length > 0) {
      await this.transport.disconnect()
      throw DeviceConnectionError.operationFailed(failures.join('; '))
    }
  }

  // --- audio -----------------------------------------------------------------

  override async getAudioCodec(): Promise<BleAudioCodec> {
    return 'opusFS320'
  }

  override getAudioStream(subscriber: StreamSubscriber<Uint8Array>): StreamSubscription {
    const rechunker = new FixedSizeRechunker(OUTPUT_CHUNK_SIZE)
    const subscription = this.audioController.subscribe({
      onFrame: (frame) => {
        for (const chunk of rechunker.push(frame)) {
          subscriber.onValue(chunk)
        }
      },
      onFinish: (error) => {
        const tail = rechunker.flush()
        if (tail !== null) subscriber.onValue(tail)
        subscriber.onFinish(error)
      }
    })
    return { cancel: () => subscription.cancel() }
  }

  // --- battery (byte order reversed vs Bee) ----------------------------------

  async getBatteryState(): Promise<PlaudBatteryState | null> {
    try {
      const response = await this.sendCommand(CMD_GET_BATTERY, new Uint8Array(0))
      if (response === null || response.length < 2) return null
      return { level: response[1], isCharging: response[0] !== 0 }
    } catch {
      return null
    }
  }

  override async getBatteryLevel(): Promise<number> {
    const state = await this.getBatteryState()
    return state?.level ?? -1
  }

  override getBatteryLevelStream(subscriber: StreamSubscriber<number>): StreamSubscription {
    const abort = new AbortController()
    this.sessionAbort.signal.addEventListener('abort', () => abort.abort(), { once: true })
    void (async () => {
      let lastLevel: number | null = null
      for (;;) {
        // A poisoned command id can never produce another response, so polling
        // it forever would just report a stale level indefinitely.
        if (this.commandGate.isPoisoned(commandKey(CMD_GET_BATTERY))) {
          subscriber.onFinish(
            DeviceConnectionError.operationFailed(
              'PLAUD battery reporting is ambiguous; reconnect the device'
            )
          )
          return
        }
        const state = await this.getBatteryState()
        if (abort.signal.aborted) return
        if (state !== null && state.level !== lastLevel) {
          lastLevel = state.level
          subscriber.onValue(state.level)
        }
        const outcome = await this.clock.sleep(BATTERY_POLL_INTERVAL_MS, abort.signal)
        if (outcome !== 'elapsed') return
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
