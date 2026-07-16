import Foundation
@preconcurrency import CoreFoundation
import IOKit.ps

/// Monitors the Mac's power source (battery vs AC) and publishes state changes.
/// Used to adapt capture cadence on battery and trigger legacy OCR backfill when AC reconnects.
@MainActor
class PowerMonitor: ObservableObject {
  static let shared = PowerMonitor()

  nonisolated(unsafe) private static var cachedIsOnBattery = false

  @Published private(set) var isOnBattery: Bool = false

  /// Callback fired when switching from battery → AC power
  var onACReconnected: (() -> Void)?
  var onPowerSourceChanged: ((Bool) -> Void)?

  nonisolated(unsafe) private var runLoopSource: CFRunLoopSource?
  private let batteryStateProbe: @Sendable () -> Bool
  private var powerProbeGeneration: UInt64 = 0

  init(
    batteryStateProbe: @escaping @Sendable () -> Bool = { PowerMonitor.checkBatteryState() },
    startMonitoring: Bool = true
  ) {
    self.batteryStateProbe = batteryStateProbe
    isOnBattery = batteryStateProbe()
    Self.cachedIsOnBattery = isOnBattery
    if startMonitoring {
      startMonitoringPowerSource()
    }
  }

  // MARK: - Power Source Detection

  /// Returns true if the Mac is currently running on battery power
  nonisolated static func checkBatteryState() -> Bool {
    guard let snapshot = IOPSCopyPowerSourcesInfo()?.takeRetainedValue(),
      let sources = IOPSCopyPowerSourcesList(snapshot)?.takeRetainedValue() as? [Any],
      !sources.isEmpty
    else {
      // No power sources = desktop Mac (always on AC)
      return false
    }

    for source in sources {
      if let info = IOPSGetPowerSourceDescription(snapshot, source as CFTypeRef)?.takeUnretainedValue()
        as? [String: Any],
        let powerSource = info[kIOPSPowerSourceStateKey] as? String
      {
        return powerSource == kIOPSBatteryPowerValue
      }
    }

    return false
  }

  /// Last observed power state. This is safe for hot paths where a fresh IOKit probe would be too expensive.
  nonisolated static func cachedBatteryState() -> Bool {
    cachedIsOnBattery
  }

  // MARK: - Monitoring

  private func startMonitoringPowerSource() {
    let context = UnsafeMutableRawPointer(Unmanaged.passUnretained(self).toOpaque())
    if let source = IOPSCreateLimitedPowerNotification(
      { context in
        guard let context = context else { return }
        let monitor = Unmanaged<PowerMonitor>.fromOpaque(context).takeUnretainedValue()
        DispatchQueue.main.async {
          monitor.handlePowerSourceChanged()
        }
      }, context)?.takeRetainedValue()
    {
      runLoopSource = source
      CFRunLoopAddSource(CFRunLoopGetMain(), source, .defaultMode)
      log("PowerMonitor: Started monitoring power source")
    }
  }

  func handlePowerSourceChanged() {
    let wasOnBattery = isOnBattery
    powerProbeGeneration &+= 1
    let generation = powerProbeGeneration
    let batteryStateProbe = batteryStateProbe

    // IOPSCopyPowerSourcesInfo can block on Mach IPC — check off main thread
    Task.detached(priority: .utility) { [weak self] in
      let nowOnBattery = batteryStateProbe()
      guard let self else { return }
      await MainActor.run {
        guard self.powerProbeGeneration == generation else { return }
        self.isOnBattery = nowOnBattery
        Self.cachedIsOnBattery = nowOnBattery

        if wasOnBattery != nowOnBattery {
          log("PowerMonitor: Power source changed — \(nowOnBattery ? "battery" : "AC power")")
          self.onPowerSourceChanged?(nowOnBattery)

          if wasOnBattery && !nowOnBattery {
            // Switched from battery → AC: trigger legacy OCR backfill
            self.onACReconnected?()
          }
        }
      }
    }
  }

  deinit {
    if let source = runLoopSource {
      CFRunLoopRemoveSource(CFRunLoopGetMain(), source, .defaultMode)
    }
  }
}
