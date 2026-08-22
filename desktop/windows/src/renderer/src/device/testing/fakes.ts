/**
 * Shared test doubles for the device stack (imported by tests only): a
 * virtual-time clock and an in-memory DeviceTransport.
 */

import type { DeviceOperationClock } from '../session/deviceOperationBroker'
import {
  DeviceTransportError,
  type CharacteristicStreamSubscriber,
  type CharacteristicStreamSubscription,
  type DeviceTransport,
  type DeviceTransportState
} from '../transport/deviceTransport'

export class ManualClock implements DeviceOperationClock {
  private now = 0
  private waiters: Array<{ deadline: number; resolve: (r: 'elapsed' | 'aborted') => void }> = []

  sleep(ms: number, signal: AbortSignal): Promise<'elapsed' | 'aborted'> {
    return new Promise((resolve) => {
      if (signal.aborted) {
        resolve('aborted')
        return
      }
      const entry = { deadline: this.now + ms, resolve }
      this.waiters.push(entry)
      signal.addEventListener(
        'abort',
        () => {
          const index = this.waiters.indexOf(entry)
          if (index >= 0) this.waiters.splice(index, 1)
          resolve('aborted')
        },
        { once: true }
      )
    })
  }

  /** Advances virtual time, firing only sleeps whose deadline has passed. */
  advance(ms: number): void {
    this.now += ms
    const due = this.waiters.filter((w) => w.deadline <= this.now)
    this.waiters = this.waiters.filter((w) => w.deadline > this.now)
    for (const waiter of due) waiter.resolve('elapsed')
  }

  /** Fires every pending sleep regardless of deadline. */
  fireAll(): void {
    for (const waiter of this.waiters.splice(0)) waiter.resolve('elapsed')
  }
}

export const tick = (): Promise<void> => new Promise((resolve) => setTimeout(resolve, 0))

export const characteristicKey = (serviceUuid: string, characteristicUuid: string): string =>
  `${serviceUuid.toLowerCase()}:${characteristicUuid.toLowerCase()}`

export class FakeTransport implements DeviceTransport {
  deviceId = 'fake-device'
  sessionGeneration = 1
  state: DeviceTransportState = 'disconnected'
  connectError: Error | null = null
  disposed = false
  /** Static read results by characteristic key; Error values throw. */
  reads = new Map<string, Uint8Array | Error>()
  readLog: string[] = []
  writes: Array<{ key: string; data: Uint8Array; withResponse: boolean }> = []
  writeErrors = new Map<string, Error>()

  private listeners = new Set<(state: DeviceTransportState) => void>()
  private broadcasters = new Map<string, Map<number, CharacteristicStreamSubscriber>>()
  private nextSubscriberId = 1

  onStateChange(listener: (state: DeviceTransportState) => void): () => void {
    this.listeners.add(listener)
    return () => this.listeners.delete(listener)
  }

  setState(state: DeviceTransportState): void {
    if (this.state === state) return
    this.state = state
    for (const listener of Array.from(this.listeners)) listener(state)
  }

  async connect(): Promise<void> {
    if (this.connectError !== null) throw this.connectError
    this.setState('connecting')
    this.setState('connected')
  }

  async disconnect(): Promise<void> {
    this.finishAllStreams(null)
    this.setState('disconnected')
  }

  async dispose(): Promise<void> {
    this.disposed = true
    this.finishAllStreams(null)
    this.setState('disconnected')
  }

  isConnected(): boolean {
    return this.state === 'connected'
  }

  ping(): boolean {
    return this.state === 'connected'
  }

  subscribeCharacteristic(
    serviceUuid: string,
    characteristicUuid: string,
    subscriber: CharacteristicStreamSubscriber
  ): CharacteristicStreamSubscription {
    if (this.state !== 'connected') {
      subscriber.onFinish(DeviceTransportError.notConnected())
      return { cancel: () => undefined }
    }
    const key = characteristicKey(serviceUuid, characteristicUuid)
    let subscribers = this.broadcasters.get(key)
    if (subscribers === undefined) {
      subscribers = new Map()
      this.broadcasters.set(key, subscribers)
    }
    const id = this.nextSubscriberId++
    subscribers.set(id, subscriber)
    return { cancel: () => subscribers.delete(id) }
  }

  async readCharacteristic(serviceUuid: string, characteristicUuid: string): Promise<Uint8Array> {
    const key = characteristicKey(serviceUuid, characteristicUuid)
    this.readLog.push(key)
    const result = this.reads.get(key)
    if (result === undefined) throw DeviceTransportError.characteristicNotFound(characteristicUuid)
    if (result instanceof Error) throw result
    return result
  }

  async writeCharacteristic(args: {
    serviceUuid: string
    characteristicUuid: string
    data: Uint8Array
    withResponse?: boolean
  }): Promise<void> {
    const key = characteristicKey(args.serviceUuid, args.characteristicUuid)
    this.writes.push({ key, data: args.data.slice(), withResponse: args.withResponse ?? true })
    const error = this.writeErrors.get(key)
    if (error !== undefined) throw error
  }

  // --- test helpers ----------------------------------------------------------

  notify(serviceUuid: string, characteristicUuid: string, bytes: number[] | Uint8Array): void {
    const key = characteristicKey(serviceUuid, characteristicUuid)
    const data = bytes instanceof Uint8Array ? bytes : Uint8Array.from(bytes)
    const subscribers = this.broadcasters.get(key)
    if (subscribers === undefined) return
    for (const subscriber of Array.from(subscribers.values())) {
      subscriber.onData(data)
    }
  }

  subscriberCount(serviceUuid: string, characteristicUuid: string): number {
    return this.broadcasters.get(characteristicKey(serviceUuid, characteristicUuid))?.size ?? 0
  }

  writesTo(serviceUuid: string, characteristicUuid: string): Uint8Array[] {
    const key = characteristicKey(serviceUuid, characteristicUuid)
    return this.writes.filter((w) => w.key === key).map((w) => w.data)
  }

  fireUnexpectedDisconnect(): void {
    this.finishAllStreams(new Error('link lost'))
    this.setState('disconnected')
  }

  private finishAllStreams(error: Error | null): void {
    const broadcasters = Array.from(this.broadcasters.values())
    this.broadcasters.clear()
    for (const subscribers of broadcasters) {
      for (const subscriber of Array.from(subscribers.values())) {
        subscriber.onFinish(error)
      }
    }
  }
}
