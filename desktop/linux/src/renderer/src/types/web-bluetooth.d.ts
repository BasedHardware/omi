type BluetoothCharacteristicValue = DataView

declare global {
  interface Navigator {
    bluetooth?: Bluetooth
  }

  interface Bluetooth {
    requestDevice(options: RequestDeviceOptions): Promise<BluetoothDevice>
  }

  interface BluetoothDevice extends EventTarget {
    name?: string
    gatt: BluetoothRemoteGATTServer | null
    addEventListener(
      type: 'gattserverdisconnected',
      listener: (this: BluetoothDevice, ev: Event) => void,
      options?: boolean | AddEventListenerOptions
    ): void
  }

  interface BluetoothRemoteGATTServer {
    connected: boolean
    connect(): Promise<BluetoothRemoteGATTServer>
    disconnect(): void
    getPrimaryService(service: BluetoothServiceUUID): Promise<BluetoothRemoteGATTService>
  }

  interface BluetoothRemoteGATTService {
    getCharacteristic(characteristic: BluetoothCharacteristicUUID): Promise<BluetoothRemoteGATTCharacteristic>
  }

  interface BluetoothRemoteGATTCharacteristic extends EventTarget {
    value: BluetoothCharacteristicValue | null
    readValue(): Promise<BluetoothCharacteristicValue>
    startNotifications(): Promise<BluetoothRemoteGATTCharacteristic>
    addEventListener(
      type: 'characteristicvaluechanged',
      listener: (this: BluetoothRemoteGATTCharacteristic, ev: Event) => void,
      options?: boolean | AddEventListenerOptions
    ): void
  }

  type BluetoothServiceUUID = number | string
  type BluetoothCharacteristicUUID = number | string
}

export {}