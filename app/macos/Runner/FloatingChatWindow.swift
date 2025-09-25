import Cocoa
import FlutterMacOS

class FloatingChatWindow: NSWindow, NSWindowDelegate {
    
    let windowId: String
    var onClose: (() -> Void)?
    private var userDefaultsKey: String { "floatingChatWindowFrame_\(windowId)" }
    
    init(id: String, flutterViewController: FlutterViewController) {
        self.windowId = id
        
        let savedFrame = UserDefaults.standard.string(forKey: "floatingChatWindowFrame_\(id)")
        var initialRect: NSRect?
        var centerWindow = false

        if let frameString = savedFrame {
            let savedRect = NSRectFromString(frameString)
            var isOnScreen = false
            for screen in NSScreen.screens {
                if screen.visibleFrame.intersects(savedRect) {
                    isOnScreen = true
                    break
                }
            }
            if isOnScreen {
                initialRect = savedRect
            } else {
                centerWindow = true
            }
        } else {
            centerWindow = true
        }

        if initialRect == nil {
            initialRect = NSRect(x: 0, y: 0, width: 400, height: 600)
        }

        super.init(contentRect: initialRect!, styleMask: [.titled, .closable, .miniaturizable, .resizable], backing: .buffered, defer: false)
        
        if centerWindow {
            self.center()
        }
        self.minSize = NSSize(width: 300, height: 400)
        
        self.isOpaque = false
        self.backgroundColor = .clear
        self.isMovableByWindowBackground = true
        self.level = .floating
        self.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        self.titleVisibility = .hidden
        self.titlebarAppearsTransparent = true
        self.standardWindowButton(.closeButton)?.isHidden = true
        self.standardWindowButton(.miniaturizeButton)?.isHidden = true
        self.standardWindowButton(.zoomButton)?.isHidden = true
        
        // Create a container view controller to hold a native header and the Flutter view
        let containerViewController = NSViewController()
        let mainView = NSView()
        containerViewController.view = mainView
        
        // Create header view
        let headerView = NSView()
        headerView.translatesAutoresizingMaskIntoConstraints = false
        headerView.heightAnchor.constraint(equalToConstant: 30).isActive = true
        
        let visualEffectView: NSView
        if #available(macOS 26.0, *) {
            visualEffectView = NSGlassEffectView()
        } else {
            let effectView = NSVisualEffectView()
            effectView.blendingMode = .behindWindow
            effectView.state = .active
            effectView.material = .titlebar
            visualEffectView = effectView
        }
        visualEffectView.translatesAutoresizingMaskIntoConstraints = false
        headerView.addSubview(visualEffectView, positioned: .below, relativeTo: nil)
        
        // Omi branding label
        let brandLabel = NSTextField(labelWithString: "Omi")
        brandLabel.translatesAutoresizingMaskIntoConstraints = false
        headerView.addSubview(brandLabel)
        
        // Open Main App button
        let openAppButton = NSButton(title: "Open Main App", target: self, action: #selector(openMainAppAction))
        openAppButton.translatesAutoresizingMaskIntoConstraints = false
        headerView.addSubview(openAppButton)
        
        // Flutter view
        let flutterView = flutterViewController.view
        
        // Stack view to hold header and flutter view
        let stackView = NSStackView(views: [headerView, flutterView])
        stackView.orientation = .vertical
        stackView.alignment = .leading
        stackView.spacing = 0
        stackView.translatesAutoresizingMaskIntoConstraints = false
        mainView.addSubview(stackView)
        
        // Add child view controller
        containerViewController.addChild(flutterViewController)
        
        // Layout constraints
        NSLayoutConstraint.activate([
            visualEffectView.topAnchor.constraint(equalTo: headerView.topAnchor),
            visualEffectView.bottomAnchor.constraint(equalTo: headerView.bottomAnchor),
            visualEffectView.leadingAnchor.constraint(equalTo: headerView.leadingAnchor),
            visualEffectView.trailingAnchor.constraint(equalTo: headerView.trailingAnchor),
            
            brandLabel.leadingAnchor.constraint(equalTo: headerView.leadingAnchor, constant: 10),
            brandLabel.centerYAnchor.constraint(equalTo: headerView.centerYAnchor),
            
            openAppButton.trailingAnchor.constraint(equalTo: headerView.trailingAnchor, constant: -10),
            openAppButton.centerYAnchor.constraint(equalTo: headerView.centerYAnchor),
            
            stackView.topAnchor.constraint(equalTo: mainView.topAnchor),
            stackView.bottomAnchor.constraint(equalTo: mainView.bottomAnchor),
            stackView.leadingAnchor.constraint(equalTo: mainView.leadingAnchor),
            stackView.trailingAnchor.constraint(equalTo: mainView.trailingAnchor),
            
            headerView.leadingAnchor.constraint(equalTo: stackView.leadingAnchor),
            headerView.trailingAnchor.constraint(equalTo: stackView.trailingAnchor),
            
            flutterView.leadingAnchor.constraint(equalTo: stackView.leadingAnchor),
            flutterView.trailingAnchor.constraint(equalTo: stackView.trailingAnchor)
        ])
        
        self.contentViewController = containerViewController
        self.delegate = self
    }
    
    func windowWillClose(_ notification: Notification) {
        print("FloatingChatWindow is closing. Cleaning up resources.")
        onClose?()
        saveWindowFrame()
    }
    
    func windowDidResize(_ notification: Notification) {
        saveWindowFrame()
    }
    
    func windowDidMove(_ notification: Notification) {
        saveWindowFrame()
    }
    
    private func saveWindowFrame() {
        let frameString = NSStringFromRect(self.frame)
        UserDefaults.standard.set(frameString, forKey: userDefaultsKey)
    }

    public func resetPosition() {
        UserDefaults.standard.removeObject(forKey: userDefaultsKey)
        self.center()
    }
    
    @objc func openMainAppAction() {
        print("Open Main App button clicked")
        // TODO: Implement opening main app window.
    }
    
    override var canBecomeKey: Bool {
        return true
    }
    
    override var canBecomeMain: Bool {
        return true
    }
    
    override func cancelOperation(_ sender: Any?) {
        self.close()
    }
    
    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }
}
