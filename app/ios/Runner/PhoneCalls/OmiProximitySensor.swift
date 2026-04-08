import UIKit

/// Manages proximity sensor during phone calls.
/// Matches Granola's implementation: uses @MainActor for all UI updates.
final class OmiProximitySensor {
    private var observer: NSObjectProtocol?

    func enable() {
        Task { @MainActor in
            UIDevice.current.isProximityMonitoringEnabled = true
        }

        observer = NotificationCenter.default.addObserver(
            forName: UIDevice.proximityStateDidChangeNotification,
            object: nil,
            queue: nil
        ) { [weak self] _ in
            Task { @MainActor in
                self?.updateScreenForProximity()
            }
        }
    }

    func disable() {
        if let observer = observer {
            NotificationCenter.default.removeObserver(observer)
            self.observer = nil
        }

        Task { @MainActor in
            UIDevice.current.isProximityMonitoringEnabled = false
            UIApplication.shared.isIdleTimerDisabled = false
        }
    }

    @MainActor
    private func updateScreenForProximity() {
        let proximityState = UIDevice.current.proximityState

        if proximityState {
            UIApplication.shared.isIdleTimerDisabled = true
        } else {
            UIApplication.shared.isIdleTimerDisabled = false
        }
    }

    deinit {
        if let observer = observer {
            NotificationCenter.default.removeObserver(observer)
        }
    }
}
