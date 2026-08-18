/**
 * Device session coordinator — Windows port of macOS
 * Session/DeviceSessionCoordinator.swift. Owns the phase machine for one
 * paired wearable: which connection attempt is current, when a reconnect is
 * allowed, and which callbacks belong to a live generation.
 *
 * Every transition bumps the generation, so a callback from an abandoned
 * attempt can be recognized and dropped instead of mutating a newer session.
 */

import type { BtDevice } from '../protocol/btDevice'
import type { DeviceConnection } from '../connections/deviceConnection'
import { RealDeviceOperationClock, type DeviceOperationClock } from './deviceOperationBroker'

export type SessionPhaseKind =
  | 'idle'
  | 'connecting'
  | 'ready'
  | 'disconnecting'
  | 'waitingToReconnect'

export interface SessionPhase {
  kind: SessionPhaseKind
  /** Present on waitingToReconnect: which retry is pending. */
  attempt?: number
}

export interface DeviceSessionSnapshot {
  generation: number
  phase: SessionPhase
  pairedDevice: BtDevice | null
  connectedDevice: BtDevice | null
  failureMessage: string | null
}

export type DeviceSessionErrorKind =
  | 'connectionAlreadyActive'
  | 'connectionUnavailable'
  | 'superseded'

export class DeviceSessionError extends Error {
  readonly kind: DeviceSessionErrorKind

  private constructor(kind: DeviceSessionErrorKind, message: string) {
    super(message)
    this.name = 'DeviceSessionError'
    this.kind = kind
  }

  static connectionAlreadyActive(): DeviceSessionError {
    return new DeviceSessionError(
      'connectionAlreadyActive',
      'A device connection is already active'
    )
  }

  static connectionUnavailable(): DeviceSessionError {
    return new DeviceSessionError(
      'connectionUnavailable',
      'The device is not currently available over Bluetooth'
    )
  }

  static superseded(): DeviceSessionError {
    return new DeviceSessionError('superseded', 'The device connection was superseded')
  }
}

export interface DeviceReconnectRequest {
  device: BtDevice
  generation: number
  attempt: number
}

export interface DeviceSessionCallbacks {
  /** Builds a connection for one attempt; null when the device is not
   *  currently reachable (for example not in the discovery cache). */
  connectionFactory: (device: BtDevice, generation: number) => DeviceConnection | null
  onSnapshot?: (snapshot: DeviceSessionSnapshot) => void
  onSessionEnded?: () => void
  onReconnectRequested?: (request: DeviceReconnectRequest) => void
  /** Asked before a delayed reconnect so a scan can refresh the cache. */
  onDiscoveryRequested?: () => void
}

/** Fixed, not exponential: the mac stack retries at this cadence forever. */
export const RECONNECT_DELAY_MS = 15_000

const allowsConnectionAttempt = (phase: SessionPhase): boolean =>
  phase.kind === 'idle' || phase.kind === 'waitingToReconnect'

export class DeviceSessionCoordinator {
  private generation = 0
  private phase: SessionPhase = { kind: 'idle' }
  private pairedDevice: BtDevice | null
  private connectedDevice: BtDevice | null = null
  private failureMessage: string | null = null
  private activeConnection: DeviceConnection | null = null
  private reconnectAttempt = 0
  private reconnectAbort: AbortController | null = null

  autoReconnectEnabled = true

  constructor(
    private readonly callbacks: DeviceSessionCallbacks,
    options: { pairedDevice?: BtDevice | null; clock?: DeviceOperationClock } = {}
  ) {
    this.pairedDevice = options.pairedDevice ?? null
    this.clock = options.clock ?? new RealDeviceOperationClock()
  }

  private readonly clock: DeviceOperationClock

  get snapshot(): DeviceSessionSnapshot {
    return {
      generation: this.generation,
      phase: { ...this.phase },
      pairedDevice: this.pairedDevice,
      connectedDevice: this.connectedDevice,
      failureMessage: this.failureMessage
    }
  }

  get connection(): DeviceConnection | null {
    return this.activeConnection
  }

  // --- connect ---------------------------------------------------------------

  /**
   * Opens a session. A reconnect request must still match the generation,
   * phase, attempt and device it was scheduled for; anything else means a
   * newer decision has already replaced it.
   */
  async connect(device: BtDevice, reconnect?: DeviceReconnectRequest): Promise<void> {
    if (reconnect !== undefined) {
      const matches =
        reconnect.generation === this.generation &&
        this.phase.kind === 'waitingToReconnect' &&
        this.phase.attempt === reconnect.attempt &&
        this.pairedDevice?.id === reconnect.device.id &&
        // A retry token is for ONE device: without this, a valid token could be
        // replayed to open a session against a different device.
        reconnect.device.id === device.id
      if (!matches) throw DeviceSessionError.superseded()
    } else if (!allowsConnectionAttempt(this.phase)) {
      throw DeviceSessionError.connectionAlreadyActive()
    }

    this.cancelScheduledReconnect()
    const generation = ++this.generation
    this.phase = { kind: 'connecting' }
    this.connectedDevice = null
    this.failureMessage = null
    this.publish()

    const connection = this.callbacks.connectionFactory(device, generation)
    if (connection === null) {
      this.recordConnectionFailure(
        generation,
        DeviceSessionError.connectionUnavailable().message,
        reconnect !== undefined
      )
      throw DeviceSessionError.connectionUnavailable()
    }

    this.activeConnection = connection
    try {
      await connection.connect()
    } catch (error) {
      if (this.generation !== generation) {
        await connection.disconnect()
        throw DeviceSessionError.superseded()
      }
      this.activeConnection = null
      this.recordConnectionFailure(
        generation,
        error instanceof Error ? error.message : String(error),
        reconnect !== undefined
      )
      await connection.disconnect()
      throw error
    }

    if (this.generation !== generation || this.phase.kind !== 'connecting') {
      await connection.disconnect()
      throw DeviceSessionError.superseded()
    }

    this.reconnectAttempt = 0
    this.phase = { kind: 'ready' }
    this.pairedDevice = connection.device
    this.connectedDevice = connection.device
    this.publish()
  }

  private recordConnectionFailure(
    generation: number,
    message: string,
    wasReconnectAttempt: boolean
  ): void {
    if (this.generation !== generation) return
    this.phase = { kind: 'idle' }
    this.failureMessage = message
    this.publish()
    if (wasReconnectAttempt) {
      // The immediate retry already failed, so fall back to the delayed path,
      // which rescans before trying again.
      this.scheduleReconnectIfNeeded(RECONNECT_DELAY_MS)
    }
  }

  // --- disconnect / unpair ----------------------------------------------------

  /**
   * Tears the session down. reconnectAfterMs defaults to 0, which means
   * "reconnect immediately without scanning"; null means stay disconnected.
   */
  async disconnect(reconnectAfterMs: number | null = 0): Promise<void> {
    this.cancelScheduledReconnect()
    const connection = this.activeConnection
    if (connection === null) {
      if (reconnectAfterMs === null) {
        this.phase = { kind: 'idle' }
        this.publish()
      } else {
        this.scheduleReconnectIfNeeded(reconnectAfterMs)
      }
      return
    }

    const generation = ++this.generation
    this.activeConnection = null
    this.phase = { kind: 'disconnecting' }
    this.connectedDevice = null
    this.publish()

    await connection.disconnect()

    if (this.generation === generation) {
      this.phase = { kind: 'idle' }
      this.publish()
      this.callbacks.onSessionEnded?.()
    }
    if (reconnectAfterMs !== null) this.scheduleReconnectIfNeeded(reconnectAfterMs)
  }

  async unpair(): Promise<void> {
    this.cancelScheduledReconnect()
    const connection = this.activeConnection
    const generation = ++this.generation
    this.activeConnection = null
    this.connectedDevice = null
    this.pairedDevice = null
    this.phase = { kind: connection === null ? 'idle' : 'disconnecting' }
    this.publish()

    if (connection !== null) {
      await connection.unpair()
      if (this.generation === generation) {
        this.callbacks.onSessionEnded?.()
        this.phase = { kind: 'idle' }
        this.publish()
      }
    }
  }

  /** Called by the connection delegate; ignored unless it is the live one. */
  handleUnexpectedDisconnect(connection: DeviceConnection): void {
    if (this.activeConnection !== connection) return
    this.activeConnection = null
    this.generation += 1
    this.phase = { kind: 'idle' }
    this.connectedDevice = null
    this.failureMessage = 'Device disconnected unexpectedly'
    this.publish()
    this.callbacks.onSessionEnded?.()
    // Immediate: the cached peripheral is still valid right after a drop.
    this.scheduleReconnectIfNeeded(0)
  }

  // --- reconnect scheduling ---------------------------------------------------

  startReconnecting(): void {
    this.scheduleReconnectIfNeeded(0)
  }

  stopReconnecting(): void {
    this.cancelScheduledReconnect()
    if (this.phase.kind === 'waitingToReconnect') {
      this.phase = { kind: 'idle' }
      this.publish()
    }
  }

  private scheduleReconnectIfNeeded(delayMs: number): void {
    if (!this.autoReconnectEnabled) return
    const device = this.pairedDevice
    if (device === null) return
    if (!allowsConnectionAttempt(this.phase)) return

    this.cancelScheduledReconnect()
    this.reconnectAttempt += 1
    const attempt = this.reconnectAttempt
    const generation = this.generation
    this.phase = { kind: 'waitingToReconnect', attempt }
    this.publish()

    if (delayMs > 0) {
      // A delayed retry rescans first. The zero-delay path deliberately does
      // not: scanning clears the cached peripheral the direct reconnect needs.
      this.callbacks.onDiscoveryRequested?.()
    }

    const abort = new AbortController()
    this.reconnectAbort = abort
    void (async () => {
      if (delayMs > 0) {
        const outcome = await this.clock.sleep(delayMs, abort.signal)
        if (outcome !== 'elapsed') return
      }
      if (abort.signal.aborted) return
      const stillValid =
        this.generation === generation &&
        this.phase.kind === 'waitingToReconnect' &&
        this.phase.attempt === attempt &&
        this.pairedDevice?.id === device.id
      if (!stillValid) return
      this.callbacks.onReconnectRequested?.({ device, generation, attempt })
    })()
  }

  private cancelScheduledReconnect(): void {
    this.reconnectAbort?.abort()
    this.reconnectAbort = null
  }

  setPairedDevice(device: BtDevice | null): void {
    this.pairedDevice = device
    this.publish()
  }

  private publish(): void {
    this.callbacks.onSnapshot?.(this.snapshot)
  }
}
