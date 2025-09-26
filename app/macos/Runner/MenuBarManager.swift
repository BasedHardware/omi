import Cocoa

// MARK: - Menu Bar Manager
class MenuBarManager: NSObject {
    
    // MARK: - Properties
    private var statusBarItem: NSStatusItem?
    private weak var mainWindow: NSWindow?
    private var isFloatingChatButtonVisible: Bool = false
    
    // Callbacks for menu actions
    var onToggleWindow: (() -> Void)?
    var onToggleFloatingChat: (() -> Void)?
    var onOpenChatWindow: (() -> Void)?
    var onQuit: (() -> Void)?
    
    // MARK: - Initialization
    init(mainWindow: NSWindow) {
        self.mainWindow = mainWindow
        super.init()
        NotificationCenter.default.addObserver(
            self,
            selector: #selector(updateChatWindowStatus),
            name: FloatingChatWindowManager.windowCountChangedNotification,
            object: nil
        )
    }
    
    // MARK: - Setup
    func setupMenuBarItem() {
        // Create status bar item
        statusBarItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.squareLength)
        
        guard let statusBarItem = statusBarItem else {
            print("ERROR: Failed to create status bar item")
            return
        }
        
        // Set up the button with custom icon
        if let button = statusBarItem.button {
            // Load custom icon from assets
            if let customIcon = NSImage(named: "app_launcher_icon") {
                customIcon.isTemplate = true  // Make it adapt to dark/light mode
                customIcon.size = NSSize(width: 18, height: 18)  // Appropriate menu bar size
                button.image = customIcon
            } else {
                // Fallback to system icon if custom icon fails to load
                button.image = NSImage(systemSymbolName: "mic.circle", accessibilityDescription: "Omi")
                print("WARNING: Could not load custom app_launcher_icon, using fallback")
            }
            button.toolTip = "Omi - Always On AI"
        }
        
        // Create menu
        let menu = NSMenu()
        
        // Show/Hide Window item
        let showHideItem = NSMenuItem(title: getWindowToggleTitle(), action: #selector(toggleWindowVisibility), keyEquivalent: "")
        showHideItem.target = self
        menu.addItem(showHideItem)
        
        menu.addItem(NSMenuItem.separator())
        
        // Floating Chat Controls
        let showHideFloatingChatItem = NSMenuItem(title: "Show/Hide Floating Chat ⌘\\", action: #selector(toggleFloatingChat), keyEquivalent: "\\")
        showHideFloatingChatItem.target = self
        showHideFloatingChatItem.tag = 200
        menu.addItem(showHideFloatingChatItem)
        
        let openChatWindowItem = NSMenuItem(title: "Open Chat Window ⌘↩", action: #selector(openChatWindow), keyEquivalent: "")
        openChatWindowItem.target = self
        openChatWindowItem.tag = 201
        menu.addItem(openChatWindowItem)
        
        let chatStatusItem = NSMenuItem(title: "No Chat Windows Open", action: nil, keyEquivalent: "")
        chatStatusItem.tag = 202
        chatStatusItem.isEnabled = false
        menu.addItem(chatStatusItem)
        
        menu.addItem(NSMenuItem.separator())
        
        // Status item
        let statusItem = NSMenuItem(title: "Status: Ready", action: nil, keyEquivalent: "")
        statusItem.tag = 100
        menu.addItem(statusItem)
        
        menu.addItem(NSMenuItem.separator())
        
        // Quit item
        let quitItem = NSMenuItem(title: "Quit Omi", action: #selector(quitApplication), keyEquivalent: "q")
        quitItem.target = self
        menu.addItem(quitItem)
        
        statusBarItem.menu = menu
        
        print("INFO: Menu bar item created successfully")
    }
    
    // MARK: - Public Methods
    
    func updateFloatingChatButtonVisibility(isVisible: Bool) {
        isFloatingChatButtonVisible = isVisible
        updateFloatingChatMenuItemState()
    }
    
    func updateStatus(status: String, isActive: Bool = false) {
        guard let menu = statusBarItem?.menu,
              let statusItem = menu.item(withTag: 100) else { return }
        
        statusItem.title = "Status: \(status)"
        
        // Update icon based on state
        if let button = statusBarItem?.button {
            if let customIcon = NSImage(named: "app_launcher_icon") {
                customIcon.isTemplate = true
                customIcon.size = NSSize(width: 18, height: 18)
                // You could modify the icon appearance based on isActive state if needed
                // For now, we'll keep the same icon but could add visual indicators
                button.image = customIcon
            } else {
                // Fallback to system icons with state
                let iconName = isActive ? "mic.circle.fill" : "mic.circle"
                button.image = NSImage(systemSymbolName: iconName, accessibilityDescription: "Omi")
            }
        }
    }
    
    func updateWindowToggleTitle() {
        updateMenuItemTitle(itemIndex: 0, to: getWindowToggleTitle())
    }
    
    func cleanup() {
        NotificationCenter.default.removeObserver(self)
        if let statusBarItem = statusBarItem {
            NSStatusBar.system.removeStatusItem(statusBarItem)
            self.statusBarItem = nil
        }
    }
    
    // MARK: - Private Methods
    
    private func updateFloatingChatMenuItemState() {
        guard let menu = statusBarItem?.menu,
              let menuItem = menu.item(withTag: 200) else {
            print("WARNING: Cannot find floating chat menu item with tag 200")
            return
        }
        menuItem.state = isFloatingChatButtonVisible ? .on : .off
    }
    
    @objc private func updateChatWindowStatus() {
        let count = FloatingChatWindowManager.shared.windowCount
        guard let menu = statusBarItem?.menu,
              let menuItem = menu.item(withTag: 202) else {
            print("WARNING: Cannot find chat status menu item with tag 202")
            return
        }
        
        if count == 0 {
            menuItem.title = "No Chat Windows Open"
        } else if count == 1 {
            menuItem.title = "1 Chat Window Open"
        } else {
            menuItem.title = "\(count) Chat Windows Open"
        }
    }
    
    private func getWindowToggleTitle() -> String {
        guard let window = mainWindow else { return "Show Window" }
        return window.isVisible ? "Hide Window" : "Show Window"
    }
    
    private func updateMenuItemTitle(itemIndex: Int, to newTitle: String) {
        guard let menu = statusBarItem?.menu,
              itemIndex < menu.numberOfItems else { 
            print("WARNING: Cannot update menu item at index \(itemIndex)")
            return
        }
        
        if let menuItem = menu.item(at: itemIndex) {
            menuItem.title = newTitle
        }
    }
    
    // MARK: - Menu Actions
    
    @objc private func toggleWindowVisibility() {
        print("INFO: Menu bar toggle window action triggered")
        onToggleWindow?()
    }

    @objc private func toggleFloatingChat() {
        onToggleFloatingChat?()
    }

    @objc private func openChatWindow() {
        onOpenChatWindow?()
    }
    
    @objc private func quitApplication() {
        print("INFO: Menu bar quit action triggered")
        onQuit?()
    }
} 
