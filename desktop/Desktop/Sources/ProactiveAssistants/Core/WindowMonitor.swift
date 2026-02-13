import AppKit
import Foundation

/// Observer for NSWorkspace app activation notifications
class WindowMonitor {
    private var observer: NSObjectProtocol?
    private let callback: (String) -> Void

    init(callback: @escaping (String) -> Void) {
        self.callback = callback
    }

    /// Start observing app switches
    func start() {
        observer = NSWorkspace.shared.notificationCenter.addObserver(
            forName: NSWorkspace.didActivateApplicationNotification,
            object: nil,
            queue: .main
        ) { [weak self] notification in
            self?.handleAppActivation(notification)
        }
    }

    /// Stop observing app switches
    func stop() {
        if let observer = observer {
            NSWorkspace.shared.notificationCenter.removeObserver(observer)
            self.observer = nil
        }
    }

    private func handleAppActivation(_ notification: Notification) {
        guard let app = notification.userInfo?[NSWorkspace.applicationUserInfoKey] as? NSRunningApplication,
              let appName = app.localizedName else {
            return
        }
        callback(appName)
    }

    /// Get the name of the frontmost application (static version)
    static func getActiveAppName() -> String? {
        // Refresh run loop to get fresh state
        RunLoop.current.run(until: Date(timeIntervalSinceNow: 0.01))
        return NSWorkspace.shared.frontmostApplication?.localizedName
    }

    /// Get the active app name, window title, and window ID (static version)
    static func getActiveWindowInfoStatic() -> (appName: String?, windowTitle: String?, windowID: CGWindowID?) {
        return ScreenCaptureService.getActiveWindowInfo()
    }

    /// Instance method for getting active window info
    func getActiveWindowInfo() -> (appName: String?, windowTitle: String?, windowID: CGWindowID?) {
        return Self.getActiveWindowInfoStatic()
    }

    deinit {
        stop()
    }
}
