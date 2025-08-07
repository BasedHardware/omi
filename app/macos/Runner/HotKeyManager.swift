import Cocoa
import SwiftUI
import HotKey
import ApplicationServices

// Custom NSWindow that can become key window to accept input
class KeyableWindow: NSWindow {
    override var canBecomeKey: Bool {
        return true
    }
    
    override var canBecomeMain: Bool {
        return false  // Don't become main to avoid stealing focus from other apps
    }
    
    func acceptsFirstMouse(for event: NSEvent?) -> Bool {
        return true
    }
}

class HotKeyManager: NSObject {
    static let shared = HotKeyManager()
    
    private var hotKey: HotKey?
    private var chatWindow: NSWindow?
    private var hostingController: NSHostingController<VoiceAssistantPopup>?
    
    private override init() {
        super.init()
        print("🔥 HotKeyManager: singleton init() called")
        // Don't setup hotkey in init - wait for explicit initialize() call
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
        
        print("🔥 Setting up hotkey with Option+Space...")
        
        // Option + Space hotkey
        hotKey = HotKey(key: .space, modifiers: [.option])
        
        print("🔥 HotKey object created: \(String(describing: hotKey))")
        
        hotKey?.keyDownHandler = { [weak self] in
            print("🔥 HotKey triggered: Option+Space")
            guard let self = self else {
                print("❌ HotKeyManager instance is nil")
                return
            }
            DispatchQueue.main.async {
                self.toggleChatWindow()
            }
        }
        print("✅ HotKey manager initialized with Option+Space")
        print("🔥 HotKey keyCombo: \(String(describing: hotKey?.keyCombo))")
    }
    
    func toggleChatWindow() {
        print("🔥 toggleChatWindow() called")
        
        if let window = chatWindow, window.isVisible {
            print("🔥 Window is visible, hiding it")
            hideChatWindow()
        } else {
            print("🔥 Window is not visible, showing it")
            showChatWindow()
        }
    }
    
    private func showChatWindow() {
    print("🔥 showChatWindow() called")
    
    // If window already exists and is visible, just bring it to front
    if let window = chatWindow, window.isVisible {
        window.makeKeyAndOrderFront(nil)
        // Focus on the text field
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.1) {
            window.makeFirstResponder(nil)
        }
        return
    }
    
    // Create the SwiftUI view - now using VoiceAssistantPopup
    let voiceAssistantPopup = VoiceAssistantPopup()
    hostingController = NSHostingController(rootView: voiceAssistantPopup)

    // Window size and position
    let initialWindowSize = CGSize(width: 420, height: 300) // Slightly larger for voice popup
    
    // Use visibleFrame for accurate positioning that accounts for Dock and menu bar
    guard let screen = NSScreen.main else {
        print("❌ Could not get main screen")
        return
    }
    
    let visibleFrame = screen.visibleFrame
    let originX = visibleFrame.origin.x + (visibleFrame.width - initialWindowSize.width) / 2
    let originY = visibleFrame.origin.y - 10 // Just above Dock
    
    let windowRect = NSRect(
        x: originX,
        y: originY,
        width: initialWindowSize.width,
        height: initialWindowSize.height
    )

    // Create the floating window with proper style mask
    chatWindow = KeyableWindow(
        contentRect: windowRect,
        styleMask: [.borderless],
        backing: .buffered,
        defer: false
    )

    guard let chatWindow = chatWindow,
          let hostingView = hostingController?.view else { 
        print("❌ Failed to create chat window or hosting view")
        return 
    }

    // Configure window properties for overlay
    chatWindow.isOpaque = false
    chatWindow.backgroundColor = .clear
    chatWindow.level = .floating
    chatWindow.isMovableByWindowBackground = true
    chatWindow.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .ignoresCycle]
    chatWindow.hasShadow = true
    chatWindow.isReleasedWhenClosed = false // Important: prevent window from being deallocated
    
    // Make window accept mouse events
    chatWindow.acceptsMouseMovedEvents = true

    // Create a NSVisualEffectView (glass background)
    let visualEffectView = NSVisualEffectView()
    visualEffectView.material = .hudWindow
    visualEffectView.blendingMode = .behindWindow
    visualEffectView.state = .active
    visualEffectView.translatesAutoresizingMaskIntoConstraints = false

    // SwiftUI hosting view
    hostingView.translatesAutoresizingMaskIntoConstraints = false

    // Container view with rounded corners
    let containerView = NSView()
    containerView.wantsLayer = true
    containerView.layer?.cornerRadius = 24
    containerView.layer?.masksToBounds = true
    containerView.translatesAutoresizingMaskIntoConstraints = false

    containerView.addSubview(visualEffectView)
    containerView.addSubview(hostingView)

    // Constraints for both subviews to fill the container
    NSLayoutConstraint.activate([
        visualEffectView.topAnchor.constraint(equalTo: containerView.topAnchor),
        visualEffectView.bottomAnchor.constraint(equalTo: containerView.bottomAnchor),
        visualEffectView.leadingAnchor.constraint(equalTo: containerView.leadingAnchor),
        visualEffectView.trailingAnchor.constraint(equalTo: containerView.trailingAnchor),

        hostingView.topAnchor.constraint(equalTo: containerView.topAnchor),
        hostingView.bottomAnchor.constraint(equalTo: containerView.bottomAnchor),
        hostingView.leadingAnchor.constraint(equalTo: containerView.leadingAnchor),
        hostingView.trailingAnchor.constraint(equalTo: containerView.trailingAnchor),
    ])

    // Set container as the window's content view
    chatWindow.contentView = containerView

    // Show the window and make it key to accept input
    chatWindow.makeKeyAndOrderFront(nil)
    
    // Focus on the text field (if possible)
    DispatchQueue.main.asyncAfter(deadline: .now() + 0.1) {
        chatWindow.makeFirstResponder(nil)
    }
    
    print("✅ Chat window shown with glass style")
}

    
    private func hideChatWindow() {
        print("🔥 hideChatWindow() called")
        if let window = chatWindow {
            window.orderOut(nil)
            // Don't set chatWindow to nil immediately - keep it for reuse
            print("✅ Chat window hidden")
        }
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
