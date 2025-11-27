import Cocoa
import FlutterMacOS
import ScreenCaptureKit
import AVFoundation
import ServiceManagement
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

    // Floating control bar
    private var floatingControlBar: FloatingControlBar?
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

        floatingControlBarChannel.setMethodCallHandler { [weak self] (call, result) in
            guard let self = self else { return }

            switch call.method {
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
                
            case "getAvailableAudioDevices":
                let devices = self.audioManager.getAvailableAudioDevices()
                result(devices)
                
            case "selectAudioDevice":
                if let args = call.arguments as? [String: Any],
                   let deviceId = args["deviceId"] as? String {
                    let success = self.audioManager.selectAudioDevice(deviceID: deviceId)
                    result(success)
                } else {
                    result(FlutterError(code: "INVALID_ARGUMENTS", message: "Device ID is required", details: nil))
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
        let wasRecording = audioManager.isRecording()
        
        // Explicitly stop recording before sleep to prevent SCStream crashes
        if wasRecording {
            print("DEBUG: Stopping recording before system sleep")
            audioManager.stopCapture()
        }
        
        // Notify Flutter that system is going to sleep
        screenCaptureChannel.invokeMethod("systemWillSleep", arguments: [
            "wasRecording": wasRecording
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
        menuBarManager = MenuBarManager.shared
        menuBarManager?.configure(mainWindow: self)
        menuBarManager?.setupMenuBarItem()
        
        // Setup notification observers for menu actions
        setupMenuBarObservers()
    }
    
    private func setupMenuBarObservers() {
        NotificationCenter.default.addObserver(
            self,
            selector: #selector(handleMenuBarToggleWindow),
            name: MenuBarManager.toggleWindowNotification,
            object: nil
        )
        
        NotificationCenter.default.addObserver(
            self,
            selector: #selector(handleMenuBarQuitApplication),
            name: MenuBarManager.quitApplicationNotification,
            object: nil
        )
        
        NotificationCenter.default.addObserver(
            self,
            selector: #selector(handleMenuBarToggleFloatingChat),
            name: MenuBarManager.toggleFloatingChatNotification,
            object: nil
        )
        
        NotificationCenter.default.addObserver(
            self,
            selector: #selector(handleMenuBarOpenChatWindow),
            name: MenuBarManager.openChatWindowNotification,
            object: nil
        )
    }
    
    private func handleOpenWindow() {
        DispatchQueue.main.async {
            self.makeKeyAndOrderFront(nil)
            NSApp.activate(ignoringOtherApps: true)
            // Mark Flutter engine as active after showing window
            self.audioManager.setFlutterEngineActive(true)
            print("INFO: Window opened and brought to front")
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
                self.floatingControlBar = FloatingControlBar()
                FloatingChatWindowManager.shared.floatingButton = self.floatingControlBar
                self.menuBarManager?.observeFloatingControlBar(self.floatingControlBar!)
                
                self.floatingControlBar?.onAskAI = { fileUrl in
                    let screenshot: URL?
                    if let url = fileUrl {
                        screenshot = url
                    } else {
                        screenshot = ScreenCaptureManager.captureScreen()
                    }
                    FloatingChatWindowManager.shared.toggleAIConversation(fileUrl: screenshot)
                }
                
                self.floatingControlBar?.onPlayPause = { [weak self] in
                    self?.handlePlayPauseWithRetry()
                }
                
                self.floatingControlBar?.onSendQuery = { message, url in
                    FloatingChatWindowManager.shared.sendAIQuery(message: message, url: url)
                }
                
                self.floatingControlBar?.onHide = { }
            }
            self.floatingControlBar?.makeKeyAndOrderFront(nil)
        }
    }

    func hideFloatingControlBar() {
        DispatchQueue.main.async {
            self.floatingControlBar?.orderOut(nil)
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
    
    // MARK: - Menu Bar Action Handlers
    
    @objc private func handleMenuBarToggleWindow() {
        handleOpenWindow()
    }
    
    @objc private func handleMenuBarQuitApplication() {
        handleQuitApplication()
    }
    
    @objc private func handleMenuBarToggleFloatingChat() {
        handleToggleFloatingButtonShortcut()
    }
    
    @objc private func handleMenuBarOpenChatWindow() {
        let fileUrl = ScreenCaptureManager.captureScreen()
        FloatingChatWindowManager.shared.toggleAIConversation(fileUrl: fileUrl)
    }

    private func handlePlayPauseWithRetry() {
        var attempts = 0
        let maxAttempts = 3
        
        func attemptInvoke() {
            attempts += 1
            
            floatingControlBarChannel.invokeMethod("togglePauseResume", arguments: nil) { result in
                if result is FlutterError, attempts < maxAttempts {
                    DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) {
                        attemptInvoke()
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
        let fileUrl = ScreenCaptureManager.captureScreen()
        FloatingChatWindowManager.shared.toggleAIConversation(fileUrl: fileUrl)
    }
}
