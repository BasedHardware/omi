import Cocoa
import FlutterMacOS

/// Manages the lifecycle of multiple floating chat windows.
class FloatingChatWindowManager: NSObject, NSWindowDelegate {
    static let shared = FloatingChatWindowManager()

    private var chatWindows: [String: FloatingChatWindow] = [:]
    private weak var flutterEngine: FlutterEngine?

    private override init() {}

    /// Configures the manager with the main Flutter engine.
    func configure(flutterEngine: FlutterEngine) {
        self.flutterEngine = flutterEngine
    }

    /// Creates and shows a new chat window or brings an existing one to the front.
    func showWindow(id: String) {
        DispatchQueue.main.async {
            if let window = self.chatWindows[id] {
                window.makeKeyAndOrderFront(nil)
                NSApp.activate(ignoringOtherApps: true)
                return
            }

            guard let engine = self.flutterEngine else {
                print("Error: FloatingChatWindowManager has not been configured with a FlutterEngine.")
                return
            }

            let flutterViewController = FlutterViewController(engine: engine, nibName: nil, bundle: nil)
            
            // TODO: Send window ID to Flutter via method channel on the new controller.

            let window = FloatingChatWindow(id: id, flutterViewController: flutterViewController)
            
            window.delegate = self

            self.chatWindows[id] = window
            window.makeKeyAndOrderFront(nil)
            NSApp.activate(ignoringOtherApps: true)
        }
    }

    /// Closes and removes a chat window from management.
    func closeWindow(id: String) {
        DispatchQueue.main.async {
            if let window = self.chatWindows.removeValue(forKey: id) {
                window.close()
            }
        }
    }
    
    func resetAllPositions() {
        DispatchQueue.main.async {
            for (_, window) in self.chatWindows {
                window.resetPosition()
            }
        }
    }
    
    // MARK: - NSWindowDelegate
    
    func windowWillClose(_ notification: Notification) {
        guard let window = notification.object as? NSWindow else { return }
        
        // Find the ID for this window and remove it from our tracking dictionary.
        if let (id, _) = chatWindows.first(where: { $0.value == window }) {
            chatWindows.removeValue(forKey: id)
            print("DEBUG: Closed and removed chat window with id \(id)")
        }
    }
}
