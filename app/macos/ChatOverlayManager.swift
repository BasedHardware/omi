import Cocoa
import SwiftUI

// mark: - swiftui content view
struct HelloWorldView: View {
    var body: some View {
        VStack {
            Text("Hello World")
                .font(.title2)
                .fontWeight(.medium)
                .foregroundColor(.primary)
            
            Text("Option + Space POC")
                .font(.caption)
                .foregroundColor(.secondary)
        }
        .padding(20)
        .background(
            RoundedRectangle(cornerRadius: 12)
                .fill(Color(NSColor.controlBackgroundColor))
                .shadow(radius: 8)
        )
        .frame(minWidth: 200, minHeight: 100)
    }
}

// mark: - chat overlay manager
class ChatOverlayManager: NSObject {
    
    // mark: - properties
    private var popupWindow: NSWindow?
    private var localEventMonitor: Any?
    
    // mark: - public methods
    func showPopup() {
        // don't create multiple windows
        if popupWindow != nil {
            return
        }
        
        // create the popup window
        createPopupWindow()
        
        // center and show the window
        centerAndShowWindow()
        
        // set up dismissal handlers
        setupDismissalHandlers()
    }
    
    func hidePopup() {
        guard let window = popupWindow else { return }
        
        // remove event monitors
        if let monitor = localEventMonitor {
            NSEvent.removeMonitor(monitor)
            localEventMonitor = nil
        }
        
        // close and cleanup window
        window.close()
        popupWindow = nil
        
        print("DEBUG: Popup hidden")
    }
    
    func isPopupVisible() -> Bool {
        return popupWindow != nil && popupWindow?.isVisible == true
    }
    
    func cleanup() {
        hidePopup()
    }
    
    // mark: - private methods
    private func createPopupWindow() {
        // create swiftui hosting view
        let contentView = HelloWorldView()
        let hostingView = NSHostingView(rootView: contentView)
        
        // calculate window size based on content
        let windowSize = NSSize(width: 240, height: 140)
        
        // create borderless window
        popupWindow = NSWindow(
            contentRect: NSRect(origin: .zero, size: windowSize),
            styleMask: [.borderless],
            backing: .buffered,
            defer: false
        )
        
        guard let window = popupWindow else { return }
        
        // configure window properties
        window.contentView = hostingView
        window.backgroundColor = NSColor.clear
        window.isOpaque = false
        window.level = .floating
        window.isMovableByWindowBackground = true
        window.hasShadow = true
        window.ignoresMouseEvents = false
        
        // make window non-modal but focusable
        // note: canbecomekey and canbecomemain are read-only properties
        // window behavior is controlled by window level and style mask
        
        print("DEBUG: Popup window created")
    }
    
    private func centerAndShowWindow() {
        guard let window = popupWindow else { return }
        
        // center on main screen
        if let screen = NSScreen.main {
            let screenRect = screen.visibleFrame
            let windowRect = window.frame
            
            let newOrigin = NSPoint(
                x: screenRect.midX - windowRect.width / 2,
                y: screenRect.midY - windowRect.height / 2
            )
            
            window.setFrameOrigin(newOrigin)
        }
        
        // show the window
        window.makeKeyAndOrderFront(nil)
        window.orderFrontRegardless()
        
        print("DEBUG: Popup window shown and centered")
    }
    
    private func setupDismissalHandlers() {
        guard let window = popupWindow else { return }
        
        // monitor for escape key and clicks outside
        localEventMonitor = NSEvent.addLocalMonitorForEvents(matching: [.keyDown, .leftMouseDown, .rightMouseDown]) { [weak self] event in
            guard let self = self else { return event }
            
            switch event.type {
            case .keyDown:
                // check for escape key (keycode 53)
                if event.keyCode == 53 {
                    print("DEBUG: Escape key pressed, hiding popup")
                    self.hidePopup()
                    return nil // consume the event
                }
                
            case .leftMouseDown, .rightMouseDown:
                // check if click is outside the popup window
                if let clickWindow = event.window, clickWindow != window {
                    print("DEBUG: Click outside popup detected, hiding popup")
                    self.hidePopup()
                }
                
            default:
                break
            }
            
            return event
        }
        
        // also handle window deactivation
        NotificationCenter.default.addObserver(
            forName: NSWindow.didResignKeyNotification,
            object: window,
            queue: .main
        ) { [weak self] _ in
            // add small delay to prevent immediate dismissal when showing
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.1) {
                self?.hidePopup()
            }
        }
    }
    
    // mark: - deinitialization
    deinit {
        cleanup()
    }
} 