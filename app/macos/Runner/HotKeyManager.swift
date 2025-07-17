import Cocoa
import SwiftUI
import HotKey

class HotKeyManager: NSObject {
    static let shared = HotKeyManager()
    
    private var hotKey: HotKey?
    private var chatWindow: NSWindow?
    private var hostingController: NSHostingController<ChatView>?
    
    private override init() {
        super.init()
        setupHotKey()
    }
    
    private func setupHotKey() {
        // Option + Space hotkey
        hotKey = HotKey(key: .space, modifiers: [.option])
        hotKey?.keyDownHandler = { [weak self] in
            DispatchQueue.main.async {
                self?.toggleChatWindow()
            }
        }
        print("HotKey manager initialized with Option+Space")
    }
    
    func toggleChatWindow() {
        if chatWindow?.isVisible == true {
            hideChatWindow()
        } else {
            showChatWindow()
        }
    }
    
    private func showChatWindow() {
        // Create the SwiftUI view
        let chatView = ChatView()
        hostingController = NSHostingController(rootView: chatView)
        
        // Calculate window position (center of main screen)
        let screenSize = NSScreen.main?.frame.size ?? CGSize(width: 1920, height: 1080)
        let initialWindowSize = CGSize(width: 420, height: 100)
        let windowRect = NSRect(
            x: (screenSize.width - initialWindowSize.width) / 2,
            y: (screenSize.height - initialWindowSize.height) / 2,
            width: initialWindowSize.width,
            height: initialWindowSize.height
        )
        
        // Create window with floating style
        chatWindow = NSWindow(
            contentRect: windowRect,
            styleMask: [.titled, .fullSizeContentView, .resizable],
            backing: .buffered,
            defer: false
        )
        
        // Configure window appearance
        chatWindow?.isOpaque = false
        chatWindow?.backgroundColor = .clear
        chatWindow?.level = .floating
        chatWindow?.titleVisibility = .hidden
        chatWindow?.titlebarAppearsTransparent = true
        chatWindow?.isMovableByWindowBackground = true
        chatWindow?.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        
        // Set minimum and maximum sizes
        chatWindow?.minSize = CGSize(width: 320, height: 80)
        chatWindow?.maxSize = CGSize(width: 600, height: 400)
        
        // Set content
        chatWindow?.contentView = hostingController?.view
        
        // Show window
        chatWindow?.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        
        print("Chat window shown")
    }
    
    private func hideChatWindow() {
        chatWindow?.orderOut(nil)
        chatWindow = nil
        hostingController = nil
        print("Chat window hidden")
    }
    
    func cleanup() {
        hideChatWindow()
        hotKey = nil
        print("HotKey manager cleaned up")
    }
}

// Extension to make HotKeyManager accessible from AppDelegate
extension HotKeyManager {
    func initialize() {
        // This method can be called from AppDelegate to ensure initialization
        print("HotKeyManager explicitly initialized")
    }
}
