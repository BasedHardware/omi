import { describe, it, expect } from 'vitest'
import { BleTransport } from './bleTransport'
import { DeviceTransportError, type CharacteristicStreamSubscriber } from './deviceTransport'
import type { BlePhysicalDriver } from './blePhysicalDriver'
import { BluetoothConnectionLeaseRegistry } from '../session/bluetoothConnectionLease'
import {
  DeviceOperationBrokerError,
  type DeviceOperationClock
} from '../session/deviceOperationBroker'

const OMI_SERVICE = '19B10000-E8F2-537E-4F6C-D104768A1214'
const OMI_AUDIO = '19b10001-e8f2-537e-4f6c-d104768a1214'
const BATTERY_SERVICE = '0000180f-0000-1000-8000-00805f9b34fb'
const BATTERY_LEVEL = '00002a19-0000-1000-8000-00805f9b34fb'

class ManualClock implements DeviceOperationClock {
  private pending: Array<(r: 'elapsed' | 'aborted') => void> = []

  sleep(_ms: number, signal: AbortSignal): Promise<'elapsed' | 'aborted'> {
    return new Promise((resolve) => {
      if (signal.aborted) {
        resolve('aborted')
        return
      }
      this.pending.push(resolve)
      signal.addEventListener(
        'abort',
        () => {
          const index = this.pending.indexOf(resolve)
          if (index >= 0) this.pending.splice(index, 1)
          resolve('aborted')
        },
        { once: true }
      )
    })
  }

  fireAll(): void {
    for (const resolve of this.pending.splice(0)) resolve('elapsed')
  }
}

interface Pending<T> {
  key: string
  resolve: (value: T) => void
  reject: (error: Error) => void
}

class FakeDriver implements BlePhysicalDriver {
  id = 'fake-device-1'
  name = 'omi test'
  connected = false
  connectCalls = 0
  disconnectCalls = 0
  discoverServicesError: Error | null = null
  services: Array<{ uuid: string; characteristics: string[] }> = [
    { uuid: OMI_SERVICE, characteristics: [OMI_AUDIO, '19b10002-e8f2-537e-4f6c-d104768a1214'] },
    { uuid: BATTERY_SERVICE, characteristics: [BATTERY_LEVEL] }
  ]
  pendingReads: Array<Pending<Uint8Array>> = []
  writes: Array<{ key: string; data: Uint8Array; withResponse: boolean }> = []
  pendingWrites: Array<Pending<void>> = []
  notifyStarts: string[] = []
  notifyHandlers = new Map<string, (data: Uint8Array) => void>()

  private connectResolve: (() => void) | null = null
  private connectReject: ((e: Error) => void) | null = null
  private disconnectListeners = new Set<() => void>()

  isConnected(): boolean {
    return this.connected
  }

  connect(): Promise<void> {
    this.connectCalls += 1
    return new Promise((resolve, reject) => {
      this.connectResolve = () => {
        this.connected = true
        resolve()
      }
      this.connectReject = reject
    })
  }

  resolveConnect(): void {
    this.connectResolve?.()
  }

  rejectConnect(error: Error): void {
    this.connectReject?.(error)
  }

  disconnect(): void {
    this.disconnectCalls += 1
    this.connected = false
  }

  async discoverServices(): Promise<Array<{ uuid: string }>> {
    if (this.discoverServicesError !== null) throw this.discoverServicesError
    return this.services.map((s) => ({ uuid: s.uuid }))
  }

  async discoverCharacteristics(serviceUuid: string): Promise<Array<{ uuid: string }>> {
    const service = this.services.find((s) => s.uuid.toLowerCase() === serviceUuid.toLowerCase())
    if (service === undefined) throw new Error(`unknown service ${serviceUuid}`)
    return service.characteristics.map((uuid) => ({ uuid }))
  }

  readValue(serviceUuid: string, characteristicUuid: string): Promise<Uint8Array> {
    return new Promise((resolve, reject) => {
      this.pendingReads.push({
        key: `${serviceUuid.toLowerCase()}:${characteristicUuid.toLowerCase()}`,
        resolve,
        reject
      })
    })
  }

  resolveNextRead(bytes: number[]): void {
    this.pendingReads.shift()?.resolve(Uint8Array.from(bytes))
  }

  writeValue(
    serviceUuid: string,
    characteristicUuid: string,
    data: Uint8Array,
    withResponse: boolean
  ): Promise<void> {
    const key = `${serviceUuid.toLowerCase()}:${characteristicUuid.toLowerCase()}`
    this.writes.push({ key, data, withResponse })
    if (!withResponse) return Promise.resolve()
    return new Promise((resolve, reject) => {
      this.pendingWrites.push({ key, resolve, reject })
    })
  }

  resolveNextWrite(): void {
    this.pendingWrites.shift()?.resolve(undefined)
  }

  async startNotifications(
    serviceUuid: string,
    characteristicUuid: string,
    onValue: (data: Uint8Array) => void
  ): Promise<void> {
    const key = `${serviceUuid.toLowerCase()}:${characteristicUuid.toLowerCase()}`
    this.notifyStarts.push(key)
    this.notifyHandlers.set(key, onValue)
  }

  notify(serviceUuid: string, characteristicUuid: string, bytes: number[]): void {
    const key = `${serviceUuid.toLowerCase()}:${characteristicUuid.toLowerCase()}`
    this.notifyHandlers.get(key)?.(Uint8Array.from(bytes))
  }

  onDisconnected(listener: () => void): () => void {
    this.disconnectListeners.add(listener)
    return () => this.disconnectListeners.delete(listener)
  }

  fireDisconnected(): void {
    this.connected = false
    for (const listener of Array.from(this.disconnectListeners)) listener()
  }
}

interface Recorder extends CharacteristicStreamSubscriber {
  frames: Uint8Array[]
  finished: { error: Error | null } | null
}

const recorder = (): Recorder => {
  const rec: Recorder = {
    frames: [],
    finished: null,
    onData: (data) => rec.frames.push(data),
    onFinish: (error) => {
      rec.finished = { error }
    }
  }
  return rec
}

const setup = async (): Promise<{
  driver: FakeDriver
  clock: ManualClock
  leases: BluetoothConnectionLeaseRegistry
  transport: BleTransport
}> => {
  const driver = new FakeDriver()
  const clock = new ManualClock()
  const leases = new BluetoothConnectionLeaseRegistry()
  const transport = new BleTransport({ driver, sessionGeneration: 1, leases, clock })
  const connecting = transport.connect()
  driver.resolveConnect()
  await connecting
  return { driver, clock, leases, transport }
}

describe('BleTransport connect', () => {
  it('walks connect, service discovery, characteristic discovery to connected', async () => {
    const { driver, transport, leases } = await setup()
    expect(transport.state).toBe('connected')
    expect(transport.isConnected()).toBe(true)
    expect(transport.ping()).toBe(true)
    expect(driver.connectCalls).toBe(1)
    expect(leases.activeLease(driver.id)).not.toBeNull()
  })

  it('connect timeout invalidates the single-use transport and keeps the lease draining', async () => {
    const driver = new FakeDriver()
    const clock = new ManualClock()
    const leases = new BluetoothConnectionLeaseRegistry()
    const transport = new BleTransport({ driver, sessionGeneration: 1, leases, clock })
    const connecting = transport.connect()
    clock.fireAll()
    await expect(connecting).rejects.toMatchObject({
      kind: 'connectionFailed',
      message: 'Connection failed: Operation timed out'
    })
    expect(transport.state).toBe('disconnected')
    expect(driver.disconnectCalls).toBe(1)

    // Single-use: the same transport can never connect again.
    await expect(transport.connect()).rejects.toMatchObject({
      message: 'Connection failed: Transport session must be recreated'
    })

    // The attempt is still draining, so a new session is fenced out.
    const second = new BleTransport({
      driver: new FakeDriver(),
      sessionGeneration: 2,
      leases,
      clock
    })
    await expect(second.connect()).rejects.toMatchObject({
      message: 'Connection failed: A previous Bluetooth connection attempt is still draining'
    })

    // The platform reporting the attempt dead releases the fence.
    driver.rejectConnect(new Error('gone'))
    await Promise.resolve()
    expect(leases.activeLease(driver.id)).toBeNull()
  })

  it('a discovery failure tears the session down and wraps the reason', async () => {
    const driver = new FakeDriver()
    driver.discoverServicesError = new Error('discovery blew up')
    const leases = new BluetoothConnectionLeaseRegistry()
    const transport = new BleTransport({
      driver,
      sessionGeneration: 1,
      leases,
      clock: new ManualClock()
    })
    const connecting = transport.connect()
    driver.resolveConnect()
    await expect(connecting).rejects.toMatchObject({
      message: 'Connection failed: discovery blew up'
    })
    expect(driver.disconnectCalls).toBe(1)
    expect(leases.activeLease(driver.id)).toBeNull()
  })
})

describe('BleTransport reads', () => {
  it('resolves a read with case-insensitive characteristic lookup', async () => {
    const { driver, transport } = await setup()
    const reading = transport.readCharacteristic(
      OMI_SERVICE.toLowerCase(),
      '19B10002-E8F2-537E-4F6C-D104768A1214'
    )
    driver.resolveNextRead([20])
    await expect(reading).resolves.toEqual(Uint8Array.from([20]))
  })

  it('a timed-out read poisons the characteristic, drops the late value, and never suppresses notifications', async () => {
    const { driver, clock, transport } = await setup()
    const stream = recorder()
    transport.subscribeCharacteristic(BATTERY_SERVICE, BATTERY_LEVEL, stream)

    const reading = transport.readCharacteristic(BATTERY_SERVICE, BATTERY_LEVEL)
    clock.fireAll()
    await expect(reading).rejects.toMatchObject({
      kind: 'readFailed',
      message: 'Read failed: Operation timed out'
    })

    await expect(
      transport.readCharacteristic(BATTERY_SERVICE, BATTERY_LEVEL)
    ).rejects.toMatchObject({
      message: 'Read failed: A previous read has an uncorrelated callback; reconnect the device'
    })

    // The late physical value must be dropped, not attributed to anything.
    driver.resolveNextRead([88])
    await Promise.resolve()

    // ...but notifications on the same characteristic still flow.
    driver.notify(BATTERY_SERVICE, BATTERY_LEVEL, [90])
    expect(stream.frames).toEqual([Uint8Array.from([90])])

    // The write gate is independent of the poisoned read gate.
    const writing = transport.writeCharacteristic({
      serviceUuid: BATTERY_SERVICE,
      characteristicUuid: BATTERY_LEVEL,
      data: Uint8Array.from([1])
    })
    driver.resolveNextWrite()
    await expect(writing).resolves.toBeUndefined()
  })

  it('suppresses the notification echo of a pending read', async () => {
    const { driver, transport } = await setup()
    const stream = recorder()
    transport.subscribeCharacteristic(BATTERY_SERVICE, BATTERY_LEVEL, stream)

    const reading = transport.readCharacteristic(BATTERY_SERVICE, BATTERY_LEVEL)
    driver.notify(BATTERY_SERVICE, BATTERY_LEVEL, [77])
    expect(stream.frames.length).toBe(0)
    driver.resolveNextRead([77])
    await expect(reading).resolves.toEqual(Uint8Array.from([77]))

    driver.notify(BATTERY_SERVICE, BATTERY_LEVEL, [76])
    expect(stream.frames).toEqual([Uint8Array.from([76])])
  })

  it('guards disposed, not-connected, and unknown characteristics', async () => {
    const { transport } = await setup()
    await expect(
      transport.readCharacteristic(OMI_SERVICE, 'ffff0000-0000-0000-0000-000000000000')
    ).rejects.toMatchObject({ kind: 'characteristicNotFound' })

    const fresh = new BleTransport({
      driver: new FakeDriver(),
      sessionGeneration: 9,
      leases: new BluetoothConnectionLeaseRegistry(),
      clock: new ManualClock()
    })
    await expect(fresh.readCharacteristic(OMI_SERVICE, OMI_AUDIO)).rejects.toMatchObject({
      kind: 'notConnected'
    })

    await transport.dispose()
    await expect(transport.readCharacteristic(OMI_SERVICE, OMI_AUDIO)).rejects.toMatchObject({
      kind: 'disposed'
    })
  })
})

describe('BleTransport writes', () => {
  it('write with response resolves on the physical acknowledgement', async () => {
    const { driver, transport } = await setup()
    const writing = transport.writeCharacteristic({
      serviceUuid: OMI_SERVICE,
      characteristicUuid: OMI_AUDIO,
      data: Uint8Array.from([1, 2])
    })
    expect(driver.writes[0]).toMatchObject({ withResponse: true })
    driver.resolveNextWrite()
    await expect(writing).resolves.toBeUndefined()
  })

  it('write without response returns immediately and never waits', async () => {
    const { driver, transport } = await setup()
    await transport.writeCharacteristic({
      serviceUuid: OMI_SERVICE,
      characteristicUuid: OMI_AUDIO,
      data: Uint8Array.from([9]),
      withResponse: false
    })
    expect(driver.writes[0]).toMatchObject({ withResponse: false })
    expect(driver.pendingWrites.length).toBe(0)
  })

  it('a timed-out write poisons the write gate until reconnect', async () => {
    const { driver, clock, transport } = await setup()
    const writing = transport.writeCharacteristic({
      serviceUuid: OMI_SERVICE,
      characteristicUuid: OMI_AUDIO,
      data: Uint8Array.from([1])
    })
    clock.fireAll()
    await expect(writing).rejects.toMatchObject({
      kind: 'writeFailed',
      message: 'Write failed: Operation timed out'
    })
    await expect(
      transport.writeCharacteristic({
        serviceUuid: OMI_SERVICE,
        characteristicUuid: OMI_AUDIO,
        data: Uint8Array.from([2])
      })
    ).rejects.toMatchObject({
      message: 'Write failed: A previous write has an uncorrelated callback; reconnect the device'
    })
    driver.resolveNextWrite()
  })
})

describe('BleTransport streams and teardown', () => {
  it('multicasts notifications with a single physical subscription', async () => {
    const { driver, transport } = await setup()
    const first = recorder()
    const second = recorder()
    const firstSub = transport.subscribeCharacteristic(OMI_SERVICE, OMI_AUDIO, first)
    transport.subscribeCharacteristic(OMI_SERVICE, OMI_AUDIO, second)
    expect(driver.notifyStarts.length).toBe(1)

    driver.notify(OMI_SERVICE, OMI_AUDIO, [5])
    expect(first.frames.length).toBe(1)
    expect(second.frames.length).toBe(1)

    firstSub.cancel()
    driver.notify(OMI_SERVICE, OMI_AUDIO, [6])
    expect(first.frames.length).toBe(1)
    expect(second.frames.length).toBe(2)
  })

  it('an unexpected disconnect fails pending operations and finishes streams with an error', async () => {
    const { driver, transport, leases } = await setup()
    const stream = recorder()
    transport.subscribeCharacteristic(OMI_SERVICE, OMI_AUDIO, stream)
    const reading = transport.readCharacteristic(BATTERY_SERVICE, BATTERY_LEVEL)

    driver.fireDisconnected()
    await expect(reading).rejects.toMatchObject({
      message: 'Read failed: Device disconnected before the operation completed'
    })
    expect(stream.finished?.error).toBeInstanceOf(DeviceOperationBrokerError)
    expect(transport.state).toBe('disconnected')
    expect(leases.activeLease(driver.id)).toBeNull()
  })

  it('a clean disconnect finishes streams without error', async () => {
    const { driver, transport, leases } = await setup()
    const stream = recorder()
    transport.subscribeCharacteristic(OMI_SERVICE, OMI_AUDIO, stream)
    const states: string[] = []
    transport.onStateChange((s) => states.push(s))

    await transport.disconnect()
    expect(stream.finished).toEqual({ error: null })
    expect(states).toEqual(['disconnecting', 'disconnected'])
    expect(driver.disconnectCalls).toBe(1)
    expect(leases.activeLease(driver.id)).toBeNull()
  })

  it('subscribing on a disposed transport finishes immediately', async () => {
    const { transport } = await setup()
    await transport.dispose()
    const stream = recorder()
    transport.subscribeCharacteristic(OMI_SERVICE, OMI_AUDIO, stream)
    expect(stream.finished?.error).toBeInstanceOf(DeviceTransportError)
    expect((stream.finished?.error as DeviceTransportError).kind).toBe('disposed')
  })
})
