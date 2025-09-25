import Cocoa
import FlutterMacOS

@main
class AppDelegate: FlutterAppDelegate {
    var floatingChatButton: FloatingChatButton?

    override func applicationDidFinishLaunching(_ aNotification: Notification) {
        super.applicationDidFinishLaunching(aNotification)

        let mainWindow = NSApp.windows.first { $0 is MainFlutterWindow }

        // On subsequent launches via login item, we might want to show only the floating button.
        if LoginItemManager.shared.isEnabled && LoginItemManager.shared.startupBehavior == .showFloatingButton {
            // Hide the main window. It's created by FlutterAppDelegate but we don't want to show it.
            mainWindow?.orderOut(nil)
            showFloatingChatButton()
        } else {
            // This is the default behavior for first launch or if the user prefers it.
            mainWindow?.makeKeyAndOrderFront(nil)
        }
    }

    func showFloatingChatButton() {
        if floatingChatButton == nil {
            let buttonSize = NSSize(width: 150, height: 36)
            floatingChatButton = FloatingChatButton(
                contentRect: NSRect(origin: .zero, size: buttonSize),
                styleMask: [.borderless],
                backing: .buffered,
                defer: false
            )
            floatingChatButton?.onClick = { [weak self] in
                FloatingChatWindowManager.shared.showWindow(id: "default")
                // The AppDelegate's button instance must be closed manually.
                self?.floatingChatButton?.close()
                self?.floatingChatButton = nil
            }
        }
        floatingChatButton?.makeKeyAndOrderFront(nil)
    }

    override func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        if !flag {
            let mainWindow = NSApp.windows.first { $0 is MainFlutterWindow }
            mainWindow?.makeKeyAndOrderFront(nil)
        }
        return true
    }

    override func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        return true
    }
  
    override func applicationSupportsSecureRestorableState(_ app: NSApplication) -> Bool {
        return true
    }
}
