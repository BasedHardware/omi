import Cocoa
import FlutterMacOS
import ScreenCaptureKit
import AVFoundation
import CoreBluetooth
import CoreLocation
import UserNotifications

class MainFlutterWindow: NSWindow, NSWindowDelegate {

    private var screenCaptureChannel: FlutterMethodChannel!
    
    // Audio manager
    private let audioManager = AudioManager()

    // Permission manager
    private let permissionManager = PermissionManager.shared

    // Menu bar manager
    private var menuBarManager: MenuBarManager?

    // Auto-start channel
    private var autoStartChannel: FlutterMethodChannel!

    // Floating Chat
    private var floatingControlBar: FloatingControlBar?
    private var floatingChatChannel: FlutterMethodChannel!
    private var floatingControlBarChannel: FlutterMethodChannel!
    private var askAIChannel: FlutterMethodChannel!



    override func awakeFromNib() {
        let flutterViewController = FlutterViewController()
        let windowFrame = self.frame
        self.contentViewController = flutterViewController
        self.setFrame(windowFrame, display: true)

        RegisterGeneratedPlugins(registry: flutterViewController)

        screenCaptureChannel = FlutterMethodChannel(
            name: "screenCapturePlatform",
            binaryMessenger: flutterViewController.engine.binaryMessenger)

        // Setup auto-start channel
        autoStartChannel = FlutterMethodChannel(
            name: "com.omi.macos/autostart",
            binaryMessenger: flutterViewController.engine.binaryMessenger)

        // Setup floating chat channel
        floatingChatChannel = FlutterMethodChannel(
            name: "com.omi/floating_chat",
            binaryMessenger: flutterViewController.engine.binaryMessenger)

        // Setup floating control bar channel
        floatingControlBarChannel = FlutterMethodChannel(
            name: "com.omi/floating_control_bar",
            binaryMessenger: flutterViewController.engine.binaryMessenger)

        askAIChannel = FlutterMethodChannel(
            name: "com.omi/ask_ai",
            binaryMessenger: flutterViewController.engine.binaryMessenger)
        
        // Configure the shared window manager
        FloatingChatWindowManager.shared.configure(flutterEngine: flutterViewController.engine, askAIChannel: askAIChannel)
        
        askAIChannel.setMethodCallHandler { (call, result) in
            switch call.method {
            case "aiResponseChunk":
                FloatingChatWindowManager.shared.handleAIResponseChunk(arguments: call.arguments)
                result(nil)
            default:
                result(FlutterMethodNotImplemented)
            }
        }

        // Set self as delegate to detect window events
        self.delegate = self

        // Configure window for rounded corners
        self.titlebarAppearsTransparent = true
        self.isMovableByWindowBackground = true
        self.backgroundColor = NSColor.clear
        self.isOpaque = false
        
        // Add rounded corners to the window
        if let contentView = self.contentView {
            contentView.wantsLayer = true
            contentView.layer?.cornerRadius = 18.0
            contentView.layer?.masksToBounds = true
            
            // Add subtle shadow for depth
            self.hasShadow = true
            contentView.layer?.shadowColor = NSColor.black.cgColor
            contentView.layer?.shadowOpacity = 0.1
            contentView.layer?.shadowRadius = 8.0
            contentView.layer?.shadowOffset = CGSize(width: 0, height: 4)
        }

        // MARK: - Setup Menu Bar (after channels are initialized)
        // Add a small delay to ensure Flutter engine is fully ready
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.1) {
            self.setupMenuBar()
        }

        // Setup global shortcuts
        GlobalShortcutManager.shared.registerShortcuts()

        // Setup audio manager with Flutter channel
        audioManager.setFlutterChannel(screenCaptureChannel)

        autoStartChannel.setMethodCallHandler { (call, result) in
            switch call.method {
            case "isAutoStartEnabled":
                result(LoginItemManager.shared.isEnabled)
            case "setAutoStart":
                if let args = call.arguments as? [String: Any],
                   let isEnabled = args["isEnabled"] as? Bool {
                    LoginItemManager.shared.isEnabled = isEnabled
                    result(nil)
                } else {
                    result(FlutterError(code: "INVALID_ARGUMENTS", message: "Missing 'isEnabled' argument", details: nil))
                }
            case "getStartupBehavior":
                result(LoginItemManager.shared.startupBehavior.rawValue)
            case "setStartupBehavior":
                if let args = call.arguments as? [String: Any],
                   let behaviorRawValue = args["behavior"] as? String,
                   let behavior = StartupBehavior(rawValue: behaviorRawValue) {
                    LoginItemManager.shared.startupBehavior = behavior
                    result(nil)
                } else {
                    result(FlutterError(code: "INVALID_ARGUMENTS", message: "Invalid 'behavior' argument", details: nil))
                }
            default:
                result(FlutterMethodNotImplemented)
            }
        }

        floatingChatChannel.setMethodCallHandler { (call, result) in
            switch call.method {
            case "showChatWindow":
                if let args = call.arguments as? [String: Any],
                   let id = args["id"] as? String {
                    FloatingChatWindowManager.shared.showWindow(id: id)
                    result(nil)
                } else {
                    result(FlutterError(code: "INVALID_ARGUMENTS", message: "Missing 'id' argument", details: nil))
                }
            case "hideChatWindow":
                if let args = call.arguments as? [String: Any],
                   let id = args["id"] as? String {
                    FloatingChatWindowManager.shared.hideWindow(id: id)
                    result(nil)
                } else {
                    result(FlutterError(code: "INVALID_ARGUMENTS", message: "Missing 'id' argument", details: nil))
                }
            case "aiResponse":
                FloatingChatWindowManager.shared.handleAIResponse(arguments: call.arguments)
                result(nil)
            case "chatHistory":
                FloatingChatWindowManager.shared.handleChatHistory(arguments: call.arguments)
                result(nil)
            default:
                result(FlutterMethodNotImplemented)
            }
        }

        floatingControlBarChannel.setMethodCallHandler { [weak self] (call, result) in
            guard let self = self else { return }

            switch call.method {
            case "showButton":
                self.showFloatingControlBar()
                result(nil)
            case "hideButton":
                self.hideFloatingControlBar()
                result(nil)
            case "resetButtonPosition":
                self.floatingControlBar?.resetPosition()
                result(nil)
            case "resetAllPositions":
                self.floatingControlBar?.resetPosition()
                FloatingChatWindowManager.shared.resetAllPositions()
                result(nil)
            case "updateRecordingState":
                if let args = call.arguments as? [String: Any],
                   let isRecording = args["isRecording"] as? Bool,
                   let isPaused = args["isPaused"] as? Bool,
                   let duration = args["duration"] as? Int,
                   let isInitialising = args["isInitialising"] as? Bool {
                    self.floatingControlBar?.updateRecordingState(
                        isRecording: isRecording, 
                        isPaused: isPaused, 
                        duration: duration,
                        isInitialising: isInitialising
                    )
                }
                result(nil)
            default:
                result(FlutterMethodNotImplemented)
            }
        }

        screenCaptureChannel.setMethodCallHandler { [weak self] (call, result) in
            guard let self = self else { return }
            switch call.method {
            case "checkMicrophonePermission":
                let status = self.permissionManager.checkMicrophonePermission()
                result(status)
                
            case "requestMicrophonePermission":
                Task {
                    let granted = await self.permissionManager.requestMicrophonePermission()
                    result(granted)
                }
                
            case "checkScreenCapturePermission":
                Task {
                    let status = await self.permissionManager.checkScreenCapturePermission()
                    result(status)
                }
                
            case "requestScreenCapturePermission":
                Task {
                    let granted = await self.permissionManager.requestScreenCapturePermission()
                    result(granted)
                }
                
            case "checkBluetoothPermission":
                let status = self.permissionManager.checkBluetoothPermission()
                result(status)
                
            case "requestBluetoothPermission":
                Task {
                    let granted = await self.permissionManager.requestBluetoothPermission()
                    result(granted)
                }
                
            case "checkLocationPermission":
                let status = self.permissionManager.checkLocationPermission()
                result(status)
                
            case "requestLocationPermission":
                Task {
                    let granted = await self.permissionManager.requestLocationPermission()
                    result(granted)
                }
                
            case "checkNotificationPermission":
                Task {
                    let status = await self.permissionManager.checkNotificationPermission()
                    result(status)
                }
                
            case "requestNotificationPermission":
                Task {
                    let granted = await self.permissionManager.requestNotificationPermission()
                    result(granted)
                }
                
            case "bringAppToFront":
                DispatchQueue.main.async {
                    NSApp.activate(ignoringOtherApps: true)
                    self.makeKeyAndOrderFront(nil)
                    self.orderFrontRegardless()
                    print("DEBUG: App brought to front after authentication")
                }
                result(nil)
                
            case "start":
                Task {
                    // Check permissions before starting
                    let micStatus = self.permissionManager.checkMicrophonePermission()
                    if micStatus != "granted" {
                        result(FlutterError(code: "MIC_PERMISSION_REQUIRED",
                                          message: "Microphone permission is required. Current status: \(micStatus)",
                                          details: nil))
                        return
                    }

                    let screenStatus = await self.permissionManager.checkScreenCapturePermission()
                    if screenStatus != "granted" {
                        result(FlutterError(code: "SCREEN_PERMISSION_REQUIRED",
                                          message: "Screen capture permission is required. Current status: \(screenStatus)",
                                          details: nil))
                        return
                    }

                    do {
                        try await self.audioManager.startCapture()
                        result(nil)
                    } catch {
                        print("Error starting audio capture: \(error.localizedDescription)")
                        result(FlutterError(code: "AUDIO_START_ERROR", message: error.localizedDescription, details: nil))
                    }
                }
            case "stop":
                self.audioManager.stopCapture()
                result(nil)
                
            case "isRecording":
                let isRecording = self.audioManager.isRecording()
                result(isRecording)
                
            case "validateDisplays":
                Task {
                    let isValid = await self.audioManager.validateDisplaySetup()
                    result(isValid)
                }
                
            case "refreshDisplays":
                Task {
                    do {
                        try await self.audioManager.refreshAvailableContent()
                        result(true)
                    } catch {
                        result(FlutterError(code: "DISPLAY_REFRESH_ERROR", 
                                          message: error.localizedDescription, 
                                          details: nil))
                    }
                }
                
            default:
                result(FlutterMethodNotImplemented)
            }
        }

        // Add screen sleep/wake observers
        setupScreenSleepWakeObservers()

        // Add observers for global shortcuts
        setupShortcutObservers()

        super.awakeFromNib()
    }


    private func setupScreenSleepWakeObservers() {
        // System sleep/wake notifications
        let workspaceCenter = NSWorkspace.shared.notificationCenter
        
        workspaceCenter.addObserver(
            self,
            selector: #selector(systemWillSleep),
            name: NSWorkspace.willSleepNotification,
            object: nil
        )
        
        workspaceCenter.addObserver(
            self,
            selector: #selector(systemDidWake),
            name: NSWorkspace.didWakeNotification,
            object: nil
        )
        
        // Screen lock/unlock notifications (screensaver)
        DistributedNotificationCenter.default().addObserver(
            self,
            selector: #selector(screenDidLock),
            name: Notification.Name("com.apple.screenIsLocked"),
            object: nil
        )
        
        DistributedNotificationCenter.default().addObserver(
            self,
            selector: #selector(screenDidUnlock),
            name: Notification.Name("com.apple.screenIsUnlocked"),
            object: nil
        )
    }
    
    @objc private func systemWillSleep() {
        // Notify Flutter that system is going to sleep
        screenCaptureChannel.invokeMethod("systemWillSleep", arguments: [
            "wasRecording": audioManager.isRecording()
        ])
    }
    
    @objc private func systemDidWake() {
        handleWakeUpStateCheck()
    }
    
    @objc private func screenDidLock() {
        // Notify Flutter about screen lock
        screenCaptureChannel.invokeMethod("screenDidLock", arguments: [
            "wasRecording": audioManager.isRecording()
        ])
    }
    
    @objc private func screenDidUnlock() {
        handleWakeUpStateCheck()
    }
    
    private func handleWakeUpStateCheck() {
        let nativeIsRecording = audioManager.isRecording()
        
        // Always notify Flutter about wake up with current recording state
        screenCaptureChannel.invokeMethod("systemDidWake", arguments: [
            "nativeIsRecording": nativeIsRecording
        ])
        
        // If native is recording, ensure display setup is still valid
        if nativeIsRecording {
            Task {
                let displayValid = await audioManager.validateDisplaySetup()
                
                if !displayValid {
                    screenCaptureChannel.invokeMethod("displaySetupInvalid", arguments: [
                        "reason": "Display setup became invalid after wake up"
                    ])
                }
            }
        }
    }

    // MARK: - Menu Bar Setup
    
    private func setupMenuBar() {
        menuBarManager = MenuBarManager(mainWindow: self)
        
        // Setup callbacks
        menuBarManager?.onToggleWindow = { [weak self] in
            self?.handleWindowToggle()
        }
        
        menuBarManager?.onQuit = { [weak self] in
            self?.handleQuitApplication()
        }
        
        menuBarManager?.onToggleFloatingChat = { [weak self] in
            self?.handleToggleFloatingButtonShortcut()
        }

        menuBarManager?.onOpenChatWindow = {
            // TODO: This should eventually support opening specific or new windows.
            FloatingChatWindowManager.shared.showWindow(id: "default")
        }
        
        menuBarManager?.setupMenuBarItem()
    }
    
    private func handleWindowToggle() {
        DispatchQueue.main.async {
            if self.isVisible {
                // Mark Flutter engine as inactive before hiding window
                self.audioManager.setFlutterEngineActive(false)
                self.orderOut(nil)
                print("INFO: Window hidden")
            } else {
                self.makeKeyAndOrderFront(nil)
                NSApp.activate(ignoringOtherApps: true)
                // Mark Flutter engine as active after showing window
                self.audioManager.setFlutterEngineActive(true)
                print("INFO: Window shown")
            }
            // Update menu title after window state change
            self.menuBarManager?.updateWindowToggleTitle()
        }
    }
    
    private func handleQuitApplication() {
        // Cleanup: stop audio engine and streams
        audioManager.stopCapture()
        
        // Cleanup menu bar
        menuBarManager?.cleanup()
        
        // Unregister global shortcuts
        GlobalShortcutManager.shared.unregisterShortcuts()
        
        NSApp.terminate(nil)
    }

    // MARK: - Floating Chat Methods

    func showFloatingControlBar() {
        DispatchQueue.main.async {
            if self.floatingControlBar == nil {
                let buttonSize = NSSize(width: 280, height: 40)
                self.floatingControlBar = FloatingControlBar(
                    contentRect: NSRect(origin: .zero, size: buttonSize),
                    styleMask: [.borderless],
                    backing: .buffered,
                    defer: false
                )
                FloatingChatWindowManager.shared.floatingButton = self.floatingControlBar
                self.floatingControlBar?.onAskAI = {
                    Task {
                        let screenshotURL = await ScreenCaptureManager.captureScreen()
                        FloatingChatWindowManager.shared.toggleAIConversationWindow(screenshotURL: screenshotURL)
                    }
                }
                self.floatingControlBar?.onPlayPause = { [weak self] in
                    self?.handlePlayPauseWithRetry()
                }
                self.floatingControlBar?.onMove = {
                    // Call both positioning methods when the control bar moves
                    FloatingChatWindowManager.shared.floatingButtonDidMove()
                    FloatingChatWindowManager.shared.positionWindowFromButton()
                }
                self.floatingControlBar?.onResize = { newWidth in
                    FloatingChatWindowManager.shared.aiConversationWindowWidth = newWidth
                }
                self.floatingControlBar?.onHide = { [weak self] in
                    self?.menuBarManager?.updateFloatingChatButtonVisibility(isVisible: false)
                }
            }
            self.floatingControlBar?.makeKeyAndOrderFront(nil)
            self.menuBarManager?.updateFloatingChatButtonVisibility(isVisible: true)
        }
    }

    func hideFloatingControlBar() {
        DispatchQueue.main.async {
            self.floatingControlBar?.orderOut(nil)
            self.menuBarManager?.updateFloatingChatButtonVisibility(isVisible: false)
        }
    }
    
    // MARK: - NSWindowDelegate Methods
    
    func windowDidBecomeMain(_ notification: Notification) {
        guard let notificationWindow = notification.object as? NSWindow,
              notificationWindow == self else {
            return
        }
        
        print("DEBUG: Main window became main")
        
        // Ensure Flutter engine is marked as active when window becomes main
        audioManager.setFlutterEngineActive(true)
    }
    
    func windowDidBecomeKey(_ notification: Notification) {
        guard let notificationWindow = notification.object as? NSWindow,
              notificationWindow == self else {
            return
        }
        
        print("DEBUG: Window became key")
        
        // Ensure Flutter engine is marked as active when window becomes key
        audioManager.setFlutterEngineActive(true)
    }
    
    func windowDidDeminiaturize(_ notification: Notification) {
        guard let notificationWindow = notification.object as? NSWindow,
              notificationWindow == self else {
            return
        }
        
        print("DEBUG: Window deminiaturized")
        
        // Ensure Flutter engine is marked as active when window is deminiaturized
        audioManager.setFlutterEngineActive(true)
    }
    
    func windowDidMiniaturize(_ notification: Notification) {
        guard let notificationWindow = notification.object as? NSWindow,
              notificationWindow == self else {
            return
        }
        
        print("DEBUG: Window miniaturized")
        
        // Mark Flutter engine as inactive when window is minimized
        audioManager.setFlutterEngineActive(false)
    }
    
    func windowWillClose(_ notification: Notification) {
        guard let notificationWindow = notification.object as? NSWindow,
              notificationWindow == self else {
            return
        }
        
        print("DEBUG: Window will close")
        
        // Mark Flutter engine as inactive when window is closing
        audioManager.setFlutterEngineActive(false)
    }

    deinit {
        // Clean up observers
        NSWorkspace.shared.notificationCenter.removeObserver(self)
        DistributedNotificationCenter.default().removeObserver(self)
        NotificationCenter.default.removeObserver(self)
        print("DEBUG: 🧹 Observers removed")
    }
}

// MARK: - Global Shortcut Handlers
extension MainFlutterWindow {
    private func setupShortcutObservers() {
        NotificationCenter.default.addObserver(
            self,
            selector: #selector(handleToggleFloatingButtonShortcut),
            name: GlobalShortcutManager.toggleFloatingButtonNotification,
            object: nil
        )
        NotificationCenter.default.addObserver(
            self,
            selector: #selector(handleAskAIShortcut),
            name: GlobalShortcutManager.askAINotification,
            object: nil
        )
    }

    private func handlePlayPauseWithRetry() {
        var attempts = 0
        let maxAttempts = 3
        
        func attemptInvoke() {
            attempts += 1
            
            floatingControlBarChannel.invokeMethod("togglePauseResume", arguments: nil) { result in
                if let error = result as? FlutterError {
                    if attempts < maxAttempts {
                        DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) {
                            attemptInvoke()
                        }
                    }
                }
            }
        }
        
        attemptInvoke()
    }

    @objc private func handleToggleFloatingButtonShortcut() {
        if floatingControlBar?.isVisible ?? false {
            hideFloatingControlBar()
        } else {
            showFloatingControlBar()
        }
    }

    @objc private func handleAskAIShortcut() {
        Task {
            let screenshotURL = await ScreenCaptureManager.captureScreen()
            FloatingChatWindowManager.shared.toggleAIConversationWindow(screenshotURL: screenshotURL)
        }
    }
}
