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

    // Floating overlay window
    private var floatingOverlay: FloatingRecordingOverlay?

    // Menu bar manager
    private var menuBarManager: MenuBarManager?

    // Overlay channel
    private var overlayChannel: FlutterMethodChannel!



    override func awakeFromNib() {
        let flutterViewController = FlutterViewController()
        let windowFrame = self.frame
        self.contentViewController = flutterViewController
        self.setFrame(windowFrame, display: true)

        RegisterGeneratedPlugins(registry: flutterViewController)

        screenCaptureChannel = FlutterMethodChannel(
            name: "screenCapturePlatform",
            binaryMessenger: flutterViewController.engine.binaryMessenger)

        // Setup overlay channel
        overlayChannel = FlutterMethodChannel(
            name: "overlayPlatform",
            binaryMessenger: flutterViewController.engine.binaryMessenger)

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

        // Setup audio manager with Flutter channel
        audioManager.setFlutterChannel(screenCaptureChannel)

        // Setup overlay channel handlers
        overlayChannel.setMethodCallHandler { [weak self] (call, result) in
            guard let self = self else { return }
            
            switch call.method {
            case "showOverlay":
                self.showOverlay()
                result(nil)
                
            case "hideOverlay":
                self.hideOverlay()
                result(nil)
                
            case "updateOverlayState":
                guard let args = call.arguments as? [String: Any],
                      let isRecording = args["isRecording"] as? Bool,
                      let isPaused = args["isPaused"] as? Bool else {
                    result(FlutterError(code: "INVALID_ARGUMENTS", message: "Missing required parameters", details: nil))
                    return
                }
                self.updateOverlayState(isRecording: isRecording, isPaused: isPaused)
                result(nil)
                
            case "updateOverlayTranscript":
                guard let args = call.arguments as? [String: Any],
                      let transcript = args["transcript"] as? String,
                      let segmentCount = args["segmentCount"] as? Int else {
                    result(FlutterError(code: "INVALID_ARGUMENTS", message: "Missing required parameters", details: nil))
                    return
                }
                self.updateOverlayTranscript(transcript: transcript, segmentCount: segmentCount)
                result(nil)
                
            case "updateOverlayStatus":
                guard let args = call.arguments as? [String: Any],
                      let status = args["status"] as? String else {
                    result(FlutterError(code: "INVALID_ARGUMENTS", message: "Missing status parameter", details: nil))
                    return
                }
                self.updateOverlayStatus(status: status)
                result(nil)
                
            case "moveOverlay":
                guard let args = call.arguments as? [String: Any],
                      let x = args["x"] as? Double,
                      let y = args["y"] as? Double else {
                    result(FlutterError(code: "INVALID_ARGUMENTS", message: "Missing position parameters", details: nil))
                    return
                }
                self.moveOverlay(x: x, y: y)
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
        
        // Hide overlay
        hideOverlay()
        
        // Cleanup menu bar
        menuBarManager?.cleanup()
        
        NSApp.terminate(nil)
    }
    
    // MARK: - Floating Overlay Methods
    
    private func showOverlay() {
        DispatchQueue.main.async {
            print("DEBUG: showOverlay called")
            
            if self.floatingOverlay != nil {
                print("DEBUG: Overlay already exists, updating instead of creating new one")
                self.floatingOverlay?.makeKeyAndOrderFront(nil)
                return
            }
            
            print("DEBUG: Creating new overlay window")
            
            // Position overlay in top-right corner of main screen
            guard let screen = NSScreen.main else { 
                print("ERROR: Could not get main screen for overlay positioning")
                return 
            }
            
            let screenFrame = screen.visibleFrame
            let overlayFrame = NSRect(
                x: screenFrame.maxX - 240, // 220 width + 20 margin
                y: screenFrame.maxY - 72,  // 52 height + 20 margin
                width: 220,
                height: 52
            )
            
            print("DEBUG: Overlay frame: \(overlayFrame)")
                
            self.floatingOverlay = FloatingRecordingOverlay(
                contentRect: overlayFrame,
                styleMask: [.borderless],
                backing: .buffered,
                defer: false
            )
            
            // Configure overlay window properties for stability
            self.floatingOverlay?.isReleasedWhenClosed = false
            self.floatingOverlay?.hidesOnDeactivate = false
            
            print("DEBUG: Overlay window created successfully")
            
            // Setup callbacks
            self.floatingOverlay?.onPlayPause = { [weak self] in
                guard let self = self, let overlayChannel = self.overlayChannel else {
                    print("WARNING: Overlay channel not available for onPlayPause")
                    return
                }
                print("DEBUG: Overlay play/pause callback triggered")
                overlayChannel.invokeMethod("onPlayPause", arguments: nil)
            }
            
            self.floatingOverlay?.onStop = { [weak self] in
                guard let self = self, let overlayChannel = self.overlayChannel else {
                    print("WARNING: Overlay channel not available for onStop")
                    return
                }
                print("DEBUG: Overlay stop callback triggered")
                overlayChannel.invokeMethod("onStop", arguments: nil)
            }
            
            self.floatingOverlay?.onExpand = { [weak self] in
                guard let self = self else {
                    print("WARNING: MainFlutterWindow reference lost in onExpand")
                    return
                }
                print("DEBUG: Overlay expand callback triggered - restoring main window")
                
                // Prevent delegate callbacks during restoration to avoid conflicts
                self.delegate = nil
                
                // Hide the overlay first to prevent visual conflicts
                self.hideOverlay()
                
                // Restore the main window after hiding overlay
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.1) {
                    self.restoreMainWindow()
                    
                    // Re-enable delegate after restoration is complete
                    DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) {
                        self.delegate = self
                    }
                    
                    // Notify Flutter after restoration is complete
                    if let overlayChannel = self.overlayChannel {
                        overlayChannel.invokeMethod("onExpand", arguments: nil)
                    }
                }
            }
            
            self.floatingOverlay?.makeKeyAndOrderFront(nil)
            
            print("DEBUG: Floating overlay shown successfully")
        }
    }
    
    private func hideOverlay() {
        // Ensure we're on the main thread and prevent concurrent access
        DispatchQueue.main.async {
            guard let overlay = self.floatingOverlay else {
                print("DEBUG: No overlay to hide")
                return
            }
            
            print("DEBUG: Hiding floating overlay...")
            
            // Clear the reference first to prevent recursive calls
            self.floatingOverlay = nil
            
            // Safely close the overlay with error handling
            do {
                overlay.orderOut(nil)
                overlay.close()
                print("DEBUG: Floating overlay hidden successfully")
            } catch {
                print("DEBUG: Error closing overlay: \(error)")
            }
            
            // Notify Flutter that overlay was hidden (with error handling)
            if let overlayChannel = self.overlayChannel {
                overlayChannel.invokeMethod("onOverlayHidden", arguments: nil)
            }
        }
    }
    
    private func updateOverlayState(isRecording: Bool, isPaused: Bool) {
        DispatchQueue.main.async {
            self.floatingOverlay?.updateRecordingState(isRecording: isRecording, isPaused: isPaused)
            
            // Update menu bar status
            if isRecording {
                self.menuBarManager?.updateStatus(status: "Recording", isActive: true)
            } else if isPaused {
                self.menuBarManager?.updateStatus(status: "Paused", isActive: false)
            } else {
                self.menuBarManager?.updateStatus(status: "Ready", isActive: false)
            }
        }
    }
    
    private func updateOverlayTranscript(transcript: String, segmentCount: Int) {
        DispatchQueue.main.async {
            self.floatingOverlay?.updateTranscript(transcript, segmentCount: segmentCount)
            
            // Update menu bar status with segment count if recording
            if segmentCount > 0 {
                self.menuBarManager?.updateStatus(status: "Recording (\(segmentCount) segments)", isActive: true)
            }
        }
    }
    
    private func updateOverlayStatus(status: String) {
        DispatchQueue.main.async {
            self.floatingOverlay?.updateStatusText(status)
        }
    }
    
    private func moveOverlay(x: Double, y: Double) {
        DispatchQueue.main.async {
            let newOrigin = NSPoint(x: x, y: y)
            self.floatingOverlay?.setFrameOrigin(newOrigin)
        }
    }
    
    private func restoreMainWindow() {
        print("DEBUG: Attempting to restore main window from MainFlutterWindow...")
        
        // Ensure we're on the main thread for all window operations
        DispatchQueue.main.async {
            // Check if window is valid before operating on it
            guard self.isVisible || self.isMiniaturized else {
                print("DEBUG: Window is not in a valid state for restoration")
                NSApp.activate(ignoringOtherApps: true)
                return
            }
            
            // If this window is minimized, deminiaturize it first
            if self.isMiniaturized {
                print("DEBUG: Window is minimized, deminiaturizing...")
                self.deminiaturize(nil)
                
                // Wait a brief moment for deminiaturization to complete
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.1) {
                    self.completeWindowRestoration()
                }
            } else {
                self.completeWindowRestoration()
            }
        }
    }
    
    private func completeWindowRestoration() {
        print("DEBUG: Completing window restoration...")
        
        // Make this window visible and bring to front
        self.makeKeyAndOrderFront(nil)
        self.orderFrontRegardless()
        
        // Activate the app
        NSApp.activate(ignoringOtherApps: true)
        
        print("DEBUG: Successfully restored main window")
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
        
        // Only hide overlay if it exists and is visible
        guard let overlay = floatingOverlay, overlay.isVisible else {
            return
        }
        
        print("DEBUG: Main Flutter window became active, hiding overlay")
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.1) {
            self.hideOverlay()
        }
    }
    
    func windowDidBecomeKey(_ notification: Notification) {
        guard let notificationWindow = notification.object as? NSWindow,
              notificationWindow == self else {
            return
        }
        
        print("DEBUG: Window became key")
        
        // Ensure Flutter engine is marked as active when window becomes key
        audioManager.setFlutterEngineActive(true)
        
        // Only hide overlay if it exists and is visible
        guard let overlay = floatingOverlay, overlay.isVisible else {
            return
        }
        
        print("DEBUG: Main Flutter window became key, hiding overlay")
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.1) {
            self.hideOverlay()
        }
    }
    
    func windowDidDeminiaturize(_ notification: Notification) {
        guard let notificationWindow = notification.object as? NSWindow,
              notificationWindow == self else {
            return
        }
        
        print("DEBUG: Window deminiaturized")
        
        // Ensure Flutter engine is marked as active when window is deminiaturized
        audioManager.setFlutterEngineActive(true)
        
        // Only hide overlay if it exists and is visible
        guard let overlay = floatingOverlay, overlay.isVisible else {
            return
        }
        
        print("DEBUG: Main Flutter window deminiaturized, hiding overlay")
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.1) {
            self.hideOverlay()
        }
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
        print("DEBUG: 🧹 Screen sleep/wake observers removed")
    }
}
