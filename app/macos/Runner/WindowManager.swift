import SwiftUI
import AppKit

class WindowManager {
    static func openChatWindow(initialMessage: String) {
        let chatView = ChatView(initialMessage: initialMessage)

        let hostingController = NSHostingController(rootView: chatView)
        let window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 600, height: 500),
            styleMask: [.titled, .closable, .resizable],
            backing: .buffered,
            defer: false
        )
        window.center()
        window.title = "Chat with Omi"
        window.contentView = hostingController.view
        window.makeKeyAndOrderFront(nil)
    }
}
