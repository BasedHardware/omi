import AppKit

@MainActor
final class OmiEscapeMonitor {
    static let shared = OmiEscapeMonitor()
    private var monitor: Any?
    private var onCancel: (() -> Void)?
    private init() {}

    // Global monitor fires even when Omi is in the background (which is always the
    // case during plan execution). Trade-off: global monitors cannot consume events,
    // so ESC also propagates to the frontmost app.
    func arm(onCancel: @escaping () -> Void) {
        // Disarm any existing monitor first (safety)
        disarm()
        self.onCancel = onCancel
        monitor = NSEvent.addGlobalMonitorForEvents(matching: .keyDown) { [weak self] event in
            if event.keyCode == 53 {
                self?.fire()
            }
        }
        log("OmiEscapeMonitor: armed")
    }

    func disarm() {
        if let m = monitor {
            NSEvent.removeMonitor(m)
            monitor = nil
        }
        onCancel = nil
        log("OmiEscapeMonitor: disarmed")
    }

    private func fire() {
        log("OmiEscapeMonitor: Escape pressed — cancelling plan")
        onCancel?()
        disarm()
    }
}
