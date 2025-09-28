import Cocoa
import ServiceManagement

// MARK: - Menu Bar Manager
class MenuBarManager: NSObject {
    
    // MARK: - Notification Names
    static let toggleWindowNotification = Notification.Name("com.omi.menubar.toggleWindow")
    static let toggleFloatingChatNotification = Notification.Name("com.omi.menubar.toggleFloatingChat")
    static let openChatWindowNotification = Notification.Name("com.omi.menubar.openChatWindow")
    static let quitApplicationNotification = Notification.Name("com.omi.menubar.quitApplication")
    
    // MARK: - Singleton
    static let shared = MenuBarManager()
    
    // MARK: - Properties
    private var statusBarItem: NSStatusItem?
    private weak var mainWindow: NSWindow?
    private var isFloatingChatButtonVisible: Bool = false
    
    // MARK: - Initialization
    private override init() {
        super.init()
    }
    
    // MARK: - Configuration
    func configure(mainWindow: NSWindow) {
        self.mainWindow = mainWindow
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
        
        // Open Omi Window item
        let openOmiItem = NSMenuItem(title: "Open Omi", action: #selector(openOmiWindow), keyEquivalent: "m")
        openOmiItem.target = self
        openOmiItem.keyEquivalentModifierMask = [.command]
        menu.addItem(openOmiItem)
        
        menu.addItem(NSMenuItem.separator())
        
        // Control Bar Toggle
        let toggleControlBarItem = NSMenuItem(title: "Toggle Control Bar", action: #selector(toggleFloatingChat), keyEquivalent: "\\")
        toggleControlBarItem.target = self
        toggleControlBarItem.keyEquivalentModifierMask = [.command]
        toggleControlBarItem.tag = 200
        menu.addItem(toggleControlBarItem)
        
        // Chat Window
        let openChatWindowItem = NSMenuItem(title: "Ask AI", action: #selector(openChatWindow), keyEquivalent: "\r")
        openChatWindowItem.target = self
        openChatWindowItem.keyEquivalentModifierMask = [.command]
        openChatWindowItem.tag = 201
        menu.addItem(openChatWindowItem)
        
        menu.addItem(NSMenuItem.separator())
        
        // Launch at Login item
        if #available(macOS 13.0, *) {
            let launchAtLoginItem = NSMenuItem(title: "Launch at Login", action: #selector(toggleLaunchAtLogin), keyEquivalent: "")
            launchAtLoginItem.target = self
            updateLaunchAtLoginState(for: launchAtLoginItem)
            menu.addItem(launchAtLoginItem)
        }
        
        let aboutItem = NSMenuItem(title: "About Omi", action: #selector(openOmiWebsite), keyEquivalent: "")
        aboutItem.target = self
        menu.addItem(aboutItem)
        
        menu.addItem(NSMenuItem.separator())
        
        // Quit item
        let quitItem = NSMenuItem(title: "Quit Omi", action: #selector(quitApplication), keyEquivalent: "q")
        quitItem.target = self
        quitItem.keyEquivalentModifierMask = [.command]
        menu.addItem(quitItem)
        
        statusBarItem.menu = menu
        
        print("INFO: Menu bar item created successfully")
    }
    
    // MARK: - Public Methods
    
    func updateFloatingChatButtonVisibility(isVisible: Bool) {
        isFloatingChatButtonVisible = isVisible
        updateFloatingChatMenuItemState()
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
            print("WARNING: Cannot find control bar menu item with tag 200")
            return
        }
        menuItem.state = isFloatingChatButtonVisible ? .on : .off
        menuItem.title = isFloatingChatButtonVisible ? "Hide Control Bar" : "Show Control Bar"
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
    
    @available(macOS 13.0, *)
    private func updateLaunchAtLoginState(for item: NSMenuItem) {
        item.state = SMAppService.mainApp.status == SMAppService.Status.enabled ? .on : .off
    }
    
    @available(macOS 13.0, *)
    private func performToggleLaunchAtLogin(for item: NSMenuItem) {
        do {
            if SMAppService.mainApp.status == SMAppService.Status.enabled {
                try SMAppService.mainApp.unregister()
                item.state = .off
            } else {
                try SMAppService.mainApp.register()
                item.state = .on
            }
        } catch {
            print("ERROR: Failed to update Launch at Login status: \(error.localizedDescription)")
        }
    }
    
    @objc private func toggleLaunchAtLogin(_ sender: NSMenuItem) {
        if #available(macOS 13.0, *) {
            performToggleLaunchAtLogin(for: sender)
        }
    }
    
    @objc private func openOmiWindow() {
        print("INFO: Menu bar open Omi window action triggered")
        NotificationCenter.default.post(name: MenuBarManager.toggleWindowNotification, object: nil)
    }

    @objc private func toggleFloatingChat() {
        NotificationCenter.default.post(name: MenuBarManager.toggleFloatingChatNotification, object: nil)
    }

    @objc private func openChatWindow() {
        NotificationCenter.default.post(name: MenuBarManager.openChatWindowNotification, object: nil)
    }
    
    @objc private func openOmiWebsite() {
        print("INFO: Menu bar about action triggered - opening omi.me")
        if let url = URL(string: "https://omi.me") {
            NSWorkspace.shared.open(url)
        }
    }
    
    @objc private func quitApplication() {
        print("INFO: Menu bar quit action triggered")
        NotificationCenter.default.post(name: MenuBarManager.quitApplicationNotification, object: nil)
    }
} 
