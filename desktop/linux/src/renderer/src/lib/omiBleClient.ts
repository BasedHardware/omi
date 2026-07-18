// src/renderer/src/lib/omiBleClient.ts
// Bluetooth Low Energy client for Omi wearable device
// Uses Web Bluetooth API to connect and stream audio from the Omi device

const OMI_DEVICE_NAME = 'Omi'

// BLE Service UUIDs
const BATTERY_SERVICE_UUID = 0x180F
const DEVICE_INFO_SERVICE_UUID = 0x180A
const AUDIO_SERVICE_UUID = '19b10000-e8f2-537e-4f6c-d104768a1214'

// Audio Service Characteristic UUIDs
const AUDIO_DATA_UUID = '19b10001-e8f2-537e-4f6c-d104768a1214'
const CODEC_TYPE_UUID = '19b10002-e8f2-537e-4f6c-d104768a1214'

// Codec types
const CODEC_PCM = 0
export type OmiDeviceState = 'disconnected' | 'scanning' | 'connecting' | 'connected'

export type OmiDeviceInfo = {
  name: string
  firmwareRevision?: string
  manufacturerName?: string
  batteryLevel?: number
}

export type OmiBleCallbacks = {
  onStateChange?: (state: OmiDeviceState) => void
  onDeviceInfo?: (info: OmiDeviceInfo) => void
  onBatteryLevel?: (level: number) => void
  onAudioData?: (data: ArrayBuffer, codec: number) => void
  onError?: (error: string) => void
}

class OmiBleClient {
  private device: BluetoothDevice | null = null
  private server: BluetoothRemoteGATTServer | null = null
  private audioCharacteristic: BluetoothRemoteGATTCharacteristic | null = null
  private codecCharacteristic: BluetoothRemoteGATTCharacteristic | null = null
  private state: OmiDeviceState = 'disconnected'
  private callbacks: OmiBleCallbacks = {}
  private currentCodec = CODEC_PCM

  on(callbacks: OmiBleCallbacks): () => void {
    this.callbacks = { ...this.callbacks, ...callbacks }
    return () => {
      this.callbacks = {}
    }
  }

  private setState(state: OmiDeviceState): void {
    this.state = state
    this.callbacks.onStateChange?.(state)
  }

  async scan(): Promise<BluetoothDevice | null> {
    if (!navigator.bluetooth) {
      this.callbacks.onError?.('Web Bluetooth not supported in this browser')
      return null
    }

    this.setState('scanning')

    try {
      const device = await navigator.bluetooth.requestDevice({
        filters: [
          { name: OMI_DEVICE_NAME },
          { services: [AUDIO_SERVICE_UUID] }
        ],
        optionalServices: [
          BATTERY_SERVICE_UUID,
          DEVICE_INFO_SERVICE_UUID
        ]
      })

      this.device = device
      device.addEventListener('gattserverdisconnected', () => this.handleDisconnect())
      return device
    } catch (e) {
      const msg = (e as Error).message
      if (msg.includes('cancelled') || msg.includes('User cancelled')) {
        this.setState('disconnected')
        return null
      }
      this.callbacks.onError?.(`Scan failed: ${msg}`)
      this.setState('disconnected')
      return null
    }
  }

  async connect(device?: BluetoothDevice): Promise<boolean> {
    const d = device || this.device
    if (!d) {
      this.callbacks.onError?.('No device to connect to')
      return false
    }

    this.setState('connecting')

    try {
      const gatt = d.gatt
      if (!gatt) throw new Error('Bluetooth GATT server unavailable')

      if (!gatt.connected) {
        this.server = await gatt.connect()
      } else {
        this.server = gatt
      }

      const server = this.server
      if (!server) throw new Error('Bluetooth server unavailable')

      // Get device info
      try {
        const infoService = await server.getPrimaryService(DEVICE_INFO_SERVICE_UUID)
        const firmwareChar = await infoService.getCharacteristic(0x2A26)
        const firmwareValue = await firmwareChar.readValue()
        const firmwareRevision = new TextDecoder().decode(firmwareValue)

        this.callbacks.onDeviceInfo?.({
          name: d.name || 'Omi',
          firmwareRevision,
          manufacturerName: 'Based Hardware'
        })
      } catch {
        // Device info not available (older firmware)
      }

      // Get battery level
      try {
        const batteryService = await server.getPrimaryService(BATTERY_SERVICE_UUID)
        const batteryChar = await batteryService.getCharacteristic(0x2A19)
        const batteryValue = await batteryChar.readValue()
        const batteryLevel = batteryValue.getUint8(0)
        this.callbacks.onBatteryLevel?.(batteryLevel)
      } catch {
        // Battery not available (older firmware)
      }

      // Get audio service
      const audioService = await server.getPrimaryService(AUDIO_SERVICE_UUID)
      this.audioCharacteristic = await audioService.getCharacteristic(AUDIO_DATA_UUID)
      const audioCharacteristic = this.audioCharacteristic
      if (!audioCharacteristic) throw new Error('Audio characteristic unavailable')

      // Try to get codec characteristic
      try {
        this.codecCharacteristic = await audioService.getCharacteristic(CODEC_TYPE_UUID)
        const codecValue = await this.codecCharacteristic.readValue()
        this.currentCodec = codecValue.getUint8(0)
      } catch {
        this.currentCodec = CODEC_PCM
      }

      // Start notifications on audio characteristic
      await audioCharacteristic.startNotifications()
      audioCharacteristic.addEventListener('characteristicvaluechanged', (event) => {
        const value = (event as Event).target as BluetoothRemoteGATTCharacteristic
        if (value.value) {
          this.callbacks.onAudioData?.(value.value.buffer as ArrayBuffer, this.currentCodec)
        }
      })

      this.setState('connected')
      return true
    } catch (e) {
      this.callbacks.onError?.(`Connection failed: ${(e as Error).message}`)
      this.setState('disconnected')
      return false
    }
  }

  private handleDisconnect(): void {
    this.audioCharacteristic = null
    this.codecCharacteristic = null
    this.server = null
    this.device = null
    this.setState('disconnected')
  }

  disconnect(): void {
    if (this.device?.gatt?.connected) {
      this.device.gatt.disconnect()
    }
    this.handleDisconnect()
  }

  getState(): OmiDeviceState {
    return this.state
  }

  getDevice(): BluetoothDevice | null {
    return this.device
  }

  isConnected(): boolean {
    return this.state === 'connected'
  }
}

export const omiBleClient = new OmiBleClient()
