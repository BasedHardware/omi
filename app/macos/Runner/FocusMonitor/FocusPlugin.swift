import Cocoa
import FlutterMacOS
import UserNotifications

/// Flutter plugin that bridges the Focus Monitoring functionality to Dart
@MainActor
public class FocusPlugin: NSObject, FlutterPlugin {

    // MARK: - Properties

    private var methodChannel: FlutterMethodChannel?
    private var eventChannel: FlutterEventChannel?
    private var eventSink: FlutterEventSink?

    private var screenCaptureService: ScreenCaptureService?
    private var windowMonitor: WindowMonitor?
    private var geminiService: GeminiService?
    private var captureTimer: Timer?

    private var isMonitoring = false
    private var currentApp: String?
    private var lastStatus: FocusStatus?

    // MARK: - Plugin Registration

    public static func register(with registrar: FlutterPluginRegistrar) {
        let instance = FocusPlugin()

        // Method channel for commands (start, stop, etc.)
        let methodChannel = FlutterMethodChannel(
            name: "com.omi.focus/methods",
            binaryMessenger: registrar.messenger
        )
        instance.methodChannel = methodChannel
        registrar.addMethodCallDelegate(instance, channel: methodChannel)

        // Event channel for streaming focus events
        let eventChannel = FlutterEventChannel(
            name: "com.omi.focus/events",
            binaryMessenger: registrar.messenger
        )
        instance.eventChannel = eventChannel
        eventChannel.setStreamHandler(instance)

        // Load environment variables
        instance.loadEnvironment()

        log("FocusPlugin registered")
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
            GlowOverlayController.shared.showGlowAroundActiveWindow(colorMode: colorMode)
            result(nil)

        default:
            result(FlutterMethodNotImplemented)
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
                    result(FlutterError(code: "NO_NOTIFICATION_PERMISSION", message: "Notification permission is required for focus monitoring", details: nil))
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
            geminiService = try GeminiService(
                onAlert: { [weak self] message in
                    // Notification is sent directly by GeminiService
                    // This callback is just for Flutter event streaming
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
                        GlowOverlayController.shared.showGlowAroundActiveWindow(colorMode: .focused)
                        self?.sendEventToFlutter(type: "refocus", data: [:])
                    }
                },
                onDistraction: {
                    Task { @MainActor in
                        GlowOverlayController.shared.showGlowAroundActiveWindow(colorMode: .distracted)
                    }
                }
            )
        } catch {
            result(FlutterError(code: "INIT_ERROR", message: error.localizedDescription, details: nil))
            return
        }

        // Get initial app state
        let (appName, _, _) = WindowMonitor.getActiveWindowInfoStatic()
        if let appName = appName {
            currentApp = appName
            geminiService?.onAppSwitch(newApp: appName)
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
            title: "OMI Focus",
            message: "Focus monitoring started",
            applyCooldown: false
        )

        sendEventToFlutter(type: "monitoringStarted", data: [:])
        log("Focus monitoring started via Flutter")

        result(nil)
    }

    private func stopMonitoring(result: @escaping FlutterResult) {
        guard isMonitoring else {
            result(nil)
            return
        }

        // Stop timer
        captureTimer?.invalidate()
        captureTimer = nil

        // Stop window monitor
        windowMonitor?.stop()
        windowMonitor = nil

        // Stop services
        if let service = geminiService {
            Task {
                await service.stop()
            }
        }
        geminiService = nil
        screenCaptureService = nil

        isMonitoring = false
        currentApp = nil
        lastStatus = nil

        NotificationService.shared.sendNotification(
            title: "OMI Focus",
            message: "Focus monitoring stopped",
            applyCooldown: false
        )

        sendEventToFlutter(type: "monitoringStopped", data: [:])
        log("Focus monitoring stopped via Flutter")

        result(nil)
    }

    // MARK: - Frame Capture

    private func onAppActivated(appName: String) {
        guard appName != currentApp else { return }
        currentApp = appName
        geminiService?.onAppSwitch(newApp: appName)

        sendEventToFlutter(type: "appSwitch", data: ["app": appName])

        // Capture immediately on app switch for faster response
        Task { @MainActor in
            await captureFrame()
        }
    }

    private func captureFrame() async {
        guard isMonitoring, let screenCaptureService = screenCaptureService else { return }

        if let jpegData = await screenCaptureService.captureActiveWindowAsync(),
           let appName = currentApp {
            geminiService?.submitFrame(jpegData: jpegData, appName: appName)
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

extension FocusPlugin: FlutterStreamHandler {
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
