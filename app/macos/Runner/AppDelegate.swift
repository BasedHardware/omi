import Cocoa
import FlutterMacOS

@main
class AppDelegate: FlutterAppDelegate {
    var floatingControlBar: FloatingControlBar?

    override func applicationDidFinishLaunching(_ aNotification: Notification) {
        super.applicationDidFinishLaunching(aNotification)

        let mainWindow = NSApp.windows.first { $0 is MainFlutterWindow }

        // On subsequent launches via login item, we might want to show only the floating button.
        if LoginItemManager.shared.isEnabled && LoginItemManager.shared.startupBehavior == .showFloatingButton {
            // Hide the main window. It's created by FlutterAppDelegate but we don't want to show it.
            mainWindow?.orderOut(nil)
            showFloatingControlBar()
        } else {
            // This is the default behavior for first launch or if the user prefers it.
            mainWindow?.makeKeyAndOrderFront(nil)
        }
    }

    func showFloatingControlBar() {
        if floatingControlBar == nil {
            let buttonSize = NSSize(width: 280, height: 40)
            floatingControlBar = FloatingControlBar(
                contentRect: NSRect(origin: .zero, size: buttonSize),
                styleMask: [.borderless],
                backing: .buffered,
                defer: false
            )
            FloatingChatWindowManager.shared.floatingButton = floatingControlBar
            floatingControlBar?.onAskAI = { [weak self] in
                FloatingChatWindowManager.shared.showWindow(id: "default")
                // The AppDelegate's button instance must be closed manually.
                self?.floatingControlBar?.close()
                FloatingChatWindowManager.shared.floatingButton = nil
                self?.floatingControlBar = nil
            }
            floatingControlBar?.onMove = {
                FloatingChatWindowManager.shared.positionWindowFromButton()
            }
        }
        floatingControlBar?.makeKeyAndOrderFront(nil)
    }
}
