import Cocoa
import FlutterMacOS

class FloatingChatButton: NSWindow {
    private static let positionKey = "FloatingChatButtonPosition"
    var onClick: (() -> Void)?

    override init(contentRect: NSRect, styleMask style: NSWindow.StyleMask, backing backingStoreType: NSWindow.BackingStoreType, defer flag: Bool) {
        super.init(contentRect: contentRect, styleMask: [.borderless], backing: .buffered, defer: false)
        
        self.isOpaque = false
        self.backgroundColor = .clear
        self.level = .floating
        self.isMovableByWindowBackground = true
        self.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        self.hasShadow = false
        
        setupButtonView()
        
        if let savedPosition = UserDefaults.standard.string(forKey: FloatingChatButton.positionKey) {
            let origin = NSPointFromString(savedPosition)
            let potentialFrame = NSRect(origin: origin, size: contentRect.size)
            
            var isOnScreen = false
            for screen in NSScreen.screens {
                if screen.visibleFrame.intersects(potentialFrame) {
                    isOnScreen = true
                    break
                }
            }

            if isOnScreen {
                self.setFrameOrigin(origin)
            } else {
                self.center()
            }
        } else {
            self.center()
        }
        
        NotificationCenter.default.addObserver(self, selector: #selector(handleMainWindowFocusChange), name: NSWindow.didBecomeMainNotification, object: nil)
        NotificationCenter.default.addObserver(self, selector: #selector(handleMainWindowFocusChange), name: NSWindow.didResignMainNotification, object: nil)
        NotificationCenter.default.addObserver(self, selector: #selector(windowDidMove), name: NSWindow.didMoveNotification, object: self)
    }
    
    private func setupButtonView() {
        let buttonView: NSView
        if #available(macOS 26.0, *) {
            let glassView = NSGlassEffectView()
            buttonView = glassView
        } else {
            let visualEffectView = NSVisualEffectView()
            visualEffectView.material = .popover
            visualEffectView.blendingMode = .behindWindow
            visualEffectView.state = .active
            buttonView = visualEffectView
        }
        buttonView.wantsLayer = true
        buttonView.layer?.cornerRadius = 18.0
        
        self.contentView = buttonView
        
        let trackingArea = NSTrackingArea(rect: buttonView.bounds, options: [.mouseEnteredAndExited, .activeAlways], owner: self, userInfo: nil)
        buttonView.addTrackingArea(trackingArea)
        
        let clickGesture = NSClickGestureRecognizer(target: self, action: #selector(buttonClicked))
        buttonView.addGestureRecognizer(clickGesture)
        
        let omiLogo = NSView()
        omiLogo.translatesAutoresizingMaskIntoConstraints = false
        omiLogo.wantsLayer = true
        omiLogo.layer?.backgroundColor = NSColor.systemPurple.cgColor
        omiLogo.layer?.cornerRadius = 5
        
        let buttonLabel = NSTextField(labelWithString: "Ask (\u{2318}) (\u{23CE})")
        buttonLabel.translatesAutoresizingMaskIntoConstraints = false
        buttonLabel.textColor = NSColor.labelColor
        buttonLabel.font = NSFont.systemFont(ofSize: 13, weight: .medium)
        
        buttonView.addSubview(omiLogo)
        buttonView.addSubview(buttonLabel)
        
        NSLayoutConstraint.activate([
            omiLogo.leadingAnchor.constraint(equalTo: buttonView.leadingAnchor, constant: 12),
            omiLogo.centerYAnchor.constraint(equalTo: buttonView.centerYAnchor),
            omiLogo.widthAnchor.constraint(equalToConstant: 10),
            omiLogo.heightAnchor.constraint(equalToConstant: 10),
            
            buttonLabel.leadingAnchor.constraint(equalTo: omiLogo.trailingAnchor, constant: 8),
            buttonLabel.trailingAnchor.constraint(equalTo: buttonView.trailingAnchor, constant: -12),
            buttonLabel.centerYAnchor.constraint(equalTo: buttonView.centerYAnchor)
        ])
    }
    
    
    @objc private func buttonClicked() {
        onClick?()
    }

    public func resetPosition() {
        UserDefaults.standard.removeObject(forKey: FloatingChatButton.positionKey)
        self.center()
    }
    
    @objc private func windowDidMove(_ notification: Notification) {
        UserDefaults.standard.set(NSStringFromPoint(self.frame.origin), forKey: FloatingChatButton.positionKey)
    }
    
    @objc private func handleMainWindowFocusChange(notification: Notification) {
        guard let window = notification.object as? NSWindow else { return }

        // We are interested in the main flutter window, not ourselves or other windows.
        let windowClassName = NSStringFromClass(type(of: window))
        if windowClassName == "Runner.MainFlutterWindow" || windowClassName == "MainFlutterWindow" {
            if notification.name == NSWindow.didBecomeMainNotification {
                self.orderOut(nil) // Hide when main window is focused
            } else if notification.name == NSWindow.didResignMainNotification {
                self.orderFront(nil) // Show when main window loses focus
            }
        }
    }
    
    deinit {
        NotificationCenter.default.removeObserver(self)
    }
}
