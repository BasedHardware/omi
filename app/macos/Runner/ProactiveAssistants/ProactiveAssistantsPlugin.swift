import Cocoa
import FlutterMacOS
import UserNotifications

/// Flutter plugin that bridges the Proactive Assistants functionality to Dart
@MainActor
public class ProactiveAssistantsPlugin: NSObject, FlutterPlugin {

    // MARK: - Singleton

    /// Shared instance for access from native UI (e.g., settings window)
    public static var shared: ProactiveAssistantsPlugin?

    // MARK: - Properties

    private var methodChannel: FlutterMethodChannel?
    private var eventChannel: FlutterEventChannel?
    private var eventSink: FlutterEventSink?

    private var screenCaptureService: ScreenCaptureService?
    private var windowMonitor: WindowMonitor?
    private var focusAssistant: FocusAssistant?
    private var taskAssistant: TaskAssistant?
    private var captureTimer: Timer?
    private var analysisDelayTimer: Timer?
    private var isInDelayPeriod = false

    private(set) var isMonitoring = false
    private var currentApp: String?
    private var currentWindowID: CGWindowID?
    private var currentWindowTitle: String?
    private var lastStatus: FocusStatus?
    private var frameCount = 0

    // MARK: - Plugin Registration

    public static func register(with registrar: FlutterPluginRegistrar) {
        let instance = ProactiveAssistantsPlugin()
        shared = instance

        // Method channel for commands (start, stop, etc.)
        let methodChannel = FlutterMethodChannel(
            name: "com.omi.assistants/methods",
            binaryMessenger: registrar.messenger
        )
        instance.methodChannel = methodChannel
        registrar.addMethodCallDelegate(instance, channel: methodChannel)

        // Event channel for streaming assistant events
        let eventChannel = FlutterEventChannel(
            name: "com.omi.assistants/events",
            binaryMessenger: registrar.messenger
        )
        instance.eventChannel = eventChannel
        eventChannel.setStreamHandler(instance)

        // Load environment variables
        instance.loadEnvironment()

        // Set up the coordinator event callback
        AssistantCoordinator.shared.setEventCallback { [weak instance] type, data in
            instance?.sendEventToFlutter(type: type, data: data)
        }

        log("ProactiveAssistantsPlugin registered")
    }

    // MARK: - Environment Loading

    private func loadEnvironment() {
        let envPaths = [
            Bundle.main.path(forResource: ".env", ofType: nil),
            FileManager.default.currentDirectoryPath + "/.env",
            NSHomeDirectory() + "/.omi.env",
            NSHomeDirectory() + "/.hartford.env"
        ].compactMap { $0 }

        for path in envPaths {
            if let contents = try? String(contentsOfFile: path, encoding: .utf8) {
                for line in contents.components(separatedBy: .newlines) {
                    let parts = line.split(separator: "=", maxSplits: 1)
                    if parts.count == 2 {
                        let key = String(parts[0]).trimmingCharacters(in: .whitespaces)
                        let value = String(parts[1]).trimmingCharacters(in: .whitespaces)
                            .trimmingCharacters(in: CharacterSet(charactersIn: "\"'"))
                        setenv(key, value, 1)
                    }
                }
                log("Loaded environment from: \(path)")
                break
            }
        }
    }

    // MARK: - FlutterPlugin Method Handling

    public func handle(_ call: FlutterMethodCall, result: @escaping FlutterResult) {
        switch call.method {
        case "startMonitoring":
            startMonitoring(result: result)

        case "stopMonitoring":
            stopMonitoring(result: result)

        case "isMonitoring":
            result(isMonitoring)

        case "hasScreenRecordingPermission":
            result(CGPreflightScreenCaptureAccess())

        case "requestScreenRecordingPermission":
            CGRequestScreenCaptureAccess()
            result(nil)

        case "openScreenRecordingSettings":
            ScreenCaptureService.openScreenRecordingPreferences()
            result(nil)

        case "hasNotificationPermission":
            checkNotificationPermission(result: result)

        case "requestNotificationPermission":
            requestNotificationPermission(result: result)

        case "getCurrentStatus":
            result([
                "isMonitoring": isMonitoring,
                "currentApp": currentApp as Any,
                "lastStatus": lastStatus?.rawValue as Any
            ])

        case "triggerGlow":
            // Optional: pass "distracted" to test red glow, defaults to green (focused)
            let args = call.arguments as? [String: Any]
            let colorModeStr = args?["colorMode"] as? String ?? "focused"
            let colorMode: GlowColorMode = colorModeStr == "distracted" ? .distracted : .focused
            OverlayService.shared.showGlowAroundActiveWindow(colorMode: colorMode)
            result(nil)

        case "openSettings":
            SettingsWindow.show()
            result(nil)

        case "getSettings":
            let settings = AssistantSettings.shared
            result([
                "cooldownInterval": settings.cooldownInterval,
                "glowOverlayEnabled": settings.glowOverlayEnabled,
                "analysisDelay": settings.analysisDelay
            ])

        case "getAssistants":
            result([
                [
                    "identifier": "focus",
                    "displayName": "Focus Monitor",
                    "enabled": FocusAssistantSettings.shared.isEnabled
                ],
                [
                    "identifier": "task-extraction",
                    "displayName": "Task Extractor",
                    "enabled": TaskAssistantSettings.shared.isEnabled
                ]
            ])

        case "enableAssistant":
            let args = call.arguments as? [String: Any]
            if let identifier = args?["identifier"] as? String {
                enableAssistant(identifier: identifier, enabled: true)
            }
            result(nil)

        case "disableAssistant":
            let args = call.arguments as? [String: Any]
            if let identifier = args?["identifier"] as? String {
                enableAssistant(identifier: identifier, enabled: false)
            }
            result(nil)

        default:
            result(FlutterMethodNotImplemented)
        }
    }

    // MARK: - Assistant Management

    private func enableAssistant(identifier: String, enabled: Bool) {
        switch identifier {
        case "focus":
            FocusAssistantSettings.shared.isEnabled = enabled
        case "task-extraction":
            TaskAssistantSettings.shared.isEnabled = enabled
        default:
            log("Unknown assistant: \(identifier)")
        }
    }

    // MARK: - Monitoring Control

    private func startMonitoring(result: @escaping FlutterResult) {
        guard !isMonitoring else {
            result(FlutterError(code: "ALREADY_MONITORING", message: "Monitoring is already active", details: nil))
            return
        }

        // Check screen recording permission
        guard CGPreflightScreenCaptureAccess() else {
            result(FlutterError(code: "NO_PERMISSION", message: "Screen recording permission not granted", details: nil))
            return
        }

        // Request notification permission before starting
        UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound, .badge]) { [weak self] granted, error in
            DispatchQueue.main.async {
                if let error = error {
                    log("Notification permission error: \(error.localizedDescription)")
                    result(FlutterError(code: "NOTIFICATION_ERROR", message: error.localizedDescription, details: nil))
                    return
                }

                guard granted else {
                    log("Notification permission denied")
                    result(FlutterError(code: "NO_NOTIFICATION_PERMISSION", message: "Notification permission is required for monitoring", details: nil))
                    return
                }

                log("Notification permission granted")
                self?.continueStartMonitoring(result: result)
            }
        }
    }

    private func continueStartMonitoring(result: @escaping FlutterResult) {
        // Initialize services
        screenCaptureService = ScreenCaptureService()

        do {
            // Initialize Focus Assistant
            focusAssistant = try FocusAssistant(
                onAlert: { [weak self] message in
                    self?.sendEventToFlutter(type: "alert", data: ["message": message])
                },
                onStatusChange: { [weak self] status in
                    Task { @MainActor in
                        self?.lastStatus = status
                        self?.sendEventToFlutter(type: "statusChange", data: ["status": status.rawValue])
                    }
                },
                onRefocus: { [weak self] in
                    Task { @MainActor in
                        OverlayService.shared.showGlowAroundActiveWindow(colorMode: .focused)
                        self?.sendEventToFlutter(type: "refocus", data: [:])
                    }
                },
                onDistraction: {
                    Task { @MainActor in
                        OverlayService.shared.showGlowAroundActiveWindow(colorMode: .distracted)
                    }
                }
            )

            // Register Focus Assistant with coordinator
            if let focus = focusAssistant {
                AssistantCoordinator.shared.register(focus)
            }

            // Initialize Task Assistant
            taskAssistant = try TaskAssistant()

            // Register Task Assistant with coordinator
            if let task = taskAssistant {
                AssistantCoordinator.shared.register(task)
            }

        } catch {
            result(FlutterError(code: "INIT_ERROR", message: error.localizedDescription, details: nil))
            return
        }

        // Get initial app state
        let (appName, _, _) = WindowMonitor.getActiveWindowInfoStatic()
        if let appName = appName {
            currentApp = appName
            AssistantCoordinator.shared.notifyAppSwitch(newApp: appName)
        }

        // Start window monitor for instant app switch detection
        windowMonitor = WindowMonitor { [weak self] appName in
            Task { @MainActor in
                self?.onAppActivated(appName: appName)
            }
        }
        windowMonitor?.start()

        // Start capture timer (every 1 second)
        captureTimer = Timer.scheduledTimer(withTimeInterval: 1.0, repeats: true) { [weak self] _ in
            Task { @MainActor in
                await self?.captureFrame()
            }
        }

        isMonitoring = true

        NotificationService.shared.sendNotification(
            title: "OMI Assistants",
            message: "Monitoring started",
            applyCooldown: false
        )

        sendEventToFlutter(type: "monitoringStarted", data: [:])
        log("Proactive assistants started via Flutter")

        result(nil)
    }

    private func stopMonitoring(result: @escaping FlutterResult) {
        guard isMonitoring else {
            result(nil)
            return
        }

        // Stop timers
        captureTimer?.invalidate()
        captureTimer = nil
        analysisDelayTimer?.invalidate()
        analysisDelayTimer = nil
        isInDelayPeriod = false

        // Stop window monitor
        windowMonitor?.stop()
        windowMonitor = nil

        // Stop assistants
        if let focus = focusAssistant {
            Task {
                await focus.stop()
            }
        }
        if let task = taskAssistant {
            Task {
                await task.stop()
            }
        }

        focusAssistant = nil
        taskAssistant = nil
        screenCaptureService = nil

        isMonitoring = false
        currentApp = nil
        currentWindowID = nil
        currentWindowTitle = nil
        lastStatus = nil
        frameCount = 0

        NotificationService.shared.sendNotification(
            title: "OMI Assistants",
            message: "Monitoring stopped",
            applyCooldown: false
        )

        sendEventToFlutter(type: "monitoringStopped", data: [:])
        log("Proactive assistants stopped via Flutter")

        result(nil)
    }

    // MARK: - Public Monitoring Control (for native UI)

    /// Start monitoring from native UI (e.g., settings window)
    public func startMonitoringFromNative(completion: @escaping (Bool, String?) -> Void) {
        guard !isMonitoring else {
            completion(true, nil)
            return
        }

        // Check screen recording permission
        guard CGPreflightScreenCaptureAccess() else {
            completion(false, "Screen recording permission not granted")
            return
        }

        // Request notification permission before starting
        UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound, .badge]) { [weak self] granted, error in
            DispatchQueue.main.async {
                if let error = error {
                    completion(false, error.localizedDescription)
                    return
                }

                guard granted else {
                    completion(false, "Notification permission is required")
                    return
                }

                self?.continueStartMonitoringFromNative(completion: completion)
            }
        }
    }

    private func continueStartMonitoringFromNative(completion: @escaping (Bool, String?) -> Void) {
        // Initialize services
        screenCaptureService = ScreenCaptureService()

        do {
            focusAssistant = try FocusAssistant(
                onAlert: { [weak self] message in
                    self?.sendEventToFlutter(type: "alert", data: ["message": message])
                },
                onStatusChange: { [weak self] status in
                    Task { @MainActor in
                        self?.lastStatus = status
                        self?.sendEventToFlutter(type: "statusChange", data: ["status": status.rawValue])
                    }
                },
                onRefocus: { [weak self] in
                    Task { @MainActor in
                        OverlayService.shared.showGlowAroundActiveWindow(colorMode: .focused)
                        self?.sendEventToFlutter(type: "refocus", data: [:])
                    }
                },
                onDistraction: {
                    Task { @MainActor in
                        OverlayService.shared.showGlowAroundActiveWindow(colorMode: .distracted)
                    }
                }
            )

            if let focus = focusAssistant {
                AssistantCoordinator.shared.register(focus)
            }

            taskAssistant = try TaskAssistant()

            if let task = taskAssistant {
                AssistantCoordinator.shared.register(task)
            }

        } catch {
            completion(false, error.localizedDescription)
            return
        }

        // Get initial app state
        let (appName, _, _) = WindowMonitor.getActiveWindowInfoStatic()
        if let appName = appName {
            currentApp = appName
            AssistantCoordinator.shared.notifyAppSwitch(newApp: appName)
        }

        // Start window monitor
        windowMonitor = WindowMonitor { [weak self] appName in
            Task { @MainActor in
                self?.onAppActivated(appName: appName)
            }
        }
        windowMonitor?.start()

        // Start capture timer
        captureTimer = Timer.scheduledTimer(withTimeInterval: 1.0, repeats: true) { [weak self] _ in
            Task { @MainActor in
                await self?.captureFrame()
            }
        }

        isMonitoring = true

        NotificationService.shared.sendNotification(
            title: "OMI Assistants",
            message: "Monitoring started",
            applyCooldown: false
        )

        sendEventToFlutter(type: "monitoringStarted", data: [:])
        NotificationCenter.default.post(name: .assistantMonitoringStateDidChange, object: nil)
        log("Proactive assistants started via native UI")

        completion(true, nil)
    }

    /// Stop monitoring from native UI
    public func stopMonitoringFromNative() {
        guard isMonitoring else { return }

        captureTimer?.invalidate()
        captureTimer = nil
        analysisDelayTimer?.invalidate()
        analysisDelayTimer = nil
        isInDelayPeriod = false

        windowMonitor?.stop()
        windowMonitor = nil

        if let focus = focusAssistant {
            Task {
                await focus.stop()
            }
        }
        if let task = taskAssistant {
            Task {
                await task.stop()
            }
        }

        focusAssistant = nil
        taskAssistant = nil
        screenCaptureService = nil

        isMonitoring = false
        currentApp = nil
        currentWindowID = nil
        currentWindowTitle = nil
        lastStatus = nil
        frameCount = 0

        NotificationService.shared.sendNotification(
            title: "OMI Assistants",
            message: "Monitoring stopped",
            applyCooldown: false
        )

        sendEventToFlutter(type: "monitoringStopped", data: [:])
        NotificationCenter.default.post(name: .assistantMonitoringStateDidChange, object: nil)
        log("Proactive assistants stopped via native UI")
    }

    /// Check if screen recording permission is granted
    public var hasScreenRecordingPermission: Bool {
        return CGPreflightScreenCaptureAccess()
    }

    // MARK: - Frame Capture

    private func onAppActivated(appName: String) {
        guard appName != currentApp else { return }
        currentApp = appName
        currentWindowID = nil
        currentWindowTitle = nil  // Reset window title on app switch

        // Notify all assistants
        AssistantCoordinator.shared.notifyAppSwitch(newApp: appName)

        sendEventToFlutter(type: "appSwitch", data: ["app": appName])

        // Start/restart the analysis delay timer
        let delaySeconds = AssistantSettings.shared.analysisDelay

        analysisDelayTimer?.invalidate()
        analysisDelayTimer = nil

        if delaySeconds > 0 {
            isInDelayPeriod = true
            AssistantCoordinator.shared.clearAllPendingWork()
            log("App switch detected, starting \(delaySeconds)s analysis delay")

            analysisDelayTimer = Timer.scheduledTimer(withTimeInterval: TimeInterval(delaySeconds), repeats: false) { [weak self] _ in
                Task { @MainActor in
                    self?.isInDelayPeriod = false
                    self?.analysisDelayTimer = nil
                    log("Analysis delay ended, resuming frame processing")
                }
            }
        } else {
            isInDelayPeriod = false
            Task { @MainActor in
                await captureFrame()
            }
        }
    }

    private func captureFrame() async {
        guard isMonitoring, let screenCaptureService = screenCaptureService else { return }

        // Check for window switch and get window title
        let (_, windowTitle, windowID) = WindowMonitor.getActiveWindowInfoStatic()

        // Track window ID changes
        if let windowID = windowID, windowID != currentWindowID {
            let previousWindowID = currentWindowID
            currentWindowID = windowID

            if previousWindowID != nil {
                onWindowSwitch(windowID: windowID)
            }
        }

        // Track window title changes (e.g., browser tab switches)
        if windowTitle != currentWindowTitle {
            if let title = windowTitle, let oldTitle = currentWindowTitle {
                log("Window title changed: '\(oldTitle)' → '\(title)'")
            }
            currentWindowTitle = windowTitle
        }

        guard !isInDelayPeriod else { return }

        if let jpegData = await screenCaptureService.captureActiveWindowAsync(),
           let appName = currentApp {
            frameCount += 1

            let frame = CapturedFrame(
                jpegData: jpegData,
                appName: appName,
                windowTitle: currentWindowTitle,
                frameNumber: frameCount
            )

            // Distribute to all assistants via coordinator
            AssistantCoordinator.shared.distributeFrame(frame)
        }
    }

    private func onWindowSwitch(windowID: CGWindowID) {
        let delaySeconds = AssistantSettings.shared.analysisDelay

        guard delaySeconds > 0 else { return }

        analysisDelayTimer?.invalidate()
        analysisDelayTimer = nil

        isInDelayPeriod = true
        AssistantCoordinator.shared.clearAllPendingWork()
        log("Window switch detected (ID: \(windowID)), starting \(delaySeconds)s analysis delay")

        analysisDelayTimer = Timer.scheduledTimer(withTimeInterval: TimeInterval(delaySeconds), repeats: false) { [weak self] _ in
            Task { @MainActor in
                self?.isInDelayPeriod = false
                self?.analysisDelayTimer = nil
                log("Analysis delay ended, resuming frame processing")
            }
        }
    }

    // MARK: - Permissions

    private func checkNotificationPermission(result: @escaping FlutterResult) {
        UNUserNotificationCenter.current().getNotificationSettings { settings in
            DispatchQueue.main.async {
                result(settings.authorizationStatus == .authorized)
            }
        }
    }

    private func requestNotificationPermission(result: @escaping FlutterResult) {
        NSApp.activate(ignoringOtherApps: true)

        UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound, .badge]) { granted, error in
            DispatchQueue.main.async {
                if let error = error {
                    result(FlutterError(code: "PERMISSION_ERROR", message: error.localizedDescription, details: nil))
                } else {
                    result(granted)
                }
            }
        }
    }

    // MARK: - Event Streaming

    private func sendEventToFlutter(type: String, data: [String: Any]) {
        guard let eventSink = eventSink else { return }

        var event = data
        event["type"] = type
        event["timestamp"] = ISO8601DateFormatter().string(from: Date())

        DispatchQueue.main.async {
            eventSink(event)
        }
    }
}

// MARK: - FlutterStreamHandler

extension ProactiveAssistantsPlugin: FlutterStreamHandler {
    public func onListen(withArguments arguments: Any?, eventSink events: @escaping FlutterEventSink) -> FlutterError? {
        self.eventSink = events
        log("Flutter event stream connected")
        return nil
    }

    public func onCancel(withArguments arguments: Any?) -> FlutterError? {
        self.eventSink = nil
        log("Flutter event stream disconnected")
        return nil
    }
}

// MARK: - Backward Compatibility Alias

typealias FocusPlugin = ProactiveAssistantsPlugin
