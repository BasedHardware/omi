import Foundation
import IOKit.ps

/// Monitors the Mac's power source (battery vs AC) and publishes state changes.
/// Used to pause OCR when on battery and trigger backfill when AC reconnects.
@MainActor
class PowerMonitor: ObservableObject {
    static let shared = PowerMonitor()

    @Published private(set) var isOnBattery: Bool = false

    /// Callback fired when switching from battery → AC power
    var onACReconnected: (() -> Void)?

    private var runLoopSource: CFRunLoopSource?

    private init() {
        isOnBattery = Self.checkBatteryState()
        startMonitoring()
    }

    // MARK: - Power Source Detection

    /// Returns true if the Mac is currently running on battery power
    nonisolated static func checkBatteryState() -> Bool {
        guard let snapshot = IOPSCopyPowerSourcesInfo()?.takeRetainedValue(),
              let sources = IOPSCopyPowerSourcesList(snapshot)?.takeRetainedValue() as? [Any],
              !sources.isEmpty else {
            // No power sources = desktop Mac (always on AC)
            return false
        }

        for source in sources {
            if let info = IOPSGetPowerSourceDescription(snapshot, source as CFTypeRef)?.takeUnretainedValue() as? [String: Any],
               let powerSource = info[kIOPSPowerSourceStateKey] as? String {
                return powerSource == kIOPSBatteryPowerValue
            }
        }

        return false
    }

    // MARK: - Monitoring

    private func startMonitoring() {
        let context = UnsafeMutableRawPointer(Unmanaged.passUnretained(self).toOpaque())
        if let source = IOPSCreateLimitedPowerNotification({ context in
            guard let context = context else { return }
            let monitor = Unmanaged<PowerMonitor>.fromOpaque(context).takeUnretainedValue()
            DispatchQueue.main.async {
                monitor.handlePowerSourceChanged()
            }
        }, context)?.takeRetainedValue() {
            runLoopSource = source
            CFRunLoopAddSource(CFRunLoopGetMain(), source, .defaultMode)
            log("PowerMonitor: Started monitoring power source")
        }
    }

    private func handlePowerSourceChanged() {
        let wasOnBattery = isOnBattery
        isOnBattery = Self.checkBatteryState()

        if wasOnBattery != isOnBattery {
            log("PowerMonitor: Power source changed — \(isOnBattery ? "battery" : "AC power")")

            if wasOnBattery && !isOnBattery {
                // Switched from battery → AC: trigger OCR backfill
                onACReconnected?()
            }
        }
    }

    deinit {
        if let source = runLoopSource {
            CFRunLoopRemoveSource(CFRunLoopGetMain(), source, .defaultMode)
        }
    }
}
