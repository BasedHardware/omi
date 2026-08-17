/**
 * Narrow side-effect seam over the platform Bluetooth stack — Windows port of
 * macOS Transports/BLEPhysicalDriver.swift, adapted from CBPeripheral to
 * WebBluetooth. The transport stays unit-testable because everything physical
 * goes through this interface; the concrete driver below is a thin adapter
 * over a chooser-granted BluetoothDevice.
 */

export interface DiscoveredCharacteristic {
  uuid: string
}

export interface DiscoveredService {
  uuid: string
}

export interface BlePhysicalDriver {
  readonly id: string
  readonly name: string | null
  isConnected(): boolean
  connect(): Promise<void>
  disconnect(): void
  discoverServices(): Promise<DiscoveredService[]>
  discoverCharacteristics(serviceUuid: string): Promise<DiscoveredCharacteristic[]>
  readValue(serviceUuid: string, characteristicUuid: string): Promise<Uint8Array>
  writeValue(
    serviceUuid: string,
    characteristicUuid: string,
    data: Uint8Array,
    withResponse: boolean
  ): Promise<void>
  startNotifications(
    serviceUuid: string,
    characteristicUuid: string,
    onValue: (data: Uint8Array) => void
  ): Promise<void>
  /** Fires on unexpected physical disconnects; returns the unsubscriber. */
  onDisconnected(listener: () => void): () => void
}

// --- WebBluetooth structural types ------------------------------------------
// The DOM lib does not ship Bluetooth types by default; these structural
// interfaces cover exactly what the driver touches.

interface GattCharacteristicLike {
  readonly uuid: string
  readonly value: DataView | null
  readValue(): Promise<DataView>
  writeValueWithResponse(value: BufferSource): Promise<void>
  writeValueWithoutResponse(value: BufferSource): Promise<void>
  startNotifications(): Promise<unknown>
  addEventListener(type: 'characteristicvaluechanged', listener: (event: Event) => void): void
  removeEventListener(type: 'characteristicvaluechanged', listener: (event: Event) => void): void
}

interface GattServiceLike {
  readonly uuid: string
  getCharacteristics(): Promise<GattCharacteristicLike[]>
}

interface GattServerLike {
  readonly connected: boolean
  connect(): Promise<GattServerLike>
  disconnect(): void
  getPrimaryServices(): Promise<GattServiceLike[]>
}

export interface BluetoothDeviceLike {
  readonly id: string
  readonly name?: string | null
  readonly gatt?: GattServerLike
  addEventListener(type: 'gattserverdisconnected', listener: (event: Event) => void): void
  removeEventListener(type: 'gattserverdisconnected', listener: (event: Event) => void): void
}

const dataViewToBytes = (view: DataView): Uint8Array =>
  new Uint8Array(view.buffer.slice(view.byteOffset, view.byteOffset + view.byteLength))

export class WebBluetoothPhysicalDriver implements BlePhysicalDriver {
  private services = new Map<string, GattServiceLike>()
  private characteristics = new Map<string, GattCharacteristicLike>()
  // Chromium rejects concurrent GATT operations on one device with
  // "GATT operation already in progress", so every operation is serialized
  // through this chain. Timeouts stay a transport/broker concern.
  private gattChain: Promise<unknown> = Promise.resolve()

  constructor(private readonly device: BluetoothDeviceLike) {}

  private enqueue<T>(operation: () => Promise<T>): Promise<T> {
    const task = this.gattChain.then(
      () => operation(),
      () => operation()
    )
    this.gattChain = task.then(
      () => undefined,
      () => undefined
    )
    return task
  }

  get id(): string {
    return this.device.id
  }

  get name(): string | null {
    return this.device.name ?? null
  }

  isConnected(): boolean {
    return this.device.gatt?.connected ?? false
  }

  async connect(): Promise<void> {
    const gatt = this.device.gatt
    if (gatt === undefined) {
      throw new Error('Device has no GATT server')
    }
    await gatt.connect()
  }

  disconnect(): void {
    this.device.gatt?.disconnect()
  }

  async discoverServices(): Promise<DiscoveredService[]> {
    const gatt = this.device.gatt
    if (gatt === undefined) {
      throw new Error('Device has no GATT server')
    }
    const services = await this.enqueue(() => gatt.getPrimaryServices())
    this.services.clear()
    for (const service of services) {
      this.services.set(service.uuid.toLowerCase(), service)
    }
    return services.map((s) => ({ uuid: s.uuid }))
  }

  async discoverCharacteristics(serviceUuid: string): Promise<DiscoveredCharacteristic[]> {
    const service = this.services.get(serviceUuid.toLowerCase())
    if (service === undefined) {
      throw new Error(`Service not discovered: ${serviceUuid}`)
    }
    const characteristics = await this.enqueue(() => service.getCharacteristics())
    for (const characteristic of characteristics) {
      this.characteristics.set(
        characteristicKey(serviceUuid, characteristic.uuid),
        characteristic
      )
    }
    return characteristics.map((c) => ({ uuid: c.uuid }))
  }

  async readValue(serviceUuid: string, characteristicUuid: string): Promise<Uint8Array> {
    const characteristic = this.characteristic(serviceUuid, characteristicUuid)
    const view = await this.enqueue(() => characteristic.readValue())
    return dataViewToBytes(view)
  }

  async writeValue(
    serviceUuid: string,
    characteristicUuid: string,
    data: Uint8Array,
    withResponse: boolean
  ): Promise<void> {
    const characteristic = this.characteristic(serviceUuid, characteristicUuid)
    if (withResponse) {
      await this.enqueue(() => characteristic.writeValueWithResponse(data))
    } else {
      await this.enqueue(() => characteristic.writeValueWithoutResponse(data))
    }
  }

  async startNotifications(
    serviceUuid: string,
    characteristicUuid: string,
    onValue: (data: Uint8Array) => void
  ): Promise<void> {
    const characteristic = this.characteristic(serviceUuid, characteristicUuid)
    characteristic.addEventListener('characteristicvaluechanged', () => {
      const value = characteristic.value
      if (value !== null) onValue(dataViewToBytes(value))
    })
    await this.enqueue(() => characteristic.startNotifications())
  }

  onDisconnected(listener: () => void): () => void {
    const handler = (): void => listener()
    this.device.addEventListener('gattserverdisconnected', handler)
    return () => this.device.removeEventListener('gattserverdisconnected', handler)
  }

  private characteristic(serviceUuid: string, characteristicUuid: string): GattCharacteristicLike {
    const characteristic = this.characteristics.get(characteristicKey(serviceUuid, characteristicUuid))
    if (characteristic === undefined) {
      throw new Error(`Characteristic not discovered: ${characteristicUuid}`)
    }
    return characteristic
  }
}

const characteristicKey = (serviceUuid: string, characteristicUuid: string): string =>
  `${serviceUuid.toLowerCase()}:${characteristicUuid.toLowerCase()}`
