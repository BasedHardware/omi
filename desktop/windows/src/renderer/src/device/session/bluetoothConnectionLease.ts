/**
 * Connection attempt identity fencing — Windows port of macOS
 * Session/BluetoothConnectionLease.swift. A GATT connect cannot be reliably
 * cancelled mid-flight, so one attempt's identity stays pinned (the entry is
 * kept, merely marked cancelling) until a terminal event reports the attempt
 * dead; a later session can neither start on top of it nor consume its stale
 * completion.
 */

export interface BluetoothConnectionLease {
  deviceId: string
  token: number
  sessionGeneration: number
}

export class BluetoothConnectionLeaseError extends Error {
  readonly kind: 'leaseAlreadyActive' | 'centralUnavailable'

  private constructor(kind: 'leaseAlreadyActive' | 'centralUnavailable', message: string) {
    super(message)
    this.name = 'BluetoothConnectionLeaseError'
    this.kind = kind
  }

  static leaseAlreadyActive(): BluetoothConnectionLeaseError {
    return new BluetoothConnectionLeaseError(
      'leaseAlreadyActive',
      'A previous Bluetooth connection attempt is still draining'
    )
  }

  static centralUnavailable(): BluetoothConnectionLeaseError {
    return new BluetoothConnectionLeaseError('centralUnavailable', 'Bluetooth is not powered on')
  }
}

type LeasePhase = 'connecting' | 'connected' | 'cancelling'

interface LeaseEntry {
  lease: BluetoothConnectionLease
  phase: LeasePhase
}

export class BluetoothConnectionLeaseRegistry {
  private entries = new Map<string, LeaseEntry>()
  private nextToken = 1

  /** Starts a connection attempt. Throws while ANY entry exists for the
   *  device — including one that is only draining after cancellation. */
  begin(deviceId: string, sessionGeneration: number): BluetoothConnectionLease {
    if (this.entries.has(deviceId)) {
      throw BluetoothConnectionLeaseError.leaseAlreadyActive()
    }
    const lease: BluetoothConnectionLease = {
      deviceId,
      token: this.nextToken++,
      sessionGeneration
    }
    this.entries.set(deviceId, { lease, phase: 'connecting' })
    return lease
  }

  markConnected(lease: BluetoothConnectionLease): void {
    const entry = this.entries.get(lease.deviceId)
    if (entry === undefined || entry.lease.token !== lease.token) return
    if (entry.phase === 'connecting') entry.phase = 'connected'
  }

  /** Marks the attempt cancelling but KEEPS the entry — identity stays fenced
   *  until the platform reports a terminal event for it. */
  requestCancellation(lease: BluetoothConnectionLease): void {
    const entry = this.entries.get(lease.deviceId)
    if (entry === undefined || entry.lease.token !== lease.token) return
    entry.phase = 'cancelling'
  }

  /** Terminal event for the attempt: releases the fence. Stale tokens no-op. */
  end(lease: BluetoothConnectionLease): void {
    const entry = this.entries.get(lease.deviceId)
    if (entry === undefined || entry.lease.token !== lease.token) return
    this.entries.delete(lease.deviceId)
  }

  activeLease(deviceId: string): BluetoothConnectionLease | null {
    return this.entries.get(deviceId)?.lease ?? null
  }

  /** Central reset: every fence is void because the platform state is gone. */
  reset(): void {
    this.entries.clear()
  }
}
