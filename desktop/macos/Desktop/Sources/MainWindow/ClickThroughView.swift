import SwiftUI
import AppKit

/// Custom NSHostingView that accepts first mouse events for click-through behavior.
class ClickThroughHostingView<Content: View>: NSHostingView<Content> {
    private var pendingClickLocation: NSPoint?
    private var wasWindowKey: Bool = false
    private var localMonitor: Any?
    private var isProcessingSyntheticClick: Bool = false  // Guard against re-entry

    /// When false, the view is transparent to AppKit hit testing (returns nil from hitTest).
    /// This prevents the NSView from intercepting clicks meant for overlapping SwiftUI views.
    var isClickThroughEnabled: Bool = true

    override func acceptsFirstMouse(for event: NSEvent?) -> Bool {
        return isClickThroughEnabled
    }

    override func hitTest(_ point: NSPoint) -> NSView? {
        guard isClickThroughEnabled else { return nil }
        return super.hitTest(point)
    }

    override func viewDidMoveToWindow() {
        super.viewDidMoveToWindow()

        // Remove existing monitor if any
        if let monitor = localMonitor {
            NSEvent.removeMonitor(monitor)
            localMonitor = nil
        }

        guard let window = self.window else { return }

        // Track window key status changes to detect activation clicks
        NotificationCenter.default.addObserver(
            self,
            selector: #selector(windowDidBecomeKey),
            name: NSWindow.didBecomeKeyNotification,
            object: window
        )

        // Monitor left mouse down events
        localMonitor = NSEvent.addLocalMonitorForEvents(matching: .leftMouseDown) { [weak self] event in
            guard let self = self, let window = self.window else { return event }

            // Skip if we're processing a synthetic click (prevent re-entry loop)
            guard !self.isProcessingSyntheticClick else { return event }

            // CRITICAL: Only capture events that are actually for OUR window, not sheets or other windows
            // event.window is the window where the click occurred
            guard event.window == window else {
                log("CLICKTHROUGH: Ignoring click from different window (event.window=\(String(describing: event.window?.className)), our window=\(window.className))")
                return event
            }

            // Skip capture when click-through is disabled (e.g., sidebar hidden behind settings)
            guard self.isClickThroughEnabled else { return event }

            // If clicking in our view while window is not key, save the location
            if !window.isKeyWindow {
                let locationInView = self.convert(event.locationInWindow, from: nil)
                if self.bounds.contains(locationInView) {
                    log("CLICKTHROUGH: Captured pending click at \(event.locationInWindow) in view bounds")
                    self.pendingClickLocation = event.locationInWindow
                    self.wasWindowKey = false
                }
            }
            return event
        }
    }

    @objc private func windowDidBecomeKey(_ notification: Notification) {
        // If we have a pending click from when the window wasn't key, re-send it
        guard let location = pendingClickLocation,
              !wasWindowKey,
              self.window != nil else {
            if pendingClickLocation != nil {
                log("CLICKTHROUGH: windowDidBecomeKey - clearing pending click (wasWindowKey=\(wasWindowKey))")
            }
            pendingClickLocation = nil
            return
        }

        log("CLICKTHROUGH: windowDidBecomeKey - has pending click at \(location)")

        // Check if a sheet was just dismissed - if so, don't process the pending click
        // This prevents click-through when dismissing modals/sheets
        if let keyWindow = NSApp.keyWindow,
           keyWindow.className.contains("Sheet") || NSApp.windows.contains(where: { $0.isSheet && $0.isVisible }) {
            log("CLICKTHROUGH: Sheet detected, ignoring pending click")
            pendingClickLocation = nil
            wasWindowKey = true
            return
        }

        wasWindowKey = true
        pendingClickLocation = nil

        // Small delay to let the window fully activate
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.01) { [weak self] in
            guard let self = self, let window = self.window else { return }

            // Find the view at the click location and simulate a click
            let locationInView = self.convert(location, from: nil)
            guard self.bounds.contains(locationInView) else { return }

            // Set guard before posting synthetic events
            self.isProcessingSyntheticClick = true

            // Use NSEvent + window.sendEvent() instead of CGEvent.post()
            // CGEvent.post(mouseCursorPosition:) physically moves the cursor, causing the jump bug
            log("CLICKTHROUGH: Sending synthetic click at window position \(location)")
            if let syntheticEvent = NSEvent.mouseEvent(
                with: .leftMouseDown,
                location: location,
                modifierFlags: [],
                timestamp: ProcessInfo.processInfo.systemUptime,
                windowNumber: window.windowNumber,
                context: nil,
                eventNumber: 0,
                clickCount: 1,
                pressure: 1.0
            ) {
                window.sendEvent(syntheticEvent)

                // Also send mouse up
                if let upEvent = NSEvent.mouseEvent(
                    with: .leftMouseUp,
                    location: location,
                    modifierFlags: [],
                    timestamp: ProcessInfo.processInfo.systemUptime,
                    windowNumber: window.windowNumber,
                    context: nil,
                    eventNumber: 0,
                    clickCount: 1,
                    pressure: 0.0
                ) {
                    window.sendEvent(upEvent)
                }
            }

            self.isProcessingSyntheticClick = false
        }
    }

    deinit {
        if let monitor = localMonitor {
            NSEvent.removeMonitor(monitor)
        }
        NotificationCenter.default.removeObserver(self)
    }
}

/// A view wrapper that enables click-through behavior on macOS.
/// Uses a fixed width to preserve sidebar sizing.
struct ClickThroughView<Content: View>: NSViewRepresentable {
    let content: Content
    let width: CGFloat?
    let enabled: Bool

    init(width: CGFloat? = nil, enabled: Bool = true, @ViewBuilder content: () -> Content) {
        self.width = width
        self.enabled = enabled
        self.content = content()
    }

    func makeNSView(context: Context) -> ClickThroughHostingView<Content> {
        let hostingView = ClickThroughHostingView(rootView: content)
        hostingView.isClickThroughEnabled = enabled
        // Don't constrain the hosting view size - let it use intrinsic size
        hostingView.setContentHuggingPriority(.defaultHigh, for: .horizontal)
        hostingView.setContentHuggingPriority(.defaultLow, for: .vertical)
        return hostingView
    }

    func updateNSView(_ nsView: ClickThroughHostingView<Content>, context: Context) {
        nsView.rootView = content
        nsView.isClickThroughEnabled = enabled
    }
}

// MARK: - View Extension for convenience
extension View {
    /// Wraps this view to enable click-through behavior.
    /// The view will maintain its intrinsic size.
    func clickThrough(enabled: Bool = true) -> some View {
        ClickThroughView(enabled: enabled) { self }
            .fixedSize(horizontal: true, vertical: false)
    }
}
