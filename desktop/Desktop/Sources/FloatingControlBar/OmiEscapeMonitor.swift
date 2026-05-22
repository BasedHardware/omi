import AppKit

@MainActor
final class OmiEscapeMonitor {
    static let shared = OmiEscapeMonitor()
    private var monitor: Any?
    private var onCancel: (() -> Void)?
    private init() {}

    func arm(onCancel: @escaping () -> Void) {
        // Disarm any existing monitor first (safety)
        disarm()
        self.onCancel = onCancel
        monitor = NSEvent.addLocalMonitorForEvents(matching: .keyDown) { [weak self] event in
            // Escape keyCode is 53
            if event.keyCode == 53 {
                self?.fire()
                return nil  // consume the event
            }
            return event
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
