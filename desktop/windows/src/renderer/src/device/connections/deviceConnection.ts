/**
 * Device connection base contract — Windows port of macOS
 * Connections/DeviceConnection.swift. BaseDeviceConnection implements the
 * template-method lifecycle (connect exactly once per instance, joined
 * teardown, unexpected-disconnect delegation) and the Omi-shaped GATT
 * defaults; families override the hooks and the surfaces their firmware
 * actually speaks.
 */

import type { BtDevice } from '../protocol/btDevice'
import {
  codecFromCharacteristicByte,
  OMI_FEATURE_BITS,
  validateWifiCredentials,
  type BleAudioCodec,
  type OmiFeatureName,
  type WifiSyncErrorCode
} from '../protocol/deviceTypes'
import {
  ACCELEROMETER_UUIDS,
  BATTERY_UUIDS,
  BUTTON_UUIDS,
  DEVICE_INFO_UUIDS,
  OMI_UUIDS,
  SPEAKER_UUIDS,
  STORAGE_UUIDS
} from '../protocol/uuids'
import type { DeviceTransport, DeviceTransportState } from '../transport/deviceTransport'
import { DeviceTransportError } from '../transport/deviceTransport'
import {
  RealDeviceOperationClock,
  type DeviceOperationClock
} from '../session/deviceOperationBroker'
import type { SubjectSubscriber, SubjectSubscription } from './subject'

export type DeviceConnectionErrorKind =
  | 'alreadyConnected'
  | 'connectionFailed'
  | 'notConnected'
  | 'operationFailed'

export class DeviceConnectionError extends Error {
  readonly kind: DeviceConnectionErrorKind

  private constructor(kind: DeviceConnectionErrorKind, message: string) {
    super(message)
    this.name = 'DeviceConnectionError'
    this.kind = kind
  }

  static alreadyConnected(): DeviceConnectionError {
    return new DeviceConnectionError(
      'alreadyConnected',
      'This connection session has already started'
    )
  }

  static connectionFailed(detail: string): DeviceConnectionError {
    return new DeviceConnectionError('connectionFailed', detail)
  }

  static notConnected(): DeviceConnectionError {
    return new DeviceConnectionError('notConnected', 'Device is not connected')
  }

  static operationFailed(detail: string): DeviceConnectionError {
    return new DeviceConnectionError('operationFailed', detail)
  }
}

export interface OrientedImage {
  imageData: Uint8Array
  orientationDegrees: 0 | 90 | 180 | 270
}

export interface AccelerometerData {
  accelX: number
  accelY: number
  accelZ: number
  gyroX: number
  gyroY: number
  gyroZ: number
  /** Acceleration-only magnitude. */
  magnitude: number
  /** Fall heuristic: magnitude above 30 raw units. */
  indicatesFall: boolean
}

export const makeAccelerometerData = (
  accelX: number,
  accelY: number,
  accelZ: number,
  gyroX: number,
  gyroY: number,
  gyroZ: number
): AccelerometerData => {
  const magnitude = Math.sqrt(accelX * accelX + accelY * accelY + accelZ * accelZ)
  return { accelX, accelY, accelZ, gyroX, gyroY, gyroZ, magnitude, indicatesFall: magnitude > 30.0 }
}

export interface DeviceConnectionDelegate {
  didDisconnectUnexpectedly(device: BtDevice): void
  didDetectFall(data: AccelerometerData): void
}

export type StreamSubscriber<T> = SubjectSubscriber<T>
export type StreamSubscription = SubjectSubscription

export interface WifiSyncResult {
  code: WifiSyncErrorCode
}

export interface DeviceConnection {
  device: BtDevice
  readonly transport: DeviceTransport
  readonly sessionGeneration: number
  lastPongAt: number | null
  delegate: DeviceConnectionDelegate | null

  connect(): Promise<void>
  disconnect(): Promise<void>
  unpair(): Promise<void>
  isConnected(): boolean
  ping(): boolean

  getBatteryLevel(): Promise<number>
  getBatteryLevelStream(subscriber: StreamSubscriber<number>): StreamSubscription

  getAudioCodec(): Promise<BleAudioCodec>
  getAudioStream(subscriber: StreamSubscriber<Uint8Array>): StreamSubscription
  /** False when the family cannot stream audio to this client at all, so a
   *  caller can skip opening a transcription session that would never receive
   *  a sample. */
  canStreamAudio(): boolean

  getButtonState(): Promise<Uint8Array>
  getButtonStream(subscriber: StreamSubscriber<Uint8Array>): StreamSubscription

  getStorageList(): Promise<number[]>
  writeToStorage(fileNum: number, command: number, offset: number): Promise<void>
  getStorageStream(subscriber: StreamSubscriber<Uint8Array>): StreamSubscription

  hasPhotoStreaming(): Promise<boolean>
  startPhotoCapture(): Promise<boolean>
  stopPhotoCapture(): Promise<boolean>
  getImageStream(subscriber: StreamSubscriber<OrientedImage>): StreamSubscription

  getAccelerometerStream(subscriber: StreamSubscriber<AccelerometerData>): StreamSubscription

  playHaptic(level: number): Promise<boolean>
  getFeatures(): Promise<OmiFeatureName[]>

  setLedDimRatio(ratio: number): Promise<boolean>
  getLedDimRatio(): Promise<number | null>
  setMicGain(gain: number): Promise<boolean>
  getMicGain(): Promise<number | null>

  isWifiSyncSupported(): Promise<boolean>
  setupWifiSync(ssid: string, password: string): Promise<WifiSyncResult>
  startWifiSync(): Promise<boolean>
  stopWifiSync(): Promise<boolean>
  getWifiSyncStatusStream(subscriber: StreamSubscriber<number>): StreamSubscription
}

const NO_SUBSCRIPTION: StreamSubscription = { cancel: () => undefined }

/** Immediately-finished stream helper for unsupported surfaces. */
export const finishedStream = <T>(
  subscriber: StreamSubscriber<T>,
  error: Error | null = null
): StreamSubscription => {
  subscriber.onFinish(error)
  return NO_SUBSCRIPTION
}

const decodeInt16LE = (lo: number, hi: number): number => {
  const value = lo | (hi << 8)
  return value > 0x7fff ? value - 0x10000 : value
}

export class BaseDeviceConnection implements DeviceConnection {
  device: BtDevice
  readonly transport: DeviceTransport
  delegate: DeviceConnectionDelegate | null = null
  lastPongAt: number | null = null

  protected readonly clock: DeviceOperationClock
  protected cachedFeatures: OmiFeatureName[] | null = null
  protected readonly sessionAbort = new AbortController()

  private didStartLifecycle = false
  private teardownPromise: Promise<void> | null = null
  private teardownStarted = false
  private readyForCallbacks = false
  private readonly unsubscribeTransportState: () => void

  constructor(args: {
    device: BtDevice
    transport: DeviceTransport
    clock?: DeviceOperationClock
  }) {
    this.device = args.device
    this.transport = args.transport
    this.clock = args.clock ?? new RealDeviceOperationClock()
    this.unsubscribeTransportState = this.transport.onStateChange((state) =>
      this.handleTransportStateChange(state)
    )
  }

  get sessionGeneration(): number {
    return this.transport.sessionGeneration
  }

  protected get isReadyForCallbacks(): boolean {
    return this.readyForCallbacks
  }

  // --- lifecycle ------------------------------------------------------------

  private handleTransportStateChange(state: DeviceTransportState): void {
    // Setup-phase drops surface as connect() errors; only a ready session
    // reports an unexpected disconnect.
    if (state === 'disconnected' && this.readyForCallbacks && !this.teardownStarted) {
      void this.beginTeardown({ notifyUnexpectedDisconnect: true })
    }
  }

  /** Template method; exactly once per instance. */
  async connect(): Promise<void> {
    if (this.didStartLifecycle || this.teardownStarted) {
      throw DeviceConnectionError.alreadyConnected()
    }
    this.didStartLifecycle = true
    try {
      await this.transport.connect()
      this.ensureLifecycleIsActive()
      if (!this.ping()) {
        console.warn(`[device] initial ping failed for ${this.device.id}`)
      }
      await this.updateDeviceInfo()
      this.ensureLifecycleIsActive()
      await this.prepareDeviceAfterConnect()
      this.ensureLifecycleIsActive()
      this.readyForCallbacks = true
    } catch (error) {
      await this.beginTeardown({ notifyUnexpectedDisconnect: false })
      throw this.normalizeConnectionError(error)
    }
  }

  async disconnect(): Promise<void> {
    await this.beginTeardown({ notifyUnexpectedDisconnect: false })
  }

  async unpair(): Promise<void> {
    this.cachedFeatures = null
    this.lastPongAt = null
    await this.beginTeardown({ notifyUnexpectedDisconnect: false, runUnpair: true })
  }

  isConnected(): boolean {
    return this.transport.isConnected()
  }

  ping(): boolean {
    const ok = this.transport.ping()
    if (ok) this.lastPongAt = Date.now()
    return ok
  }

  protected ensureLifecycleIsActive(): void {
    if (this.teardownStarted) {
      throw DeviceConnectionError.operationFailed('Connection was cancelled')
    }
    if (this.transport.state !== 'connected') {
      throw DeviceConnectionError.connectionFailed('Device disconnected during connection setup')
    }
  }

  private normalizeConnectionError(error: unknown): Error {
    if (error instanceof DeviceConnectionError) return error
    const message = error instanceof Error ? error.message : String(error)
    return DeviceConnectionError.connectionFailed(message)
  }

  private beginTeardown(args: {
    notifyUnexpectedDisconnect: boolean
    runUnpair?: boolean
  }): Promise<void> {
    if (this.teardownStarted) return this.teardownPromise ?? Promise.resolve()
    // Claim BEFORE any hook runs: a stream callback fired from inside a hook can
    // call disconnect(), and the assignment below would not have happened yet.
    this.teardownStarted = true
    this.sessionAbort.abort()
    this.teardownPromise = (async () => {
      if (args.runUnpair === true) {
        try {
          await this.performDeviceUnpair()
        } catch (error) {
          console.warn(`[device] unpair hook failed: ${String(error)}`)
        }
      }
      try {
        await this.teardownDevice()
      } catch (error) {
        console.warn(`[device] teardown hook failed: ${String(error)}`)
      }
      await this.transport.dispose()
      this.unsubscribeTransportState()
      if (args.notifyUnexpectedDisconnect) {
        this.delegate?.didDisconnectUnexpectedly(this.device)
      }
    })()
    return this.teardownPromise
  }

  /** Interruptible settle: resolves early (without throwing) at teardown;
   *  callers re-check lifecycle right after. */
  protected async settle(ms: number): Promise<void> {
    await this.clock.sleep(ms, this.sessionAbort.signal)
  }

  // --- overridable hooks (each at most once per session) ---------------------

  protected async updateDeviceInfo(): Promise<void> {
    const reads: Array<[string, (value: string) => void]> = [
      [DEVICE_INFO_UUIDS.modelNumber, (v) => (this.device.modelNumber = v)],
      [DEVICE_INFO_UUIDS.firmwareRevision, (v) => (this.device.firmwareRevision = v)],
      [DEVICE_INFO_UUIDS.hardwareRevision, (v) => (this.device.hardwareRevision = v)],
      [DEVICE_INFO_UUIDS.manufacturerName, (v) => (this.device.manufacturerName = v)]
    ]
    for (const [uuid, assign] of reads) {
      try {
        const data = await this.transport.readCharacteristic(DEVICE_INFO_UUIDS.service, uuid)
        assign(new TextDecoder().decode(data))
      } catch {
        // First failing read aborts the rest; device info stays defaulted.
        return
      }
    }
  }

  /** Post-connect setup (settles, subscriptions, handshakes). */
  protected async prepareDeviceAfterConnect(): Promise<void> {
    // No device-specific setup by default.
  }

  /** Releases device-side session state before the transport is disposed. */
  protected async teardownDevice(): Promise<void> {
    // No device-specific teardown by default.
  }

  /** Sends the family's unpair command, when it has one. */
  protected async performDeviceUnpair(): Promise<void> {
    // Most families have no unpair command.
  }

  // --- battery (standard GATT) ----------------------------------------------

  async getBatteryLevel(): Promise<number> {
    try {
      const data = await this.transport.readCharacteristic(
        BATTERY_UUIDS.service,
        BATTERY_UUIDS.level
      )
      return data.length > 0 ? data[0] : -1
    } catch {
      return -1
    }
  }

  getBatteryLevelStream(subscriber: StreamSubscriber<number>): StreamSubscription {
    return this.transport.subscribeCharacteristic(BATTERY_UUIDS.service, BATTERY_UUIDS.level, {
      onData: (data) => {
        if (data.length > 0) subscriber.onValue(data[0])
      },
      onFinish: (error) => subscriber.onFinish(error)
    })
  }

  // --- audio (Omi-shaped defaults) -------------------------------------------

  async getAudioCodec(): Promise<BleAudioCodec> {
    try {
      const data = await this.transport.readCharacteristic(
        OMI_UUIDS.mainService,
        OMI_UUIDS.audioCodec
      )
      if (data.length === 0) return 'pcm8'
      return codecFromCharacteristicByte(data[0])
    } catch {
      return 'pcm8'
    }
  }

  getAudioStream(subscriber: StreamSubscriber<Uint8Array>): StreamSubscription {
    return this.transport.subscribeCharacteristic(
      OMI_UUIDS.mainService,
      OMI_UUIDS.audioDataStream,
      {
        onData: (data) => subscriber.onValue(data),
        onFinish: (error) => subscriber.onFinish(error)
      }
    )
  }

  canStreamAudio(): boolean {
    return true
  }

  // --- button ----------------------------------------------------------------

  async getButtonState(): Promise<Uint8Array> {
    try {
      return await this.transport.readCharacteristic(BUTTON_UUIDS.service, BUTTON_UUIDS.trigger)
    } catch {
      return new Uint8Array(0)
    }
  }

  getButtonStream(subscriber: StreamSubscriber<Uint8Array>): StreamSubscription {
    return this.transport.subscribeCharacteristic(BUTTON_UUIDS.service, BUTTON_UUIDS.trigger, {
      onData: (data) => subscriber.onValue(data),
      onFinish: (error) => subscriber.onFinish(error)
    })
  }

  // --- storage ---------------------------------------------------------------

  async getStorageList(): Promise<number[]> {
    try {
      const data = await this.transport.readCharacteristic(
        STORAGE_UUIDS.service,
        STORAGE_UUIDS.readControl
      )
      const lengths: number[] = []
      for (let i = 0; i + 4 <= data.length; i += 4) {
        lengths.push(data[i] | (data[i + 1] << 8) | (data[i + 2] << 16) | (data[i + 3] << 24))
      }
      return lengths
    } catch {
      return []
    }
  }

  async writeToStorage(fileNum: number, command: number, offset: number): Promise<void> {
    // Command and file number one byte each; offset big-endian 4 bytes.
    const payload = Uint8Array.from([
      command & 0xff,
      fileNum & 0xff,
      (offset >>> 24) & 0xff,
      (offset >>> 16) & 0xff,
      (offset >>> 8) & 0xff,
      offset & 0xff
    ])
    await this.transport.writeCharacteristic({
      serviceUuid: STORAGE_UUIDS.service,
      characteristicUuid: STORAGE_UUIDS.dataStream,
      data: payload,
      withResponse: true
    })
  }

  getStorageStream(subscriber: StreamSubscriber<Uint8Array>): StreamSubscription {
    return this.transport.subscribeCharacteristic(STORAGE_UUIDS.service, STORAGE_UUIDS.dataStream, {
      onData: (data) => subscriber.onValue(data),
      onFinish: (error) => subscriber.onFinish(error)
    })
  }

  // --- camera (unsupported by default) ---------------------------------------

  async hasPhotoStreaming(): Promise<boolean> {
    return false
  }

  async startPhotoCapture(): Promise<boolean> {
    return false
  }

  async stopPhotoCapture(): Promise<boolean> {
    return false
  }

  getImageStream(subscriber: StreamSubscriber<OrientedImage>): StreamSubscription {
    return finishedStream(subscriber)
  }

  // --- accelerometer ----------------------------------------------------------

  getAccelerometerStream(subscriber: StreamSubscriber<AccelerometerData>): StreamSubscription {
    return this.transport.subscribeCharacteristic(
      ACCELEROMETER_UUIDS.service,
      ACCELEROMETER_UUIDS.dataStream,
      {
        onData: (data) => {
          let sample: AccelerometerData
          if (data.length >= 12) {
            sample = makeAccelerometerData(
              decodeInt16LE(data[0], data[1]),
              decodeInt16LE(data[2], data[3]),
              decodeInt16LE(data[4], data[5]),
              decodeInt16LE(data[6], data[7]),
              decodeInt16LE(data[8], data[9]),
              decodeInt16LE(data[10], data[11])
            )
          } else if (data.length >= 1) {
            sample = makeAccelerometerData(data[0], 0, 0, 0, 0, 0)
          } else {
            return
          }
          subscriber.onValue(sample)
          if (sample.indicatesFall) {
            this.delegate?.didDetectFall(sample)
          }
        },
        onFinish: (error) => subscriber.onFinish(error)
      }
    )
  }

  // --- haptic / features ------------------------------------------------------

  async playHaptic(level: number): Promise<boolean> {
    try {
      await this.transport.writeCharacteristic({
        serviceUuid: SPEAKER_UUIDS.service,
        characteristicUuid: SPEAKER_UUIDS.dataStream,
        data: Uint8Array.from([level & 0xff]),
        withResponse: true
      })
      return true
    } catch {
      return false
    }
  }

  async getFeatures(): Promise<OmiFeatureName[]> {
    if (this.cachedFeatures !== null) return this.cachedFeatures
    try {
      const data = await this.transport.readCharacteristic(
        OMI_UUIDS.featuresService,
        OMI_UUIDS.featuresCharacteristic
      )
      if (data.length < 4) return []
      const mask = (data[0] | (data[1] << 8) | (data[2] << 16) | (data[3] << 24)) >>> 0
      const features = (Object.keys(OMI_FEATURE_BITS) as OmiFeatureName[]).filter(
        (name) => (mask & OMI_FEATURE_BITS[name]) !== 0
      )
      this.cachedFeatures = features
      return features
    } catch {
      // Errors are not cached; the next call retries.
      return []
    }
  }

  // --- settings (unsupported by default) --------------------------------------

  async setLedDimRatio(_ratio: number): Promise<boolean> {
    return false
  }

  async getLedDimRatio(): Promise<number | null> {
    return null
  }

  async setMicGain(_gain: number): Promise<boolean> {
    return false
  }

  async getMicGain(): Promise<number | null> {
    return null
  }

  // --- wifi (unsupported by default) ------------------------------------------

  async isWifiSyncSupported(): Promise<boolean> {
    return false
  }

  async setupWifiSync(ssid: string, password: string): Promise<WifiSyncResult> {
    const validation = validateWifiCredentials(ssid, password)
    if (validation !== 'success') return { code: validation }
    return { code: 'wifiHardwareNotAvailable' }
  }

  async startWifiSync(): Promise<boolean> {
    return false
  }

  async stopWifiSync(): Promise<boolean> {
    return false
  }

  getWifiSyncStatusStream(subscriber: StreamSubscriber<number>): StreamSubscription {
    return finishedStream(subscriber)
  }

  // --- shared helpers for subclasses ------------------------------------------

  protected mapTransportError(error: unknown): Error {
    if (error instanceof DeviceConnectionError) return error
    if (error instanceof DeviceTransportError) {
      return DeviceConnectionError.operationFailed(error.message)
    }
    return DeviceConnectionError.operationFailed(
      error instanceof Error ? error.message : String(error)
    )
  }
}
