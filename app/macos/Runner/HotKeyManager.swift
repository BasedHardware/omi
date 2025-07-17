import Cocoa
import SwiftUI
import HotKey
import ApplicationServices

class HotKeyManager: NSObject {
    static let shared = HotKeyManager()
    
    private var hotKey: HotKey?
    private var chatWindow: NSWindow?
    private var hostingController: NSHostingController<ChatView>?
    
    private override init() {
        super.init()
        print("🔥 HotKeyManager: init() called")
        checkAccessibilityPermissions()
        setupHotKey()
        print("🔥 HotKeyManager: initialization complete")
    }
    
    private func checkAccessibilityPermissions() {
        let trusted = AXIsProcessTrusted()
        if !trusted {
            print("⚠️ Accessibility permissions not granted. Requesting permissions...")
            
            // Request accessibility permissions
            let options = [kAXTrustedCheckOptionPrompt.takeUnretainedValue(): true] as CFDictionary
            let isTrusted = AXIsProcessTrustedWithOptions(options)
            
            if !isTrusted {
                print("❌ User needs to grant accessibility permissions in System Preferences")
                showAccessibilityAlert()
            } else {
                print("✅ Accessibility permissions granted")
            }
        } else {
            print("✅ Accessibility permissions already granted")
        }
    }
    
    private func showAccessibilityAlert() {
        DispatchQueue.main.async {
            let alert = NSAlert()
            alert.messageText = "Accessibility Permission Required"
            alert.informativeText = "Omi needs accessibility permission to register global hotkeys (Option+Space). Please:\n\n1. Go to System Preferences → Security & Privacy → Privacy\n2. Select Accessibility from the left panel\n3. Add Omi to the list and enable it\n4. Restart the app"
            alert.alertStyle = .warning
            alert.addButton(withTitle: "Open System Preferences")
            alert.addButton(withTitle: "Later")
            
            let response = alert.runModal()
            if response == .alertFirstButtonReturn {
                NSWorkspace.shared.open(URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility")!)
            }
        }
    }
    
    private func setupHotKey() {
        // Check if we have accessibility permissions before setting up hotkey
        guard AXIsProcessTrusted() else {
            print("❌ Cannot setup hotkey: Accessibility permissions not granted")
            return
        }
        
        // Option + Space hotkey
        hotKey = HotKey(key: .space, modifiers: [.option])
        hotKey?.keyDownHandler = { [weak self] in
            print("🔥 HotKey triggered: Option+Space")
            DispatchQueue.main.async {
                self?.toggleChatWindow()
            }
        }
        print("✅ HotKey manager initialized with Option+Space")
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
        print("🔥 HotKeyManager: initialize() called explicitly")
        // Force recheck permissions and setup
        checkAccessibilityPermissions()
        if hotKey == nil {
            setupHotKey()
        }
    }
    
    func recheckPermissions() {
        // Call this method when app becomes active to recheck permissions
        print("🔥 HotKeyManager: recheckPermissions() called")
        checkAccessibilityPermissions()
        if AXIsProcessTrusted() && hotKey == nil {
            setupHotKey()
        }
    }
}
