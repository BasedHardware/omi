/**
 * Bee connection — Windows port of macOS Connections/BeeDeviceConnection.swift.
 * Commands multiplex over one control characteristic as [u16 id LE, payload]
 * frames; mute and unmute share command id 0xC006, which is why a poisoned
 * mute identity retires the whole session instead of retrying.
 */

import { BEE_UUIDS } from '../protocol/uuids'
import type { BleAudioCodec } from '../protocol/deviceTypes'
import {
  DeviceOperationBroker,
  DeviceOperationBrokerError,
  UncorrelatedOperationGate
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
import { AdtsFrameExtractor } from './adtsFrameExtractor'
import type { DeviceTransport } from '../transport/deviceTransport'
import type { BtDevice } from '../protocol/btDevice'
import type { DeviceOperationClock } from '../session/deviceOperationBroker'

/** Mute and unmute share this id; battery is 0xC00F. */
const CMD_AUDIO_MUTE_UNMUTE = 0xc006
const CMD_BATTERY = 0xc00f
const ECHO_RESPONSE_CODE = 0x8000
const COMMAND_TIMEOUT_MS = 5_000
const POST_CONNECT_SETTLE_MS = 1_000
const BATTERY_POLL_INTERVAL_MS = 60_000
const AUDIO_PACKET_HEADER_BYTES = 2

const commandKey = (cmdId: number): string => `bee-cmd:${cmdId}`

export interface BeeBatteryState {
  level: number
  isCharging: boolean
}

export class BeeDeviceConnection extends BaseDeviceConnection {
  private readonly commandQueue = new DeviceCommandQueue()
  private readonly commandBroker: DeviceOperationBroker
  private readonly commandGate = new UncorrelatedOperationGate()
  private readonly adts = new AdtsFrameExtractor()
  private readonly audioController: DeviceAudioStreamController

  constructor(args: {
    device: BtDevice
    transport: DeviceTransport
    clock?: DeviceOperationClock
  }) {
    super(args)
    this.commandBroker = new DeviceOperationBroker(this.clock)
    this.audioController = new DeviceAudioStreamController({
      start: () => this.startAudioSession(),
      stop: () => this.stopAudioSession()
    })
  }

  protected override async updateDeviceInfo(): Promise<void> {
    this.device.modelNumber = 'Bee'
    this.device.firmwareRevision = '1.0.0'
    this.device.hardwareRevision = '1.0.0'
    this.device.manufacturerName = 'Bee'
  }

  protected override async prepareDeviceAfterConnect(): Promise<void> {
    await this.settle(POST_CONNECT_SETTLE_MS)
    this.ensureLifecycleIsActive()
    this.transport.subscribeCharacteristic(BEE_UUIDS.service, BEE_UUIDS.control, {
      onData: (data) => this.handleControlResponse(data),
      onFinish: () => undefined
    })
    this.transport.subscribeCharacteristic(BEE_UUIDS.service, BEE_UUIDS.audio, {
      onData: (data) => this.handleAudioPacket(data),
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

  /** Sends one command frame and awaits its correlated response; a timeout
   *  resolves null (matching mac), a poisoned identity throws. */
  private sendCommand(cmdId: number, payload: Uint8Array): Promise<Uint8Array | null> {
    return this.commandQueue.run(async () => {
      const key = commandKey(cmdId)
      const handle = this.commandGate.register(key)
      if (handle === null) {
        throw DeviceConnectionError.operationFailed(
          'A previous command response is ambiguous; reconnect the device'
        )
      }
      const frame = new Uint8Array(2 + payload.length)
      frame[0] = cmdId & 0xff
      frame[1] = (cmdId >> 8) & 0xff
      frame.set(payload, 2)
      try {
        return await this.commandBroker.perform<Uint8Array>({
          key,
          timeoutMs: COMMAND_TIMEOUT_MS,
          onTerminal: (termination) => this.commandGate.terminal(handle, termination),
          start: () =>
            this.transport.writeCharacteristic({
              serviceUuid: BEE_UUIDS.service,
              characteristicUuid: BEE_UUIDS.control,
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

  private handleControlResponse(data: Uint8Array): void {
    if (data.length < 2) return
    const responseCode = data[0] | (data[1] << 8)
    const payload = data.subarray(2)
    if (responseCode === ECHO_RESPONSE_CODE && payload.length >= 2) {
      const echoedCmd = payload[0] | (payload[1] << 8)
      this.completeCommand(echoedCmd, payload.subarray(2))
      return
    }
    this.completeCommand(responseCode, payload)
  }

  private completeCommand(cmdId: number, payload: Uint8Array): void {
    const key = commandKey(cmdId)
    if (this.commandGate.takeHandleForCallback(key) === null) return
    this.commandBroker.succeed(key, payload.slice())
  }

  // --- audio -----------------------------------------------------------------

  private handleAudioPacket(data: Uint8Array): void {
    if (data.length <= AUDIO_PACKET_HEADER_BYTES) return
    const frames = this.adts.push(data.subarray(AUDIO_PACKET_HEADER_BYTES))
    for (const frame of frames) {
      this.audioController.yieldFrame(frame)
    }
  }

  private async startAudioSession(): Promise<void> {
    this.adts.clear()
    const response = await this.sendCommand(CMD_AUDIO_MUTE_UNMUTE, Uint8Array.from([0x01]))
    if (response === null) {
      throw DeviceConnectionError.operationFailed('Bee did not acknowledge audio start')
    }
  }

  private async stopAudioSession(): Promise<void> {
    this.adts.clear()
    // A mute command on a dead link just burns the 5 second command timeout
    // before teardown can continue, delaying the disconnect notification and
    // the reconnect that follows it.
    if (!this.transport.isConnected()) {
      this.commandBroker.cancelAll('disconnected')
      return
    }
    try {
      if (this.commandGate.isPoisoned(commandKey(CMD_AUDIO_MUTE_UNMUTE))) {
        // Mute and unmute share one command id: with the identity poisoned, a
        // late response could alias a future unmute, so write the raw mute
        // uncorrelated and retire the session.
        await this.commandQueue.run(() =>
          this.transport.writeCharacteristic({
            serviceUuid: BEE_UUIDS.service,
            characteristicUuid: BEE_UUIDS.control,
            data: Uint8Array.from([0x06, 0xc0, 0x00]),
            withResponse: true
          })
        )
        await this.transport.disconnect()
        throw DeviceConnectionError.operationFailed(
          'Bee audio command identity is ambiguous; reconnect the device'
        )
      }
      const response = await this.sendCommand(CMD_AUDIO_MUTE_UNMUTE, Uint8Array.from([0x00]))
      if (response === null) {
        throw DeviceConnectionError.operationFailed('Bee did not acknowledge audio stop')
      }
    } catch (error) {
      await this.transport.disconnect()
      throw error
    } finally {
      this.adts.clear()
    }
  }

  override async getAudioCodec(): Promise<BleAudioCodec> {
    return 'aac'
  }

  override getAudioStream(subscriber: StreamSubscriber<Uint8Array>): StreamSubscription {
    const subscription = this.audioController.subscribe({
      onFrame: (frame) => subscriber.onValue(frame),
      onFinish: (error) => subscriber.onFinish(error)
    })
    return { cancel: () => subscription.cancel() }
  }

  // --- battery ---------------------------------------------------------------

  async getBatteryState(): Promise<BeeBatteryState | null> {
    try {
      const response = await this.sendCommand(CMD_BATTERY, new Uint8Array(0))
      if (response === null || response.length < 2) return null
      return { level: response[0], isCharging: response[1] !== 0 }
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
