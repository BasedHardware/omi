import Cocoa

// MARK: - Menu Bar Manager
class MenuBarManager: NSObject {
    
    // MARK: - Properties
    private var statusBarItem: NSStatusItem?
    private weak var mainWindow: NSWindow?
    
    // Callbacks for menu actions
    var onToggleWindow: (() -> Void)?
    var onQuit: (() -> Void)?
    
    // MARK: - Initialization
    init(mainWindow: NSWindow) {
        self.mainWindow = mainWindow
        super.init()
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
        if let statusBarItem = statusBarItem {
            NSStatusBar.system.removeStatusItem(statusBarItem)
            self.statusBarItem = nil
        }
    }
    
    // MARK: - Private Methods
    
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
    
    @objc private func quitApplication() {
        print("INFO: Menu bar quit action triggered")
        onQuit?()
    }
} 