@preconcurrency import CoreFoundation
import Foundation
import IOKit.ps

/// Reads whether the Mac is low enough on battery that a background import
/// would be a rude use of the user's remaining charge.
///
/// AC-vs-battery comes from the existing ``PowerMonitor/cachedBatteryState()``
/// rather than a second IOKit subscription — `PowerMonitor` already owns the
/// power-source notification and caches the answer for hot paths. This probe
/// only reads the capacity percentage, and only when actually on battery.
enum ConnectorRefreshPowerProbe {
  /// Below this fraction of a full charge, background refresh defers.
  static let criticalBatteryFraction = 0.20

  nonisolated static func isBatteryCritical() -> Bool {
    // A Mac on AC (including every desktop Mac) is never battery-critical, so
    // the capacity read is skipped entirely in the common case.
    guard PowerMonitor.cachedBatteryState() else { return false }

    guard let snapshot = IOPSCopyPowerSourcesInfo()?.takeRetainedValue(),
      let sources = IOPSCopyPowerSourcesList(snapshot)?.takeRetainedValue() as? [Any]
    else {
      return false
    }

    for source in sources {
      guard
        let info = IOPSGetPowerSourceDescription(snapshot, source as CFTypeRef)?.takeUnretainedValue()
          as? [String: Any],
        let currentCapacity = info[kIOPSCurrentCapacityKey] as? Int,
        let maxCapacity = info[kIOPSMaxCapacityKey] as? Int
      else {
        continue
      }
      return isCritical(currentCapacity: currentCapacity, maxCapacity: maxCapacity)
    }

    return false
  }

  /// Pure capacity comparison, split out so the threshold is reviewable without
  /// an IOKit fixture. A non-positive maximum means the report is unusable —
  /// fail open rather than freezing every connector on a bad reading.
  static func isCritical(currentCapacity: Int, maxCapacity: Int) -> Bool {
    guard maxCapacity > 0 else { return false }
    return Double(currentCapacity) / Double(maxCapacity) < criticalBatteryFraction
  }
}
