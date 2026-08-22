/**
 * Transport abstraction for wearable BLE connections — Windows port of macOS
 * Transports/DeviceTransport.swift. A transport is single-use: one physical
 * connection attempt per instance, fenced by a coordinator-assigned session
 * generation.
 */

export type DeviceTransportState = 'disconnected' | 'connecting' | 'connected' | 'disconnecting'

export type DeviceTransportErrorKind =
  | 'notConnected'
  | 'connectionFailed'
  | 'serviceNotFound'
  | 'characteristicNotFound'
  | 'readFailed'
  | 'writeFailed'
  | 'timeout'
  | 'disposed'

export class DeviceTransportError extends Error {
  readonly kind: DeviceTransportErrorKind

  private constructor(kind: DeviceTransportErrorKind, message: string) {
    super(message)
    this.name = 'DeviceTransportError'
    this.kind = kind
  }

  static notConnected(): DeviceTransportError {
    return new DeviceTransportError('notConnected', 'Device is not connected')
  }

  static connectionFailed(detail: string): DeviceTransportError {
    return new DeviceTransportError('connectionFailed', `Connection failed: ${detail}`)
  }

  static serviceNotFound(uuid: string): DeviceTransportError {
    return new DeviceTransportError('serviceNotFound', `Service not found: ${uuid}`)
  }

  static characteristicNotFound(uuid: string): DeviceTransportError {
    return new DeviceTransportError('characteristicNotFound', `Characteristic not found: ${uuid}`)
  }

  static readFailed(detail: string): DeviceTransportError {
    return new DeviceTransportError('readFailed', `Read failed: ${detail}`)
  }

  static writeFailed(detail: string): DeviceTransportError {
    return new DeviceTransportError('writeFailed', `Write failed: ${detail}`)
  }

  static timeout(): DeviceTransportError {
    return new DeviceTransportError('timeout', 'Operation timed out')
  }

  static disposed(): DeviceTransportError {
    return new DeviceTransportError('disposed', 'Transport has been disposed')
  }
}

export interface CharacteristicStreamSubscriber {
  onData(data: Uint8Array): void
  /** Exactly once. Null on clean transport shutdown; an error on mid-session
   *  disconnects so stream consumers observe connection loss. */
  onFinish(error: Error | null): void
}

export interface CharacteristicStreamSubscription {
  cancel(): void
}

export interface DeviceTransport {
  readonly deviceId: string
  readonly sessionGeneration: number
  readonly state: DeviceTransportState
  onStateChange(listener: (state: DeviceTransportState) => void): () => void
  connect(): Promise<void>
  disconnect(): Promise<void>
  isConnected(): boolean
  /** Liveness probe: true when the physical link currently looks connected.
   *  There is no keepalive loop anywhere in this stack. */
  ping(): boolean
  subscribeCharacteristic(
    serviceUuid: string,
    characteristicUuid: string,
    subscriber: CharacteristicStreamSubscriber
  ): CharacteristicStreamSubscription
  readCharacteristic(serviceUuid: string, characteristicUuid: string): Promise<Uint8Array>
  writeCharacteristic(args: {
    serviceUuid: string
    characteristicUuid: string
    data: Uint8Array
    /** Defaults to true (write-with-response). */
    withResponse?: boolean
  }): Promise<void>
  dispose(): Promise<void>
}
