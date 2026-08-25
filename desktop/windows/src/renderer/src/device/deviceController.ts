/**
 * The wearable host controller: the one object in the device window that turns
 * bridge commands into device sessions and device state back into bridge
 * events. It owns the session coordinator, builds a transport per attempt,
 * starts audio decoding when a session goes ready, and drives the listen lane.
 *
 * Every external edge is injected (Bluetooth access, bridge, audio service,
 * lane factory) so the whole policy is testable without Electron, WebBluetooth,
 * or a real device.
 */

import type {
  DeviceCommand,
  DeviceEvent,
  DeviceSettings,
  DeviceStorageState,
  WearableConnectionState,
  WearableDeviceInfo
} from '../../../shared/types'
import { makeBtDevice, detectDeviceType, type BtDevice } from './protocol/btDevice'
import type { DeviceType } from './protocol/deviceTypes'
import { createDeviceConnection } from './connections/deviceConnectionFactory'
import type { DeviceConnection } from './connections/deviceConnection'
import { BleTransport } from './transport/bleTransport'
import type { BlePhysicalDriver } from './transport/blePhysicalDriver'
import { BluetoothConnectionLeaseRegistry } from './session/bluetoothConnectionLease'
import {
  DeviceSessionCoordinator,
  type DeviceSessionSnapshot
} from './session/deviceSessionCoordinator'
import { BleAudioService } from './audio/bleAudioService'
import type { DeviceListenSession } from './lane/deviceListenSession'
import { StorageDrainService, createWalDrainSink } from './storage/storageDrainService'
import type { DrainSink } from './storage/ringDrain'
import { CODEC_SAMPLE_RATE, codecFrameSize, type BleAudioCodec } from './protocol/deviceTypes'

/** Low-battery latch threshold, matching the mac notification rule. */
export const LOW_BATTERY_PERCENT = 20

export interface BluetoothAccess {
  /** Opens the chooser (a user gesture on the UI side led here) and returns a
   *  driver for the granted device, or null when the user cancelled. */
  requestDevice: () => Promise<{ driver: BlePhysicalDriver; serviceUuids: string[] } | null>
  /** Re-acquires a previously granted device without a chooser, when the
   *  platform allows it; null when the device is not currently reachable. */
  reacquire: (
    deviceId: string
  ) => Promise<{ driver: BlePhysicalDriver; serviceUuids: string[] } | null>
}

export interface DeviceControllerDeps {
  bluetooth: BluetoothAccess
  emit: (event: DeviceEvent) => void
  settings: () => DeviceSettings
  saveSettings: (patch: Partial<DeviceSettings>) => Promise<void>
  audioService?: BleAudioService
  /** Built per listening session; null disables the lane (used in tests). */
  createLane?: () => DeviceListenSession | null
  /** Persists audio recovered off the device. Omitted disables recovery, which
   *  is what a build with no offline log wants. */
  storeRecovered?: (audio: {
    bytes: Uint8Array
    timerStart: number
    seconds: number
    totalFrames: number
    codec: string
    sampleRate: number
    frameSize: number
    device: string
  }) => Promise<'stored' | 'duplicate' | 'failed'>
  /** Injectable so tests drive the drain's waits without real time. */
  sleep?: (ms: number, signal: AbortSignal) => Promise<'elapsed' | 'aborted'>
}

const IDLE_STORAGE: DeviceStorageState = {
  phase: 'unknown',
  items: 0,
  estimatedSeconds: 0,
  recovered: 0,
  message: null
}

export class DeviceController {
  private readonly leases = new BluetoothConnectionLeaseRegistry()
  private readonly audio: BleAudioService
  private readonly coordinator: DeviceSessionCoordinator
  private pendingDriver: BlePhysicalDriver | null = null
  private lane: DeviceListenSession | null = null
  private lowBatteryLatched = false
  private lastBatteryLevel: number | null = null
  private batterySubscription: { cancel: () => void } | null = null
  private drain: StorageDrainService | null = null
  private storage: DeviceStorageState = IDLE_STORAGE
  private recovered = 0

  constructor(private readonly deps: DeviceControllerDeps) {
    this.audio = deps.audioService ?? new BleAudioService()
    const paired = deps.settings().pairedDevice
    this.coordinator = new DeviceSessionCoordinator(
      {
        connectionFactory: (device, generation) => this.buildConnection(device, generation),
        onSnapshot: (snapshot) => {
          this.deps.emit({
            type: 'device-state',
            state: phaseToState(snapshot),
            device: snapshot.connectedDevice ? toDeviceInfo(snapshot.connectedDevice) : null
          })
        },
        onSessionEnded: () => this.stopStreaming(),
        onReconnectRequested: (request) => {
          void this.reconnect(request.device, request)
        },
        onDiscoveryRequested: () => {
          // A delayed retry needs a fresh platform handle; reacquire covers it
          // without a chooser, so nothing user-visible happens here.
        }
      },
      { pairedDevice: paired === null ? null : fromDeviceInfo(paired) }
    )
    this.coordinator.autoReconnectEnabled = deps.settings().autoReconnect
  }

  get sessionCoordinator(): DeviceSessionCoordinator {
    return this.coordinator
  }

  /** Bridge entry point. */
  async handleCommand(command: DeviceCommand): Promise<void> {
    switch (command.type) {
      case 'device-pair':
        await this.pair()
        return
      case 'device-connect':
        await this.connectPaired()
        return
      case 'device-disconnect':
        await this.coordinator.disconnect(null)
        return
      case 'device-forget':
        await this.forget()
        return
      case 'device-settings':
        this.applySettings(command.settings)
        return
      case 'device-request-state':
        this.publishCurrentState()
        return
      case 'device-storage-recover':
        await this.recoverStoredAudio()
        return
      case 'device-storage-cancel':
        this.drain?.cancel()
        return
      case 'device-pair-cancel':
      case 'device-pair-select':
      case 'auth-changed':
        return
    }
  }

  /**
   * Transfers the audio the device recorded while it was away from this
   * machine into the offline log, where the sync engine uploads it.
   *
   * User-initiated only. A full device can take minutes to drain and shares the
   * radio with the live session, so starting it on connect would silently
   * degrade recording for anyone who never asked for it.
   */
  private async recoverStoredAudio(): Promise<void> {
    const drain = this.drain
    if (drain === null) {
      this.publishStorage({ phase: 'unsupported', message: null })
      return
    }
    if (drain.isRunning) return

    this.recovered = 0
    this.publishStorage({
      phase: 'recovering',
      recovered: 0,
      message: 'Looking for recordings on your device'
    })
    const result = await drain.drainOnce().catch((error: unknown) => {
      this.publishStorage({
        phase: 'failed',
        message: error instanceof Error ? error.message : String(error)
      })
      return null
    })
    if (result === null || this.drain !== drain) return
    const recovered = this.recovered

    switch (result.kind) {
      case 'drained':
      case 'idle':
        this.publishStorage({
          phase: 'empty',
          items: 0,
          estimatedSeconds: 0,
          recovered,
          message: recovered > 0 ? plural(recovered, 'Recovered') : 'Nothing new to recover'
        })
        return
      case 'incomplete':
        // The device keeps whatever was not committed, so this is a pause and
        // not a loss; saying so stops it reading as audio gone missing.
        this.publishStorage({
          phase: 'available',
          recovered,
          message:
            result.reason === 'cancelled'
              ? `Stopped. ${plural(recovered, 'Recovered')}, the rest is still on your device.`
              : `Stopped after ${result.reason}. ${plural(recovered, 'Recovered')}, the rest is still on your device.`
        })
        return
      case 'unsupported':
        this.publishStorage({ phase: 'unsupported', items: 0, message: null })
        return
    }
  }

  /** Asks a freshly connected device what it is holding, without reading it. */
  private async probeStorage(): Promise<void> {
    const drain = this.drain
    if (drain === null) return
    const probe = await drain.probe().catch(() => null)
    if (this.drain !== drain) return
    if (probe === null) {
      this.publishStorage({ phase: 'empty', items: 0, estimatedSeconds: 0, message: null })
      return
    }
    this.publishStorage({
      phase: 'available',
      items: probe.items,
      estimatedSeconds: probe.estimatedSeconds,
      message: null
    })
  }

  private publishStorage(patch: Partial<DeviceStorageState>): void {
    this.storage = { ...this.storage, ...patch }
    this.deps.emit({ type: 'device-storage', storage: this.storage })
  }

  /** Re-emits everything a freshly opened UI needs: the hidden host may have
   *  connected long before Settings was opened, so a UI that only subscribes to
   *  future events would show a disconnected device. */
  private publishCurrentState(): void {
    const snapshot = this.coordinator.snapshot
    this.deps.emit({
      type: 'device-state',
      state: phaseToState(snapshot),
      device: snapshot.connectedDevice ? toDeviceInfo(snapshot.connectedDevice) : null
    })
    if (this.lastBatteryLevel !== null) {
      this.deps.emit({ type: 'device-battery', level: this.lastBatteryLevel })
    }
    this.deps.emit({ type: 'device-storage', storage: this.storage })
  }

  private async pair(): Promise<void> {
    this.deps.emit({ type: 'device-state', state: 'scanning', device: null })
    let granted: Awaited<ReturnType<BluetoothAccess['requestDevice']>> = null
    try {
      granted = await this.deps.bluetooth.requestDevice()
    } catch (error) {
      this.fail(error)
      return
    }
    if (granted === null) {
      this.deps.emit({ type: 'device-state', state: 'idle', device: null })
      return
    }
    const type = detectDeviceType({
      name: granted.driver.name,
      serviceUuids: granted.serviceUuids
    })
    if (type === null) {
      this.deps.emit({
        type: 'device-error',
        message: 'That device is not a supported Omi wearable.'
      })
      this.deps.emit({ type: 'device-state', state: 'idle', device: null })
      return
    }
    const device = makeBtDevice({ id: granted.driver.id, name: granted.driver.name, type })
    this.pendingDriver = granted.driver
    await this.deps.saveSettings({ pairedDevice: toDeviceInfo(device) })
    this.coordinator.setPairedDevice(device)
    this.deps.emit({ type: 'device-paired', device: toDeviceInfo(device) })
    await this.openSession(device)
  }

  private async connectPaired(): Promise<void> {
    const paired = this.deps.settings().pairedDevice
    if (paired === null) {
      this.deps.emit({ type: 'device-error', message: 'No device is paired yet.' })
      return
    }
    await this.openSession(fromDeviceInfo(paired))
  }

  private async openSession(device: BtDevice): Promise<void> {
    if (this.pendingDriver === null) {
      const reacquired = await this.deps.bluetooth.reacquire(device.id).catch(() => null)
      if (reacquired === null) {
        this.deps.emit({
          type: 'device-error',
          message: 'The device is not currently available over Bluetooth.'
        })
        return
      }
      this.pendingDriver = reacquired.driver
    }
    try {
      await this.coordinator.connect(device)
      await this.onSessionReady()
    } catch (error) {
      this.fail(error)
    }
  }

  private async reconnect(
    device: BtDevice,
    request: Parameters<DeviceSessionCoordinator['connect']>[1]
  ): Promise<void> {
    const reacquired = await this.deps.bluetooth.reacquire(device.id).catch(() => null)
    if (reacquired !== null) this.pendingDriver = reacquired.driver
    try {
      await this.coordinator.connect(device, request)
      await this.onSessionReady()
    } catch {
      // The coordinator already recorded the failure and scheduled the next
      // retry; surfacing an error toast on every silent retry would be noise.
    }
  }

  private buildConnection(device: BtDevice, generation: number): DeviceConnection | null {
    const driver = this.pendingDriver
    if (driver === null) return null
    this.pendingDriver = null
    const transport = new BleTransport({
      driver,
      sessionGeneration: generation,
      leases: this.leases
    })
    const connection = createDeviceConnection({ device, transport })
    if (connection === null) return null
    connection.delegate = {
      didDisconnectUnexpectedly: () => {
        this.coordinator.handleUnexpectedDisconnect(connection)
      },
      didDetectFall: () => {
        this.deps.emit({ type: 'device-error', message: 'Possible fall detected.' })
      }
    }
    return connection
  }

  private async onSessionReady(): Promise<void> {
    const connection = this.coordinator.connection
    if (connection === null) return
    this.watchBattery(connection)
    await this.buildDrain(connection)
    if (!this.deps.settings().deviceListenEnabled) return
    await this.startStreaming(connection)
  }

  /**
   * Builds the recovery service for this session and reports what the device is
   * holding. Reading the codec is what tells the drain how to time the audio it
   * recovers, so a family that will not answer gets no recovery rather than a
   * guessed one.
   */
  private async buildDrain(connection: DeviceConnection): Promise<void> {
    this.drain = null
    this.storage = IDLE_STORAGE
    if (this.deps.storeRecovered === undefined || !connection.canStreamAudio()) return
    let codec: BleAudioCodec
    try {
      codec = await connection.getAudioCodec()
    } catch {
      return
    }
    if (this.coordinator.connection !== connection) return
    this.drain = new StorageDrainService({
      connection,
      sink: this.walSink(connection, codec),
      codec,
      sleep: this.deps.sleep ?? sleepUnlessAborted,
      onProgress: (message) => this.publishStorage({ message })
    })
    await this.probeStorage()
  }

  /** Sends one recovered recording to the offline log and counts what it did. */
  private walSink(connection: DeviceConnection, codec: BleAudioCodec): DrainSink {
    const store = this.deps.storeRecovered
    const device = connection.device.type
    return createWalDrainSink(async (args) => {
      if (store === undefined) return 'failed'
      const outcome = await store({
        bytes: args.bytes,
        timerStart: args.startEpochSeconds,
        seconds: args.seconds,
        totalFrames: args.frameCount,
        codec,
        sampleRate: CODEC_SAMPLE_RATE,
        frameSize: codecFrameSize(codec),
        device
      })
      if (outcome === 'stored') {
        this.recovered += 1
        this.publishStorage({ recovered: this.recovered })
      }
      return outcome
    })
  }

  private watchBattery(connection: DeviceConnection): void {
    this.batterySubscription?.cancel()
    this.lowBatteryLatched = false
    this.batterySubscription = connection.getBatteryLevelStream({
      onValue: (level) => {
        this.lastBatteryLevel = level
        this.deps.emit({ type: 'device-battery', level })
        // Latch so a battery hovering at the threshold cannot spam the funnel;
        // it re-arms once the device charges back above it.
        if (level < LOW_BATTERY_PERCENT && !this.lowBatteryLatched) {
          this.lowBatteryLatched = true
          this.deps.emit({
            type: 'device-error',
            message: `Device battery is at ${level}%.`
          })
        } else if (level >= LOW_BATTERY_PERCENT) {
          this.lowBatteryLatched = false
        }
      },
      onFinish: () => {
        this.batterySubscription = null
      }
    })
  }

  private async startStreaming(connection: DeviceConnection): Promise<void> {
    // A family with no audio to stream would open a conversation that never
    // receives a sample and is torn down immediately.
    if (!connection.canStreamAudio()) {
      this.deps.emit({ type: 'device-listen-state', state: 'unsupported' })
      return
    }
    const lane = this.deps.createLane?.() ?? null
    this.lane = lane
    if (lane !== null) {
      const opened = await lane.start()
      this.deps.emit({ type: 'device-listen-state', state: lane.currentState })
      if (!opened) {
        // The microphone lane holds the only safe conversation socket. Stop
        // before dropping the reference: a lane that failed after opening a
        // socket schedules its own retry, which would otherwise run unowned.
        lane.stop()
        this.lane = null
        return
      }
      // Disconnect or a settings change can land while the lane opens.
      if (this.coordinator.connection !== connection || !this.deps.settings().deviceListenEnabled) {
        lane.stop()
        this.lane = null
        return
      }
    }
    let started = false
    try {
      started = await this.audio.startProcessing(connection, {
        onPcm: (pcm) => this.lane?.feed(pcm),
        onCodec: (codec) => this.deps.emit({ type: 'device-codec', codec }),
        onDegradedChange: (degraded) => this.deps.emit({ type: 'device-audio-degraded', degraded }),
        onEnded: () => this.stopStreaming()
      })
    } catch (error) {
      this.deps.emit({
        type: 'device-error',
        message: error instanceof Error ? error.message : String(error)
      })
    }
    if (!started) {
      // An open lane with no decoder behind it records nothing.
      this.lane?.stop()
      this.lane = null
    }
  }

  private stopStreaming(): void {
    this.audio.stopProcessing()
    this.lane?.stop()
    this.lane = null
    this.batterySubscription?.cancel()
    this.batterySubscription = null
    // A transfer outlives its connection as a set of pending reads that will
    // never answer, so it is stopped with the session that owns it.
    this.drain?.cancel()
    this.drain = null
    if (this.storage !== IDLE_STORAGE) {
      this.storage = IDLE_STORAGE
      this.deps.emit({ type: 'device-storage', storage: this.storage })
    }
  }

  private applySettings(settings: DeviceSettings): void {
    this.coordinator.autoReconnectEnabled = settings.autoReconnect
    if (!settings.autoReconnect) this.coordinator.stopReconnecting()
    const connection = this.coordinator.connection
    if (settings.deviceListenEnabled && connection !== null && !this.audio.isProcessing) {
      void this.startStreaming(connection)
    } else if (!settings.deviceListenEnabled && this.audio.isProcessing) {
      this.stopStreaming()
    }
  }

  private async forget(): Promise<void> {
    this.stopStreaming()
    await this.coordinator.unpair()
    await this.deps.saveSettings({ pairedDevice: null })
    this.deps.emit({ type: 'device-forgotten' })
    this.deps.emit({ type: 'device-state', state: 'idle', device: null })
  }

  private fail(error: unknown): void {
    const message = error instanceof Error ? error.message : String(error)
    this.deps.emit({ type: 'device-error', message })
    this.deps.emit({ type: 'device-state', state: 'error', device: null })
  }

  /** Window teardown. */
  dispose(): void {
    this.stopStreaming()
    void this.coordinator.disconnect(null)
  }
}

const plural = (count: number, verb: string): string =>
  `${verb} ${count} recording${count === 1 ? '' : 's'}`

/** Default drain wait: resolves early when the transfer is abandoned. */
const sleepUnlessAborted = (ms: number, signal: AbortSignal): Promise<'elapsed' | 'aborted'> =>
  new Promise((resolve) => {
    if (signal.aborted) {
      resolve('aborted')
      return
    }
    const timer = setTimeout(() => resolve('elapsed'), ms)
    signal.addEventListener(
      'abort',
      () => {
        clearTimeout(timer)
        resolve('aborted')
      },
      { once: true }
    )
  })

const phaseToState = (snapshot: DeviceSessionSnapshot): WearableConnectionState => {
  switch (snapshot.phase.kind) {
    case 'ready':
      return 'connected'
    case 'connecting':
      return 'connecting'
    case 'waitingToReconnect':
      return 'reconnecting'
    default:
      return snapshot.failureMessage !== null ? 'error' : 'idle'
  }
}

const toDeviceInfo = (device: BtDevice): WearableDeviceInfo => ({
  id: device.id,
  name: device.name,
  type: device.type
})

const fromDeviceInfo = (info: WearableDeviceInfo): BtDevice =>
  makeBtDevice({ id: info.id, name: info.name, type: info.type as DeviceType })
