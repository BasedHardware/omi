import AVFoundation
import Cocoa
import CoreBluetooth
import CoreLocation
import FlutterMacOS
import ScreenCaptureKit
import ServiceManagement
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

    // Meeting detection
    private var meetingDetector: MeetingDetector?
    private var meetingDetectorChannel: FlutterMethodChannel!
    private var meetingDetectorEventChannel: FlutterEventChannel!

    // Calendar monitoring
    private var calendarMonitor: CalendarMonitor?
    private var calendarChannel: FlutterMethodChannel!
    private var calendarEventChannel: FlutterEventChannel!

    // Shortcuts
    private var shortcutChannel: FlutterMethodChannel!

    // Recording source tracking - determines auto-stop behavior
    private enum RecordingSource {
        case none
        case calendar      // Started from calendar meeting nub (before user joined)
        case microphoneLinked  // Started from calendar, then mic activity detected (user joined)
        case microphoneOnly    // Started from mic detection nub (no calendar context)
        case manual        // Started manually from app UI
    }
    private var recordingSource: RecordingSource = .none

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

        // Setup meeting detection channels
        meetingDetectorChannel = FlutterMethodChannel(
            name: "com.omi/meeting_detector",
            binaryMessenger: flutterViewController.engine.binaryMessenger)

        meetingDetectorEventChannel = FlutterEventChannel(
            name: "com.omi/meeting_detector_events",
            binaryMessenger: flutterViewController.engine.binaryMessenger)

        // Setup calendar monitoring channels
        calendarChannel = FlutterMethodChannel(
            name: "com.omi/calendar",
            binaryMessenger: flutterViewController.engine.binaryMessenger)

        calendarEventChannel = FlutterEventChannel(
            name: "com.omi/calendar/events",
            binaryMessenger: flutterViewController.engine.binaryMessenger)

        // Setup shortcuts channel
        shortcutChannel = FlutterMethodChannel(
            name: "com.omi/shortcuts",
            binaryMessenger: flutterViewController.engine.binaryMessenger)

        // Configure the shared window manager
        FloatingChatWindowManager.shared.configure(
            flutterEngine: flutterViewController.engine, askAIChannel: askAIChannel)

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

        // Setup meeting detection
        setupMeetingDetection()

        // Setup calendar monitoring
        setupCalendarMonitoring()

        // Setup shortcuts channel
        setupShortcutsChannel()

        floatingControlBarChannel.setMethodCallHandler { [weak self] (call, result) in
            guard let self = self else { return }

            switch call.method {
            case "updateRecordingState":
                if let args = call.arguments as? [String: Any],
                    let isRecording = args["isRecording"] as? Bool,
                    let isPaused = args["isPaused"] as? Bool,
                    let duration = args["duration"] as? Int,
                    let isInitialising = args["isInitialising"] as? Bool
                {
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

            case "checkAccessibilityPermission":
                let status = self.permissionManager.checkAccessibilityPermission()
                result(status)

            case "requestAccessibilityPermission":
                Task {
                    let granted = await self.permissionManager.requestAccessibilityPermission()
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
                // Track that recording was started manually from the app
                // BUT only if not already set by nub click (microphoneOnly, calendar, etc.)
                if self.recordingSource == .none {
                    self.recordingSource = .manual
                }

                Task {
                    // Check permissions before starting
                    let micStatus = self.permissionManager.checkMicrophonePermission()
                    if micStatus != "granted" {
                        result(
                            FlutterError(
                                code: "MIC_PERMISSION_REQUIRED",
                                message:
                                    "Microphone permission is required. Current status: \(micStatus)",
                                details: nil))
                        return
                    }

                    let screenStatus = await self.permissionManager.checkScreenCapturePermission()
                    if screenStatus != "granted" {
                        result(
                            FlutterError(
                                code: "SCREEN_PERMISSION_REQUIRED",
                                message:
                                    "Screen capture permission is required. Current status: \(screenStatus)",
                                details: nil))
                        return
                    }

                    do {
                        try await self.audioManager.startCapture()
                        result(nil)
                    } catch {
                        print("Error starting audio capture: \(error.localizedDescription)")
                        result(
                            FlutterError(
                                code: "AUDIO_START_ERROR", message: error.localizedDescription,
                                details: nil))
                    }
                }
            case "stop":
                self.audioManager.stopCapture()
                result(nil)

            case "resetRecordingSource":
                // Called when user explicitly stops recording from UI
                self.recordingSource = .none
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
                        result(
                            FlutterError(
                                code: "DISPLAY_REFRESH_ERROR",
                                message: error.localizedDescription,
                                details: nil))
                    }
                }

            case "getAvailableAudioDevices":
                let devices = self.audioManager.getAvailableAudioDevices()
                result(devices)

            case "selectAudioDevice":
                if let args = call.arguments as? [String: Any],
                    let deviceId = args["deviceId"] as? String
                {
                    let success = self.audioManager.selectAudioDevice(deviceID: deviceId)
                    result(success)
                } else {
                    result(
                        FlutterError(
                            code: "INVALID_ARGUMENTS", message: "Device ID is required",
                            details: nil))
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
        screenCaptureChannel.invokeMethod(
            "systemWillSleep",
            arguments: [
                "wasRecording": wasRecording
            ])
    }

    @objc private func systemDidWake() {
        handleWakeUpStateCheck()
    }

    @objc private func screenDidLock() {
        // Notify Flutter about screen lock
        screenCaptureChannel.invokeMethod(
            "screenDidLock",
            arguments: [
                "wasRecording": audioManager.isRecording()
            ])
    }

    @objc private func screenDidUnlock() {
        handleWakeUpStateCheck()
    }

    private func handleWakeUpStateCheck() {
        let nativeIsRecording = audioManager.isRecording()

        // Always notify Flutter about wake up with current recording state
        screenCaptureChannel.invokeMethod(
            "systemDidWake",
            arguments: [
                "nativeIsRecording": nativeIsRecording
            ])

        // If native is recording, ensure display setup is still valid
        if nativeIsRecording {
            Task {
                let displayValid = await audioManager.validateDisplaySetup()

                if !displayValid {
                    screenCaptureChannel.invokeMethod(
                        "displaySetupInvalid",
                        arguments: [
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

    // MARK: - Meeting Detection Setup

    private func setupMeetingDetection() {
        // Initialize meeting detector
        meetingDetector = MeetingDetector()

        // Configure event channel
        meetingDetector?.configure(eventChannel: meetingDetectorEventChannel)

        // Set main window reference in NubManager
        NubManager.shared.setMainWindow(self)

        // Setup method channel handler
        meetingDetectorChannel.setMethodCallHandler { [weak self] (call, result) in
            guard let self = self else { return }

            switch call.method {
            case "startDetection":
                self.meetingDetector?.start()
                result(nil)

            case "stopDetection":
                self.meetingDetector?.stop()
                result(nil)

            case "getActiveMeetingApps":
                let apps = self.meetingDetector?.getActiveMeetingApps() ?? []
                result(apps)

            case "showNub":
                NubManager.shared.showNub()
                result(nil)

            case "hideNub":
                NubManager.shared.hideNub()
                result(nil)

            case "isNubVisible":
                let isVisible = NubManager.shared.isNubVisible()
                result(isVisible)

            default:
                result(FlutterMethodNotImplemented)
            }
        }

        // Start meeting detection after 10 seconds warmup
        DispatchQueue.main.asyncAfter(deadline: .now() + 10.0) { [weak self] in
            print("MainFlutterWindow: Starting meeting detection after warmup")
            self?.meetingDetector?.start()
        }

        // Setup observer for meeting state changes to control nub
        setupMeetingStateObserver()
    }

    private func setupMeetingStateObserver() {
        NubManager.shared.setMainWindow(self)

        // Provide callback to check if recording is active
        NubManager.shared.isRecordingActive = { [weak self] in
            return self?.audioManager.isRecording() ?? false
        }

        // Listen for nub clicks to start recording
        NotificationCenter.default.addObserver(
            self,
            selector: #selector(handleNubStartRecording),
            name: .nubClicked,
            object: nil
        )

        // Handle when meeting ends (mic activity stopped)
        meetingDetector?.onMeetingEnded = { [weak self] in
            guard let self = self else {
                return
            }

            let isRecording = self.audioManager.isRecording()

            guard isRecording else {
                return
            }

            // Decide whether to auto-stop based on recording source
            let shouldAutoStop: Bool
            let reason: String

            switch self.recordingSource {
            case .microphoneOnly:
                // Recording started from mic nub -> auto-stop when mic ends
                shouldAutoStop = true
                reason = "mic-only recording ended"
            case .microphoneLinked:
                // Recording started from calendar, user joined meeting, now left -> auto-stop
                shouldAutoStop = true
                reason = "user left meeting (calendar + mic)"
            case .calendar:
                // Recording started from calendar but user never joined -> DON'T auto-stop
                shouldAutoStop = false
                reason = "calendar recording (user never joined)"
            case .manual:
                // Recording started manually -> DON'T auto-stop
                shouldAutoStop = false
                reason = "manual recording"
            case .none:
                // Unknown source -> DON'T auto-stop
                shouldAutoStop = false
                reason = "unknown source"
            }

            print("MainFlutterWindow: shouldAutoStop = \(shouldAutoStop), reason = \(reason)")

            if shouldAutoStop {
                print("MainFlutterWindow: Auto-stopping recording")
                self.screenCaptureChannel.invokeMethod("recordingStoppedAutomatically", arguments: nil)
                self.audioManager.stopCapture()
                self.hideFloatingControlBar()
                self.recordingSource = .none
            }
        }
        
        // Handle when meeting starts (mic activity detected)
        meetingDetector?.onShowNub = { [weak self] appName in
            guard let self = self else { return }

            // Check if recording is active AND not paused
            if self.audioManager.isRecording() {
                // Query Flutter to check if recording is paused
                self.screenCaptureChannel.invokeMethod("isRecordingPaused", arguments: nil) { result in
                    let isPaused = result as? Bool ?? false

                    // If recording is active but NOT paused, don't show nub
                    if !isPaused {
                        // Only upgrade from calendar to microphoneLinked (one-time)
                        if self.recordingSource == .calendar {
                            self.recordingSource = .microphoneLinked
                        }
                        return
                    }

                    // Recording is paused, show nub to let user resume/restart
                    NubManager.shared.showNub(for: appName)
                }
                return
            }

            // Not recording yet, show nub to let user start
            NubManager.shared.showNub(for: appName)
        }

        // Handle hiding nub
        meetingDetector?.onHideNub = {
            NubManager.shared.hideNub()
        }
    }

    // MARK: - Calendar Monitoring Setup

    private func setupCalendarMonitoring() {
        // Initialize calendar monitor
        calendarMonitor = CalendarMonitor()

        // Configure event channel
        calendarEventChannel.setStreamHandler(calendarMonitor)

        // Setup method channel handler
        calendarChannel.setMethodCallHandler { [weak self] (call, result) in
            guard let self = self else { return }

            switch call.method {
            case "requestPermission":
                self.calendarMonitor?.requestAccess { granted in
                    if granted {
                        result("authorized")
                    } else {
                        result("denied")
                    }
                }

            case "checkPermissionStatus":
                let isAuthorized = self.calendarMonitor?.checkAuthorizationStatus() ?? false
                result(isAuthorized ? "authorized" : "denied")

            case "startMonitoring":
                self.calendarMonitor?.startMonitoring()
                result(nil)

            case "stopMonitoring":
                self.calendarMonitor?.stopMonitoring()
                result(nil)

            case "getUpcomingMeetings":
                let meetings = self.calendarMonitor?.getUpcomingMeetings() ?? []
                result(meetings)
                
            case "getAvailableCalendars":
                let calendars = self.calendarMonitor?.getAvailableCalendars() ?? []
                result(calendars)
                
            case "updateCalendarSettings":
                if let args = call.arguments as? [String: Any],
                   let showEventsWithNoParticipants = args["showEventsWithNoParticipants"] as? Bool {
                    self.calendarMonitor?.updateSettings(showEventsWithNoParticipants: showEventsWithNoParticipants)
                    result(nil)
                } else {
                    result(FlutterError(code: "INVALID_ARGUMENTS", message: "Settings required", details: nil))
                }

            case "snoozeMeeting":
                if let args = call.arguments as? [String: Any],
                   let eventId = args["eventId"] as? String,
                   let minutes = args["minutes"] as? Int {
                    let duration = TimeInterval(minutes * 60)
                    self.calendarMonitor?.snoozeMeeting(eventId: eventId, duration: duration)
                    result(nil)
                } else {
                    result(FlutterError(code: "INVALID_ARGUMENTS", message: "Event ID and minutes required", details: nil))
                }

            default:
                result(FlutterMethodNotImplemented)
            }
        }

        // Start calendar monitoring after 10 seconds warmup
        DispatchQueue.main.asyncAfter(deadline: .now() + 10.0) { [weak self] in
            guard let self = self else { return }

            // Only start monitoring if already authorized (user enabled it previously)
            let isAuthorized = self.calendarMonitor?.checkAuthorizationStatus() == true

            if isAuthorized {
                self.calendarMonitor?.startMonitoring()
            }
        }
    }

    // MARK: - Shortcuts Setup

    private func setupShortcutsChannel() {
        shortcutChannel.setMethodCallHandler { [weak self] (call, result) in
            guard self != nil else { return }

            switch call.method {
            case "getAskAIShortcut":
                let (keyCode, modifiers) = GlobalShortcutManager.shared.getAskAIShortcut()
                result([
                    "keyCode": keyCode,
                    "modifiers": Int(modifiers),
                    "displayString": GlobalShortcutManager.shared.getAskAIShortcutString()
                ])

            case "setAskAIShortcut":
                if let args = call.arguments as? [String: Any],
                   let keyCode = args["keyCode"] as? Int,
                   let modifiers = args["modifiers"] as? Int {
                    GlobalShortcutManager.shared.setAskAIShortcut(
                        keyCode: keyCode,
                        modifiers: UInt32(modifiers)
                    )
                    result(true)
                } else {
                    result(FlutterError(code: "INVALID_ARGS", message: "Invalid arguments", details: nil))
                }

            case "resetAskAIShortcut":
                GlobalShortcutManager.shared.resetAskAIShortcut()
                result(true)

            case "validateShortcut":
                if let args = call.arguments as? [String: Any],
                   let keyCode = args["keyCode"] as? Int,
                   let modifiers = args["modifiers"] as? Int {
                    let isValid = ShortcutValidator.isValid(keyCode: keyCode, modifiers: UInt32(modifiers))
                    result(isValid)
                } else {
                    result(false)
                }

            case "getToggleControlBarShortcut":
                let (keyCode, modifiers) = GlobalShortcutManager.shared.getToggleControlBarShortcut()
                result([
                    "keyCode": keyCode,
                    "modifiers": Int(modifiers),
                    "displayString": GlobalShortcutManager.shared.getToggleControlBarShortcutString()
                ])

            case "setToggleControlBarShortcut":
                if let args = call.arguments as? [String: Any],
                   let keyCode = args["keyCode"] as? Int,
                   let modifiers = args["modifiers"] as? Int {
                    GlobalShortcutManager.shared.setToggleControlBarShortcut(
                        keyCode: keyCode,
                        modifiers: UInt32(modifiers)
                    )
                    result(true)
                } else {
                    result(FlutterError(code: "INVALID_ARGS", message: "Invalid arguments", details: nil))
                }

            case "resetToggleControlBarShortcut":
                GlobalShortcutManager.shared.resetToggleControlBarShortcut()
                result(true)

            default:
                result(FlutterMethodNotImplemented)
            }
        }
    }

    @objc private func handleNubStartRecording(_ notification: Notification) {
        DispatchQueue.main.async { [weak self] in
            guard let self = self else {
                return
            }

            // Check if microphone is currently active (user already in meeting)
            let isMicActive = !(self.meetingDetector?.getActiveMeetingApps().isEmpty ?? true)

            // Determine recording source based on nub context AND current mic state
            if let meetingSource = NubManager.shared.getCurrentMeetingSource() {
                switch meetingSource {
                case .calendar:
                    // User clicked nub for calendar meeting
                    // Check if they've already joined (mic active)
                    if isMicActive {
                        self.recordingSource = .microphoneLinked
                    } else {
                        self.recordingSource = .calendar
                    }
                case .microphone:
                    // User clicked nub for mic-only detection
                    self.recordingSource = .microphoneOnly
                case .hybrid:
                    // User clicked nub for calendar meeting where they already joined
                    self.recordingSource = .microphoneLinked
                }
            } else {
                self.recordingSource = .manual
            }

            // 1. Start recording
            Task {
                do {
                    // Check permissions first
                    let micStatus = self.permissionManager.checkMicrophonePermission()
                    if micStatus != "granted" {
                        // Open main window to show permission request
                        self.makeKeyAndOrderFront(nil)
                        NSApp.activate(ignoringOtherApps: true)
                        return
                    }

                    let screenStatus = await self.permissionManager.checkScreenCapturePermission()
                    if screenStatus != "granted" {
                        // Open main window to show permission request
                        self.makeKeyAndOrderFront(nil)
                        NSApp.activate(ignoringOtherApps: true)
                        return
                    }

                    // Start audio capture
                    try await self.audioManager.startCapture()

                    // 2. Show floating control bar
                    DispatchQueue.main.async {
                        self.showFloatingControlBar()

                        // Manually update the floating control bar state since recording was started from native
                        self.floatingControlBar?.updateRecordingState(
                            isRecording: true,
                            isPaused: false,
                            duration: 0,
                            isInitialising: false
                        )
                    }

                    // 3. Notify Flutter that recording started
                    self.screenCaptureChannel.invokeMethod("recordingStartedFromNub", arguments: nil)

                } catch {
                    print("MainFlutterWindow: Error starting recording from nub: \(error.localizedDescription)")

                    // Show main window if there's an error
                    DispatchQueue.main.async {
                        self.makeKeyAndOrderFront(nil)
                        NSApp.activate(ignoringOtherApps: true)
                    }
                }
            }
        }
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

        NotificationCenter.default.addObserver(
            self,
            selector: #selector(handleMenuBarOpenKeyboardShortcuts),
            name: MenuBarManager.openKeyboardShortcutsNotification,
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

                self.floatingControlBar?.onAskAI = { [weak self] fileUrl in
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

                self.floatingControlBar?.onHide = {}
            }
            self.floatingControlBar?.makeKeyAndOrderFront(nil)
            
            self.floatingControlBarChannel.invokeMethod("requestCurrentState", arguments: nil)
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
            notificationWindow == self
        else {
            return
        }

        print("DEBUG: Main window became main")

        // Ensure Flutter engine is marked as active when window becomes main
        audioManager.setFlutterEngineActive(true)
    }

    func windowDidBecomeKey(_ notification: Notification) {
        guard let notificationWindow = notification.object as? NSWindow,
            notificationWindow == self
        else {
            return
        }

        print("DEBUG: Window became key")

        // Ensure Flutter engine is marked as active when window becomes key
        audioManager.setFlutterEngineActive(true)
    }

    func windowDidDeminiaturize(_ notification: Notification) {
        guard let notificationWindow = notification.object as? NSWindow,
            notificationWindow == self
        else {
            return
        }

        print("DEBUG: Window deminiaturized")

        // Ensure Flutter engine is marked as active when window is deminiaturized
        audioManager.setFlutterEngineActive(true)
    }

    func windowDidMiniaturize(_ notification: Notification) {
        guard let notificationWindow = notification.object as? NSWindow,
            notificationWindow == self
        else {
            return
        }

        print("DEBUG: Window miniaturized")

        // Mark Flutter engine as inactive when window is minimized
        audioManager.setFlutterEngineActive(false)
    }

    func windowWillClose(_ notification: Notification) {
        guard let notificationWindow = notification.object as? NSWindow,
            notificationWindow == self
        else {
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
        // Activate the app first so it can receive keyboard input
        NSApp.activate(ignoringOtherApps: true)

        let fileUrl = ScreenCaptureManager.captureScreen()

        // Ensure floating control bar exists and is visible
        if floatingControlBar == nil || !(floatingControlBar?.isVisible ?? false) {
            showFloatingControlBar()
        }

        // Small delay to ensure floating bar is ready
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.15) {
            FloatingChatWindowManager.shared.toggleAIConversation(fileUrl: fileUrl)
        }
    }

    @objc private func handleMenuBarOpenKeyboardShortcuts() {
        // Open the main window and navigate to keyboard shortcuts
        handleOpenWindow()
        
        // Tell Flutter to navigate to keyboard shortcuts page
        shortcutChannel.invokeMethod("openKeyboardShortcutsPage", arguments: nil)
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
            // Activate the app first so it can receive keyboard input
            NSApp.activate(ignoringOtherApps: true)
            showFloatingControlBar()
        }
    }
}
