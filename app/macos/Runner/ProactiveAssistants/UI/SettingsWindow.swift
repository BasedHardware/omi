import Cocoa
import SwiftUI

/// NSWindow subclass that hosts the Proactive Assistants Settings SwiftUI view
class SettingsWindow: NSWindow {
    private static var sharedWindow: SettingsWindow?

    /// Shows the settings window, creating it if necessary
    static func show() {
        if let existingWindow = sharedWindow {
            existingWindow.makeKeyAndOrderFront(nil)
            NSApp.activate(ignoringOtherApps: true)
            return
        }

        let window = SettingsWindow()
        sharedWindow = window
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    /// Closes the settings window
    static func close() {
        sharedWindow?.close()
        sharedWindow = nil
    }

    private init() {
        // Initial size will be adjusted after hosting view is set
        let contentRect = NSRect(x: 0, y: 0, width: 420, height: 100)

        super.init(
            contentRect: contentRect,
            styleMask: [.titled, .closable, .miniaturizable],
            backing: .buffered,
            defer: false
        )

        self.title = "Proactive Assistant Settings"
        self.isReleasedWhenClosed = false
        self.delegate = self

        // Create SwiftUI view
        let settingsView = SettingsView(onClose: { [weak self] in
            self?.close()
        })

        let hostingView = NSHostingView(rootView: settingsView)
        self.contentView = hostingView

        // Resize window to fit content
        let fittingSize = hostingView.fittingSize
        self.setContentSize(fittingSize)

        // Center on screen after sizing
        self.center()
    }
}

// MARK: - NSWindowDelegate

extension SettingsWindow: NSWindowDelegate {
    func windowWillClose(_ notification: Notification) {
        SettingsWindow.sharedWindow = nil
    }
}

// MARK: - Backward Compatibility Alias

typealias FocusSettingsWindow = SettingsWindow
