import UIKit

/// Manages proximity sensor during phone calls.
/// Turns screen off when held to ear, re-enables idle timer when moved away.
final class OmiProximitySensor {
    private var observer: NSObjectProtocol?

    func enable() {
        DispatchQueue.main.async {
            UIDevice.current.isProximityMonitoringEnabled = true
        }
        observer = NotificationCenter.default.addObserver(
            forName: UIDevice.proximityStateDidChangeNotification,
            object: nil, queue: nil
        ) { _ in
            DispatchQueue.main.async {
                // When near ear: keep screen on (but proximity dims it)
                // When away: allow normal idle timer behavior
                UIApplication.shared.isIdleTimerDisabled = UIDevice.current.proximityState
            }
        }
    }

    func disable() {
        if let observer = observer {
            NotificationCenter.default.removeObserver(observer)
            self.observer = nil
        }
        DispatchQueue.main.async {
            UIDevice.current.isProximityMonitoringEnabled = false
            UIApplication.shared.isIdleTimerDisabled = false
        }
    }

    deinit {
        disable()
    }
}
