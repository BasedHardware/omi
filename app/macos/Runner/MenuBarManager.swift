import Cocoa
import ServiceManagement
import Carbon.HIToolbox

// MARK: - Menu Bar Manager
class MenuBarManager: NSObject {
    
    // MARK: - Notification Names
    static let toggleWindowNotification = Notification.Name("com.omi.menubar.toggleWindow")
    static let toggleFloatingChatNotification = Notification.Name("com.omi.menubar.toggleFloatingChat")
    static let openChatWindowNotification = Notification.Name("com.omi.menubar.openChatWindow")
    static let openKeyboardShortcutsNotification = Notification.Name("com.omi.menubar.openKeyboardShortcuts")
    static let quitApplicationNotification = Notification.Name("com.omi.menubar.quitApplication")
    
    // MARK: - Singleton
    static let shared = MenuBarManager()
    
    // MARK: - Properties
    private var statusBarItem: NSStatusItem?
    private weak var mainWindow: NSWindow?
    private var isVisibleObservation: NSKeyValueObservation?
    
    // Meeting display
    private var currentMeetingTitle: String?
    private var currentMeetingStartDate: Date?
    private var updateTimer: Timer?
    
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
        
        // Register observer for shortcut changes
        NotificationCenter.default.addObserver(
            self,
            selector: #selector(handleShortcutDidChange),
            name: GlobalShortcutManager.shortcutDidChangeNotification,
            object: nil
        )
        
        // Setup main application menu for keyboard shortcuts to actually work
        setupMainAppMenu()
        
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
        
        // Chat Window - no shortcut label here since it's app-scoped (shown in main app menu)
        let openChatWindowItem = NSMenuItem(title: "Ask omi", action: #selector(openChatWindow), keyEquivalent: "")
        openChatWindowItem.target = self
        openChatWindowItem.tag = 201
        menu.addItem(openChatWindowItem)
        
        menu.addItem(NSMenuItem.separator())
        
        // Keyboard Shortcuts
        let keyboardShortcutsItem = NSMenuItem(title: "Keyboard Shortcuts...", action: #selector(openKeyboardShortcuts), keyEquivalent: ",")
        keyboardShortcutsItem.target = self
        keyboardShortcutsItem.keyEquivalentModifierMask = [.command]
        keyboardShortcutsItem.tag = 202
        menu.addItem(keyboardShortcutsItem)
        
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
    }
    
    // MARK: - Main Application Menu (for keyboard shortcuts)
    
    private func setupMainAppMenu() {
        // Get or create the main menu
        if NSApp.mainMenu == nil {
            NSApp.mainMenu = NSMenu()
        }
        
        guard let mainMenu = NSApp.mainMenu else { return }
        
        // Find or create the app menu item
        var appMenuItem: NSMenuItem
        if let existingItem = mainMenu.item(at: 0) {
            appMenuItem = existingItem
        } else {
            appMenuItem = NSMenuItem()
            mainMenu.addItem(appMenuItem)
        }
        
        // Create submenu if needed
        if appMenuItem.submenu == nil {
            appMenuItem.submenu = NSMenu(title: "Omi")
        }
        
        guard let appMenu = appMenuItem.submenu else { return }
        
        // Remove existing Ask omi item if present
        if let existingItem = appMenu.item(withTag: 301) {
            appMenu.removeItem(existingItem)
        }
        
        // Add Ask omi shortcut to the main app menu
        let (keyCode, modifiers) = GlobalShortcutManager.shared.getAskAIShortcut()
        let keyEquivalent = keyEquivalentString(for: keyCode)
        
        let askOmiItem = NSMenuItem(title: "Ask omi", action: #selector(openChatWindow), keyEquivalent: keyEquivalent)
        askOmiItem.target = self
        askOmiItem.keyEquivalentModifierMask = modifierMask(for: modifiers)
        askOmiItem.tag = 301
        
        // Insert at beginning of app menu
        appMenu.insertItem(askOmiItem, at: 0)
    }
    
    private func updateMainAppMenuShortcut() {
        guard let mainMenu = NSApp.mainMenu,
              let appMenuItem = mainMenu.item(at: 0),
              let appMenu = appMenuItem.submenu,
              let askOmiItem = appMenu.item(withTag: 301) else {
            return
        }
        
        let (keyCode, modifiers) = GlobalShortcutManager.shared.getAskAIShortcut()
        let keyEquivalent = keyEquivalentString(for: keyCode)
        
        askOmiItem.keyEquivalent = keyEquivalent
        askOmiItem.keyEquivalentModifierMask = modifierMask(for: modifiers)
    }
    
    // MARK: - Meeting Display

    /// Update menu bar to show upcoming meeting info
    func updateWithMeeting(title: String, startDate: Date) {
        // Store meeting info
        currentMeetingTitle = title
        currentMeetingStartDate = startDate

        // Update display immediately
        updateMeetingDisplay()

        // Start timer to update every minute
        startUpdateTimer()
    }
    
    /// Reset menu bar to default icon view
    func resetToDefaultView() {
        // Clear meeting info
        currentMeetingTitle = nil
        currentMeetingStartDate = nil
        
        // Stop timer
        stopUpdateTimer()
        
        guard let statusBarItem = statusBarItem,
              let button = statusBarItem.button else {
            return
        }
        
        DispatchQueue.main.async {
            // Clear title
            button.title = ""
            
            // Restore icon
            if let customIcon = NSImage(named: "app_launcher_icon") {
                customIcon.isTemplate = true
                customIcon.size = NSSize(width: 18, height: 18)
                button.image = customIcon
            } else {
                button.image = NSImage(systemSymbolName: "mic.circle", accessibilityDescription: "Omi")
            }
            
            button.toolTip = "Omi - Always On AI"
            statusBarItem.length = NSStatusItem.squareLength
        }
    }
    
    private func startUpdateTimer() {
        // Stop any existing timer
        stopUpdateTimer()
        
        // Create new timer that fires every minute
        updateTimer = Timer.scheduledTimer(withTimeInterval: 60.0, repeats: true) { [weak self] _ in
            self?.updateMeetingDisplay()
        }
    }
    
    private func stopUpdateTimer() {
        updateTimer?.invalidate()
        updateTimer = nil
    }
    
    private func updateMeetingDisplay() {
        guard let title = currentMeetingTitle,
              let startDate = currentMeetingStartDate,
              let statusBarItem = statusBarItem,
              let button = statusBarItem.button else {
            return
        }

        // Calculate seconds until meeting and round up to minutes
        // This ensures "in 1m" means "less than 1 minute" and "in 0m" only shows when meeting starts
        let secondsUntil = startDate.timeIntervalSinceNow
        let minutesUntil = Int(ceil(secondsUntil / 60))

        // If meeting has passed, reset to default
        if minutesUntil < 0 {
            resetToDefaultView()
            return
        }

        DispatchQueue.main.async {
            // Clear the icon
            button.image = nil

            // Format time remaining
            let timeString: String
            if minutesUntil >= 60 {
                let hours = minutesUntil / 60
                let minutes = minutesUntil % 60
                timeString = "in \(hours)h \(minutes)m"
            } else if minutesUntil == 0 {
                timeString = "starting now"
            } else {
                timeString = "in \(minutesUntil)m"
            }

            // Truncate title if too long
            let displayTitle = title.count > 20 ? String(title.prefix(17)) + "..." : title

            // Set title with meeting info
            button.title = "\(displayTitle) • \(timeString)"
            button.toolTip = "Upcoming meeting: \(title)"

            // Adjust width to fit text
            statusBarItem.length = NSStatusItem.variableLength
        }
    }
    
    // MARK: - Public Methods
    
    func observeFloatingControlBar(_ controlBar: FloatingControlBar) {
        isVisibleObservation = controlBar.observe(\.isVisible, options: [.initial, .new]) { [weak self] _, change in
            DispatchQueue.main.async {
                self?.updateFloatingChatMenuItemState(isVisible: change.newValue ?? false)
            }
        }
    }
    
    func cleanup() {
        stopUpdateTimer()
        NotificationCenter.default.removeObserver(self)
        if let statusBarItem = statusBarItem {
            NSStatusBar.system.removeStatusItem(statusBarItem)
            self.statusBarItem = nil
        }
    }
    
    // MARK: - Private Methods
    
    private func updateFloatingChatMenuItemState(isVisible: Bool) {
        guard let menu = statusBarItem?.menu,
              let menuItem = menu.item(withTag: 200) else {
            print("WARNING: Cannot find control bar menu item with tag 200")
            return
        }
        menuItem.state = isVisible ? .on : .off
        menuItem.title = isVisible ? "Hide Control Bar" : "Show Control Bar"
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
        NotificationCenter.default.post(name: MenuBarManager.toggleWindowNotification, object: nil)
    }

    @objc private func toggleFloatingChat() {
        NotificationCenter.default.post(name: MenuBarManager.toggleFloatingChatNotification, object: nil)
    }

    @objc private func openChatWindow() {
        NotificationCenter.default.post(name: MenuBarManager.openChatWindowNotification, object: nil)
    }
    
    @objc private func openKeyboardShortcuts() {
        NotificationCenter.default.post(name: MenuBarManager.openKeyboardShortcutsNotification, object: nil)
    }
    
    @objc private func openOmiWebsite() {
        if let url = URL(string: "https://omi.me") {
            NSWorkspace.shared.open(url)
        }
    }
    
    @objc private func quitApplication() {
        NotificationCenter.default.post(name: MenuBarManager.quitApplicationNotification, object: nil)
    }
    
    @objc private func handleShortcutDidChange() {
        updateAskOmiMenuItem()
        updateMainAppMenuShortcut()
    }
    
    private func updateAskOmiMenuItem() {
        // Status bar menu item no longer shows shortcut (it's app-scoped, shown in main app menu)
        // This method kept for potential future use
    }
    
    // MARK: - Helper Methods
    
    private func keyEquivalentString(for keyCode: Int) -> String {
        switch keyCode {
        case Int(kVK_Return), Int(kVK_ANSI_KeypadEnter):
            return "\r"
        case 42: // backslash
            return "\\"
        // Letter keys (ANSI codes are NOT contiguous, must handle individually)
        case Int(kVK_ANSI_A): return "a"
        case Int(kVK_ANSI_B): return "b"
        case Int(kVK_ANSI_C): return "c"
        case Int(kVK_ANSI_D): return "d"
        case Int(kVK_ANSI_E): return "e"
        case Int(kVK_ANSI_F): return "f"
        case Int(kVK_ANSI_G): return "g"
        case Int(kVK_ANSI_H): return "h"
        case Int(kVK_ANSI_I): return "i"
        case Int(kVK_ANSI_J): return "j"
        case Int(kVK_ANSI_K): return "k"
        case Int(kVK_ANSI_L): return "l"
        case Int(kVK_ANSI_M): return "m"
        case Int(kVK_ANSI_N): return "n"
        case Int(kVK_ANSI_O): return "o"
        case Int(kVK_ANSI_P): return "p"
        case Int(kVK_ANSI_Q): return "q"
        case Int(kVK_ANSI_R): return "r"
        case Int(kVK_ANSI_S): return "s"
        case Int(kVK_ANSI_T): return "t"
        case Int(kVK_ANSI_U): return "u"
        case Int(kVK_ANSI_V): return "v"
        case Int(kVK_ANSI_W): return "w"
        case Int(kVK_ANSI_X): return "x"
        case Int(kVK_ANSI_Y): return "y"
        case Int(kVK_ANSI_Z): return "z"
        // Number keys
        case Int(kVK_ANSI_0): return "0"
        case Int(kVK_ANSI_1): return "1"
        case Int(kVK_ANSI_2): return "2"
        case Int(kVK_ANSI_3): return "3"
        case Int(kVK_ANSI_4): return "4"
        case Int(kVK_ANSI_5): return "5"
        case Int(kVK_ANSI_6): return "6"
        case Int(kVK_ANSI_7): return "7"
        case Int(kVK_ANSI_8): return "8"
        case Int(kVK_ANSI_9): return "9"
        default:
            return ""
        }
    }
    
    private func modifierMask(for carbonModifiers: UInt32) -> NSEvent.ModifierFlags {
        var mask: NSEvent.ModifierFlags = []
        if (carbonModifiers & UInt32(cmdKey)) != 0 {
            mask.insert(.command)
        }
        if (carbonModifiers & UInt32(shiftKey)) != 0 {
            mask.insert(.shift)
        }
        if (carbonModifiers & UInt32(optionKey)) != 0 {
            mask.insert(.option)
        }
        if (carbonModifiers & UInt32(controlKey)) != 0 {
            mask.insert(.control)
        }
        return mask
    }
} 
