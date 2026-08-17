import { describe, it, expect } from 'vitest'
import {
  BluetoothConnectionLeaseError,
  BluetoothConnectionLeaseRegistry
} from './bluetoothConnectionLease'

describe('BluetoothConnectionLeaseRegistry', () => {
  it('one attempt per device, with monotonic tokens', () => {
    const registry = new BluetoothConnectionLeaseRegistry()
    const first = registry.begin('dev-a', 1)
    expect(() => registry.begin('dev-a', 2)).toThrow(
      'A previous Bluetooth connection attempt is still draining'
    )
    const other = registry.begin('dev-b', 1)
    expect(other.token).toBeGreaterThan(first.token)
    registry.end(first)
    const second = registry.begin('dev-a', 2)
    expect(second.token).toBeGreaterThan(other.token)
  })

  it('cancellation keeps the entry fenced until the terminal end()', () => {
    const registry = new BluetoothConnectionLeaseRegistry()
    const lease = registry.begin('dev-a', 1)
    registry.requestCancellation(lease)
    expect(registry.activeLease('dev-a')).toEqual(lease)
    expect(() => registry.begin('dev-a', 2)).toThrow(BluetoothConnectionLeaseError)
    registry.end(lease)
    expect(registry.activeLease('dev-a')).toBeNull()
    expect(() => registry.begin('dev-a', 2)).not.toThrow()
  })

  it('stale tokens cannot end or mutate a newer lease', () => {
    const registry = new BluetoothConnectionLeaseRegistry()
    const first = registry.begin('dev-a', 1)
    registry.end(first)
    const second = registry.begin('dev-a', 2)
    registry.end(first)
    registry.requestCancellation(first)
    expect(registry.activeLease('dev-a')).toEqual(second)
  })

  it('reset clears every fence', () => {
    const registry = new BluetoothConnectionLeaseRegistry()
    registry.begin('dev-a', 1)
    registry.begin('dev-b', 1)
    registry.reset()
    expect(registry.activeLease('dev-a')).toBeNull()
    expect(() => registry.begin('dev-b', 2)).not.toThrow()
  })
})
