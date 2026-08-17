/**
 * BLE transport — Windows port of macOS Transports/BleTransport.swift over
 * WebBluetooth. One instance per connection attempt: after any failure or
 * disconnect the transport is invalidated and the session coordinator builds
 * a fresh one for the next generation.
 *
 * Divergence from the mac source (registered in ARCHITECTURE.md): CoreBluetooth
 * delivers reads and notifications through one callback and demuxes via the
 * read gate; WebBluetooth correlates reads by their own promise, so here the
 * gate instead suppresses the read's characteristicvaluechanged echo without
 * claiming, and a late post-timeout resolution is dropped by the poisoned key
 * exactly as on mac.
 */

import {
  DeviceOperationBroker,
  DeviceOperationBrokerError,
  RealDeviceOperationClock,
  UncorrelatedOperationGate,
  type DeviceOperationClock
} from '../session/deviceOperationBroker'
import {
  BluetoothConnectionLeaseRegistry,
  type BluetoothConnectionLease
} from '../session/bluetoothConnectionLease'
import {
  DeviceTransportError,
  type CharacteristicStreamSubscriber,
  type CharacteristicStreamSubscription,
  type DeviceTransport,
  type DeviceTransportState
} from './deviceTransport'
import type { BlePhysicalDriver } from './blePhysicalDriver'

const CONNECT_STEP_TIMEOUT_MS = 10_000
const READ_WRITE_TIMEOUT_MS = 5_000

const CONNECT_OP_KEY = 'transport:connect'
const DISCOVER_SERVICES_OP_KEY = 'transport:discover-services'
const DISCOVER_CHARACTERISTICS_OP_KEY = 'transport:discover-characteristics'

const streamKey = (serviceUuid: string, characteristicUuid: string): string =>
  `${serviceUuid.toLowerCase()}:${characteristicUuid.toLowerCase()}`

const toError = (value: unknown): Error =>
  value instanceof Error ? value : new Error(String(value))

interface DiscoveredCharacteristicRef {
  serviceUuid: string
  characteristicUuid: string
}

interface Broadcaster {
  subscribers: Map<number, CharacteristicStreamSubscriber>
}

export class BleTransport implements DeviceTransport {
  readonly sessionGeneration: number

  private readonly driver: BlePhysicalDriver
  private readonly leases: BluetoothConnectionLeaseRegistry
  private readonly broker: DeviceOperationBroker
  private readonly readGate = new UncorrelatedOperationGate()
  private readonly writeGate = new UncorrelatedOperationGate()

  private transportState: DeviceTransportState = 'disconnected'
  private stateListeners = new Set<(state: DeviceTransportState) => void>()
  private disposed = false
  private invalidated = false
  private physicalDisconnectRequested = false
  private connectAttemptSettled = false
  private lease: BluetoothConnectionLease | null = null
  private discovered = new Map<string, Map<string, DiscoveredCharacteristicRef>>()
  private broadcasters = new Map<string, Broadcaster>()
  private nextSubscriberId = 1
  private readonly unsubscribeDisconnected: () => void

  constructor(args: {
    driver: BlePhysicalDriver
    sessionGeneration: number
    leases: BluetoothConnectionLeaseRegistry
    clock?: DeviceOperationClock
  }) {
    this.driver = args.driver
    this.sessionGeneration = args.sessionGeneration
    this.leases = args.leases
    this.broker = new DeviceOperationBroker(args.clock ?? new RealDeviceOperationClock())
    this.unsubscribeDisconnected = this.driver.onDisconnected(() =>
      this.handleUnexpectedDisconnect()
    )
  }

  get deviceId(): string {
    return this.driver.id
  }

  get state(): DeviceTransportState {
    return this.transportState
  }

  onStateChange(listener: (state: DeviceTransportState) => void): () => void {
    this.stateListeners.add(listener)
    return () => this.stateListeners.delete(listener)
  }

  async connect(): Promise<void> {
    if (this.disposed) throw DeviceTransportError.disposed()
    if (this.invalidated) {
      throw DeviceTransportError.connectionFailed('Transport session must be recreated')
    }
    if (this.transportState === 'connected') return

    try {
      this.lease = this.leases.begin(this.driver.id, this.sessionGeneration)
    } catch (error) {
      throw DeviceTransportError.connectionFailed(toError(error).message)
    }
    this.setState('connecting')

    try {
      await this.broker.perform<void>({
        key: CONNECT_OP_KEY,
        timeoutMs: CONNECT_STEP_TIMEOUT_MS,
        start: () => {
          this.driver.connect().then(
            () => {
              this.connectAttemptSettled = true
              this.broker.succeed(CONNECT_OP_KEY, undefined)
              // An attempt that resolved after being abandoned must be torn
              // back down; the fence is released once that is issued.
              if (this.invalidated) {
                this.requestPhysicalDisconnect()
                this.releaseLease()
              }
            },
            (error) => {
              this.connectAttemptSettled = true
              this.broker.fail(CONNECT_OP_KEY, toError(error))
              this.releaseLease()
            }
          )
        }
      })
      if (this.lease !== null) this.leases.markConnected(this.lease)
      this.ensureConnectionIsValid()

      const services = await this.broker.perform<Array<{ uuid: string }>>({
        key: DISCOVER_SERVICES_OP_KEY,
        timeoutMs: CONNECT_STEP_TIMEOUT_MS,
        start: () => {
          this.driver.discoverServices().then(
            (result) => this.broker.succeed(DISCOVER_SERVICES_OP_KEY, result),
            (error) => this.broker.fail(DISCOVER_SERVICES_OP_KEY, toError(error))
          )
        }
      })
      this.ensureConnectionIsValid()

      if (services.length > 0) {
        await this.broker.perform<void>({
          key: DISCOVER_CHARACTERISTICS_OP_KEY,
          timeoutMs: CONNECT_STEP_TIMEOUT_MS,
          start: () => {
            Promise.all(
              services.map(async (service) => {
                const characteristics = await this.driver.discoverCharacteristics(service.uuid)
                this.registerDiscovered(service.uuid, characteristics)
              })
            ).then(
              () => this.broker.succeed(DISCOVER_CHARACTERISTICS_OP_KEY, undefined),
              (error) => this.broker.fail(DISCOVER_CHARACTERISTICS_OP_KEY, toError(error))
            )
          }
        })
        this.ensureConnectionIsValid()
      }

      this.setState('connected')
    } catch (error) {
      this.invalidated = true
      if (this.lease !== null) this.leases.requestCancellation(this.lease)
      this.broker.cancelAll('cancelled')
      this.requestPhysicalDisconnect()
      this.setState('disconnected')
      if (this.connectAttemptSettled) this.releaseLease()
      if (error instanceof DeviceTransportError && error.kind === 'connectionFailed') {
        throw error
      }
      throw DeviceTransportError.connectionFailed(toError(error).message)
    }
  }

  async disconnect(): Promise<void> {
    this.drainSession()
  }

  async dispose(): Promise<void> {
    if (this.disposed) return
    this.disposed = true
    this.drainSession()
    this.unsubscribeDisconnected()
    this.readGate.reset()
    this.writeGate.reset()
  }

  isConnected(): boolean {
    return this.driver.isConnected() && this.transportState === 'connected'
  }

  ping(): boolean {
    return this.driver.isConnected()
  }

  subscribeCharacteristic(
    serviceUuid: string,
    characteristicUuid: string,
    subscriber: CharacteristicStreamSubscriber
  ): CharacteristicStreamSubscription {
    if (this.disposed) {
      subscriber.onFinish(DeviceTransportError.disposed())
      return { cancel: () => undefined }
    }
    if (this.transportState !== 'connected') {
      subscriber.onFinish(DeviceTransportError.notConnected())
      return { cancel: () => undefined }
    }
    const found = this.findCharacteristic(serviceUuid, characteristicUuid)
    if (found === null) {
      subscriber.onFinish(DeviceTransportError.characteristicNotFound(characteristicUuid))
      return { cancel: () => undefined }
    }

    const key = streamKey(serviceUuid, characteristicUuid)
    let broadcaster = this.broadcasters.get(key)
    const isNew = broadcaster === undefined
    if (broadcaster === undefined) {
      broadcaster = { subscribers: new Map() }
      this.broadcasters.set(key, broadcaster)
    }
    const id = this.nextSubscriberId++
    broadcaster.subscribers.set(id, subscriber)

    if (isNew) {
      // Notification enablement failures are log-only on mac
      // (didUpdateNotificationStateFor); the subscriber simply sees no data.
      this.driver
        .startNotifications(found.serviceUuid, found.characteristicUuid, (data) =>
          this.handleNotification(key, data)
        )
        .catch((error) => {
          console.warn(
            `[device] startNotifications failed for ${key}: ${toError(error).message}`
          )
        })
    }

    return {
      cancel: () => {
        broadcaster.subscribers.delete(id)
        // The broadcaster stays registered: notifications keep arriving and
        // are dropped, matching mac (notify is never turned back off).
      }
    }
  }

  async readCharacteristic(serviceUuid: string, characteristicUuid: string): Promise<Uint8Array> {
    const found = this.guardCharacteristicOperation(serviceUuid, characteristicUuid)
    const key = streamKey(serviceUuid, characteristicUuid)
    const handle = this.readGate.register(key)
    if (handle === null) {
      throw DeviceTransportError.readFailed(
        'A previous read has an uncorrelated callback; reconnect the device'
      )
    }
    try {
      return await this.broker.perform<Uint8Array>({
        key,
        timeoutMs: READ_WRITE_TIMEOUT_MS,
        onTerminal: (termination) => this.readGate.terminal(handle, termination),
        start: () => {
          this.driver.readValue(found.serviceUuid, found.characteristicUuid).then(
            (value) => {
              if (this.readGate.takeHandleForCallback(key) === null) return
              this.broker.succeed(key, value)
            },
            (error) => {
              if (this.readGate.takeHandleForCallback(key) === null) return
              this.broker.fail(key, toError(error))
            }
          )
        }
      })
    } catch (error) {
      if (error instanceof DeviceTransportError) throw error
      throw DeviceTransportError.readFailed(toError(error).message)
    }
  }

  async writeCharacteristic(args: {
    serviceUuid: string
    characteristicUuid: string
    data: Uint8Array
    withResponse?: boolean
  }): Promise<void> {
    const withResponse = args.withResponse ?? true
    const found = this.guardCharacteristicOperation(args.serviceUuid, args.characteristicUuid)

    if (!withResponse) {
      void this.driver
        .writeValue(found.serviceUuid, found.characteristicUuid, args.data, false)
        .catch(() => undefined)
      return
    }

    const key = streamKey(args.serviceUuid, args.characteristicUuid)
    const handle = this.writeGate.register(key)
    if (handle === null) {
      throw DeviceTransportError.writeFailed(
        'A previous write has an uncorrelated callback; reconnect the device'
      )
    }
    try {
      await this.broker.perform<void>({
        key,
        timeoutMs: READ_WRITE_TIMEOUT_MS,
        onTerminal: (termination) => this.writeGate.terminal(handle, termination),
        start: () => {
          this.driver.writeValue(found.serviceUuid, found.characteristicUuid, args.data, true).then(
            () => {
              if (this.writeGate.takeHandleForCallback(key) === null) return
              this.broker.succeed(key, undefined)
            },
            (error) => {
              if (this.writeGate.takeHandleForCallback(key) === null) return
              this.broker.fail(key, toError(error))
            }
          )
        }
      })
    } catch (error) {
      if (error instanceof DeviceTransportError) throw error
      throw DeviceTransportError.writeFailed(toError(error).message)
    }
  }

  // --- internals ------------------------------------------------------------

  private setState(state: DeviceTransportState): void {
    if (this.transportState === state) return
    this.transportState = state
    for (const listener of Array.from(this.stateListeners)) {
      listener(state)
    }
  }

  private ensureConnectionIsValid(): void {
    if (this.disposed || this.invalidated) {
      throw DeviceTransportError.connectionFailed('Connection was superseded')
    }
  }

  private registerDiscovered(
    serviceUuid: string,
    characteristics: Array<{ uuid: string }>
  ): void {
    const byChar = new Map<string, DiscoveredCharacteristicRef>()
    for (const characteristic of characteristics) {
      byChar.set(characteristic.uuid.toLowerCase(), {
        serviceUuid,
        characteristicUuid: characteristic.uuid
      })
    }
    this.discovered.set(serviceUuid.toLowerCase(), byChar)
  }

  private findCharacteristic(
    serviceUuid: string,
    characteristicUuid: string
  ): DiscoveredCharacteristicRef | null {
    return (
      this.discovered.get(serviceUuid.toLowerCase())?.get(characteristicUuid.toLowerCase()) ?? null
    )
  }

  private guardCharacteristicOperation(
    serviceUuid: string,
    characteristicUuid: string
  ): DiscoveredCharacteristicRef {
    if (this.disposed) throw DeviceTransportError.disposed()
    if (this.transportState !== 'connected') throw DeviceTransportError.notConnected()
    const found = this.findCharacteristic(serviceUuid, characteristicUuid)
    if (found === null) throw DeviceTransportError.characteristicNotFound(characteristicUuid)
    return found
  }

  private handleNotification(key: string, data: Uint8Array): void {
    // A pending read's value echoes through characteristicvaluechanged; the
    // read is delivered by its own promise, so the echo is not a notification.
    if (this.readGate.hasLiveAttempt(key)) return
    const broadcaster = this.broadcasters.get(key)
    if (broadcaster === undefined) return
    for (const subscriber of Array.from(broadcaster.subscribers.values())) {
      subscriber.onData(data)
    }
  }

  private finishAllStreams(error: Error | null): void {
    const broadcasters = Array.from(this.broadcasters.values())
    this.broadcasters.clear()
    for (const broadcaster of broadcasters) {
      const subscribers = Array.from(broadcaster.subscribers.values())
      broadcaster.subscribers.clear()
      for (const subscriber of subscribers) {
        subscriber.onFinish(error)
      }
    }
  }

  private requestPhysicalDisconnect(): void {
    if (this.physicalDisconnectRequested) return
    this.physicalDisconnectRequested = true
    this.driver.disconnect()
  }

  private releaseLease(): void {
    if (this.lease === null) return
    this.leases.end(this.lease)
    this.lease = null
  }

  /** Clean teardown: streams finish WITHOUT error. */
  private drainSession(): void {
    this.invalidated = true
    if (this.transportState !== 'disconnected') {
      this.setState('disconnecting')
    }
    this.broker.cancelAll('cancelled')
    this.finishAllStreams(null)
    this.requestPhysicalDisconnect()
    this.setState('disconnected')
    if (this.connectAttemptSettled) this.releaseLease()
  }

  /** Physical link dropped mid-session: subscribers observe it as an error. */
  private handleUnexpectedDisconnect(): void {
    const alreadyDrained = this.invalidated && this.transportState === 'disconnected'
    this.invalidated = true
    this.connectAttemptSettled = true
    if (!alreadyDrained) {
      this.broker.cancelAll('disconnected')
      this.finishAllStreams(new DeviceOperationBrokerError('disconnected'))
      this.setState('disconnected')
    }
    this.releaseLease()
  }
}
