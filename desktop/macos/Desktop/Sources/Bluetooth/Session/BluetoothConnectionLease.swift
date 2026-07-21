@preconcurrency import CoreBluetooth
import Foundation

/// Manager-owned identity for one CoreBluetooth connection attempt.
///
/// CoreBluetooth delegate callbacks carry only a peripheral. The manager keeps
/// a lease active until a terminal delegate callback (or central reset), so a
/// later session cannot reuse that peripheral identity while an old callback is
/// still possible.
struct BluetoothConnectionLease: Equatable, Hashable, Sendable {
  let peripheralID: UUID
  let token: UInt64
  let sessionGeneration: UInt64
}

enum BluetoothConnectionLeaseError: LocalizedError, Equatable {
  case leaseAlreadyActive(BluetoothConnectionLease)
  case centralUnavailable

  var errorDescription: String? {
    switch self {
    case .leaseAlreadyActive:
      return "A previous Bluetooth connection attempt is still draining"
    case .centralUnavailable:
      return "Bluetooth is not powered on"
    }
  }
}

@MainActor
protocol BluetoothCentralConnectionControlling: AnyObject {
  func beginConnection(
    to peripheral: CBPeripheral,
    sessionGeneration: UInt64
  ) throws -> BluetoothConnectionLease

  func cancelConnection(
    to peripheral: CBPeripheral,
    lease: BluetoothConnectionLease
  )
}

@MainActor
final class BluetoothConnectionLeaseRegistry {
  private enum Phase: Equatable {
    case connecting
    case connected
    case cancelling
  }

  private struct Entry {
    let lease: BluetoothConnectionLease
    var phase: Phase
  }

  private var nextToken: UInt64 = 0
  private var entries: [UUID: Entry] = [:]

  func begin(
    peripheralID: UUID,
    sessionGeneration: UInt64
  ) throws -> BluetoothConnectionLease {
    if let existing = entries[peripheralID]?.lease {
      throw BluetoothConnectionLeaseError.leaseAlreadyActive(existing)
    }

    nextToken &+= 1
    let lease = BluetoothConnectionLease(
      peripheralID: peripheralID,
      token: nextToken,
      sessionGeneration: sessionGeneration
    )
    entries[peripheralID] = Entry(lease: lease, phase: .connecting)
    return lease
  }

  /// Marks cancellation without releasing identity. The lease remains fenced
  /// until CoreBluetooth reports failure/disconnect or the central resets.
  @discardableResult
  func requestCancellation(_ lease: BluetoothConnectionLease) -> Bool {
    guard var entry = entries[lease.peripheralID], entry.lease == lease else {
      return false
    }
    entry.phase = .cancelling
    entries[lease.peripheralID] = entry
    return true
  }

  func markConnected(
    peripheralID: UUID
  ) -> (lease: BluetoothConnectionLease, shouldCancel: Bool)? {
    guard var entry = entries[peripheralID] else { return nil }
    let shouldCancel = entry.phase == .cancelling
    if !shouldCancel {
      entry.phase = .connected
      entries[peripheralID] = entry
    }
    return (entry.lease, shouldCancel)
  }

  func finish(peripheralID: UUID) -> BluetoothConnectionLease? {
    entries.removeValue(forKey: peripheralID)?.lease
  }

  func reset() -> [BluetoothConnectionLease] {
    let leases = entries.values.map(\.lease)
    entries.removeAll()
    return leases
  }

  func activeLease(for peripheralID: UUID) -> BluetoothConnectionLease? {
    entries[peripheralID]?.lease
  }
}
