import Cocoa
import UserNotifications

/// Service that manages proactive assistants - screen monitoring, frame capture, and assistant coordination
@MainActor
public class ProactiveAssistantsPlugin: NSObject {

    // MARK: - Singleton

    /// Shared instance
    public static let shared = ProactiveAssistantsPlugin()

    // MARK: - Properties

    private var screenCaptureService: ScreenCaptureService?
    private var windowMonitor: WindowMonitor?
    private var focusAssistant: FocusAssistant?

    /// Public read-only accessor for memory diagnostics
    var currentFocusAssistant: FocusAssistant? { focusAssistant }
    private var taskAssistant: TaskAssistant?
    private var adviceAssistant: AdviceAssistant?
    private var memoryAssistant: MemoryAssistant?
    private var captureTimer: Timer?
    private var analysisDelayTimer: Timer?
    private var isInDelayPeriod = false

    private(set) var isMonitoring = false
    private var isStartingMonitoring = false  // Prevents race condition with async startMonitoring
    private var _hasScreenRecordingPermission: Bool?  // Cached permission state
    private var currentApp: String?
    private var currentWindowID: CGWindowID?
    private var currentWindowTitle: String?
    private var lastStatus: FocusStatus?
    private var frameCount = 0

    // Backpressure: prevents unbounded CGImage accumulation (~24MB each) when video
    // encoding is slower than the capture rate — the primary cause of multi-GB memory growth.
    private(set) var isProcessingRewindFrame = false
    private(set) var droppedFrameCount = 0

    // Failure tracking for screen capture recovery
    private var consecutiveFailures = 0
    private let maxConsecutiveFailures = 5
    private var lastCaptureSucceeded = true
    private var wasMonitoringBeforeSleep = false
    private var wasMonitoringBeforeLock = false
    private var systemEventObservers: [NSObjectProtocol] = []

    // Daily settings state tracking
    private var settingsStateTimer: Timer?

    // Video call throttling: reduce capture frequency when a call app is frontmost
    // to avoid competing with the call app for CPU/GPU (ScreenCaptureKit, encoding, OCR).
    private var videoCallFrameCounter = 0
    private let videoCallThrottleFactor = 5  // Capture 1 out of every 5 frames (effective ~5s interval)

    /// Apps whose primary purpose is video/audio calls.
    private static let videoCallApps: Set<String> = [
        "Microsoft Teams",
        "zoom.us",
        "FaceTime",
        "Webex",
        "Cisco Webex Meetings",
        "GoTo Meeting",
        "GoToMeeting",
    ]

    /// Keywords in browser window titles that indicate a video call.
    private static let videoCallBrowserKeywords: [String] = [
        "Google Meet",
        "meet.google.com",
        "Teams - Microsoft",  // Teams web app
    ]

    /// Browser app names (for window-title-based call detection).
    private static let browserApps: Set<String> = [
        "Google Chrome",
        "Arc",
        "Safari",
        "Firefox",
        "Microsoft Edge",
        "Brave Browser",
        "Opera",
    ]

    // Auto-retry state for transient failures (Exposé, Mission Control, etc.)
    private var isInRecoveryMode = false
    private var recoveryRetryCount = 0
    private let maxRecoveryRetries = 30  // Try up to 30 attempts before giving up
    private let recoveryInterval: TimeInterval = 5.0  // Seconds between recovery attempts

    // Background polling state for extended recovery after initial retry fails
    private var isInBackgroundPolling = false
    private var backgroundPollTimer: Timer?
    private var backgroundPollCount = 0
    private let maxBackgroundPollAttempts = 5  // 5 attempts × 60s = 5 minutes
    private static var hasAutoResetThisSession = false

    // MARK: - Initialization

    private override init() {
        super.init()

        // Load environment variables
        loadEnvironment()

        // Set up the coordinator event callback
        AssistantCoordinator.shared.setEventCallback { [weak self] type, data in
            self?.sendEvent(type: type, data: data)
        }

        // Set up system event observers for sleep/wake/lock recovery
        setupSystemEventObservers()

        log("ProactiveAssistantsPlugin initialized")
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

    // MARK: - Assistant Management

    private func enableAssistant(identifier: String, enabled: Bool) {
        switch identifier {
        case "focus":
            FocusAssistantSettings.shared.isEnabled = enabled
        case "task-extraction":
            TaskAssistantSettings.shared.isEnabled = enabled
        case "advice":
            AdviceAssistantSettings.shared.isEnabled = enabled
        case "memory-extraction":
            MemoryAssistantSettings.shared.isEnabled = enabled
        default:
            log("Unknown assistant: \(identifier)")
        }
    }

    // MARK: - Public Monitoring Control

    /// Start monitoring
    public func startMonitoring(completion: @escaping (Bool, String?) -> Void) {
        // Guard against both active monitoring and pending startup (race condition fix)
        guard !isMonitoring && !isStartingMonitoring else {
            completion(isMonitoring, nil)
            return
        }

        // Set flag synchronously before async call to prevent race condition
        isStartingMonitoring = true

        // Check screen recording permission (and update cache)
        refreshScreenRecordingPermission()
        guard hasScreenRecordingPermission else {
            // Request both traditional TCC and ScreenCaptureKit permissions
            ScreenCaptureService.requestAllScreenCapturePermissions()
            isStartingMonitoring = false
            completion(false, "Screen recording permission not granted")
            return
        }

        // Request notification permission but don't block on it
        // Screen analysis can work without notifications - users just won't get alerts
        UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound, .badge]) { [weak self] granted, error in
            DispatchQueue.main.async {
                if let error = error {
                    let nsError = error as NSError
                    log("Notification permission request error: \(error.localizedDescription) (domain=\(nsError.domain) code=\(nsError.code))")

                    // UNErrorDomain code 1 = notificationsNotAllowed
                    // This happens when LaunchServices has the app marked as launch-disabled,
                    // preventing notification center registration. Repair and retry once.
                    if nsError.domain == "UNErrorDomain" && nsError.code == 1 {
                        AnalyticsManager.shared.notificationRepairTriggered(
                            reason: "launch_disabled_error_startup",
                            previousStatus: "notDetermined",
                            currentStatus: "error_code_1"
                        )
                        Self.repairNotificationRegistration()
                    }
                }

                if !granted {
                    log("Notification permission not granted - screen analysis will work but notifications will be disabled")
                }

                // Continue with monitoring regardless of notification permission
                self?.continueStartMonitoring(completion: completion)
            }
        }
    }

    /// Repair LaunchServices registration when notification authorization fails with "not allowed".
    /// The launch-disabled flag in LaunchServices prevents notification center registration.
    /// Unregistering and re-registering clears the flag, then retries authorization.
    static func repairNotificationRegistration() {
        let appPath = Bundle.main.bundlePath
        let bundleURL = Bundle.main.bundleURL
        log("Repairing LaunchServices registration for notifications: \(appPath)")

        let lsregister = "/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister"

        // Run blocking Process calls on a background thread
        DispatchQueue.global(qos: .utility).async {
            // Unregister to clear stale/launch-disabled entries
            let unregister = Process()
            unregister.executableURL = URL(fileURLWithPath: lsregister)
            unregister.arguments = ["-u", appPath]
            try? unregister.run()
            unregister.waitUntilExit()

            // Force re-register
            let register = Process()
            register.executableURL = URL(fileURLWithPath: lsregister)
            register.arguments = ["-f", appPath]
            try? register.run()
            register.waitUntilExit()

            DispatchQueue.main.async {
                // Also re-register via LSRegisterURL (must be on main thread)
                if let cfURL = bundleURL as CFURL? {
                    LSRegisterURL(cfURL, true)
                }

                log("LaunchServices re-registration complete, retrying notification authorization...")

                // Retry authorization after a short delay
                DispatchQueue.main.asyncAfter(deadline: .now() + 1.0) {
                    NSApp.activate(ignoringOtherApps: true)
                    UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound, .badge]) { granted, error in
                        if let error = error {
                            log("Notification retry after repair failed: \(error.localizedDescription)")
                        } else if granted {
                            log("Notification permission granted after LaunchServices repair")
                        }
                    }
                }
            }
        }
    }

    private func continueStartMonitoring(completion: @escaping (Bool, String?) -> Void) {
        // Report resources before starting heavy monitoring
        ResourceMonitor.shared.reportResourcesNow(context: "before_monitoring_start")

        // Initialize services
        screenCaptureService = ScreenCaptureService()

        do {
            focusAssistant = try FocusAssistant(
                onAlert: { [weak self] message in
                    self?.sendEvent(type: "alert", data: ["message": message])
                },
                onStatusChange: { [weak self] status in
                    Task { @MainActor in
                        self?.lastStatus = status
                        self?.sendEvent(type: "statusChange", data: ["status": status.rawValue])
                    }
                },
                onRefocus: {
                    Task { @MainActor in
                        OverlayService.shared.showGlowAroundActiveWindow(colorMode: .focused)
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

            Task { await TaskDeduplicationService.shared.start() }
            Task { await TaskPrioritizationService.shared.start() }
            Task { await TaskPromotionService.shared.start() }

            adviceAssistant = try AdviceAssistant()

            if let advice = adviceAssistant {
                AssistantCoordinator.shared.register(advice)
            }

            memoryAssistant = try MemoryAssistant()

            if let memory = memoryAssistant {
                AssistantCoordinator.shared.register(memory)
            }

        } catch {
            log("ProactiveAssistantsPlugin: Failed to initialize assistants: \(error.localizedDescription)")
            logError("ProactiveAssistantsPlugin: Assistant initialization failed", error: error)
            isStartingMonitoring = false
            completion(false, error.localizedDescription)
            return
        }

        // Get initial app state
        let (appName, _, _) = WindowMonitor.getActiveWindowInfoStatic()
        if let appName = appName {
            currentApp = appName
            // Update FocusStorage with initial detected app
            FocusStorage.shared.updateDetectedApp(appName)
            AssistantCoordinator.shared.notifyAppSwitch(newApp: appName)
        }

        // Start window monitor
        windowMonitor = WindowMonitor { [weak self] appName in
            Task { @MainActor in
                self?.onAppActivated(appName: appName)
            }
        }
        windowMonitor?.start()

        // Start capture timer (invalidate any orphaned timer first as safety measure)
        captureTimer?.invalidate()
        captureTimer = Timer.scheduledTimer(withTimeInterval: RewindSettings.shared.captureInterval, repeats: true) { [weak self] _ in
            Task { @MainActor in
                await self?.captureFrame()
            }
        }

        isMonitoring = true
        isStartingMonitoring = false

        // Report resources after initialization
        ResourceMonitor.shared.reportResourcesNow(context: "after_monitoring_start")

        sendEvent(type: "monitoringStarted", data: [:])
        AnalyticsManager.shared.monitoringStarted()
        trackSettingsState()
        startSettingsStateTimer()
        NotificationCenter.default.post(
            name: .assistantMonitoringStateDidChange,
            object: nil,
            userInfo: ["isMonitoring": true]
        )
        log("Proactive assistants started")

        completion(true, nil)
    }

    /// Stop monitoring
    public func stopMonitoring() {
        guard isMonitoring else { return }

        captureTimer?.invalidate()
        captureTimer = nil
        analysisDelayTimer?.invalidate()
        analysisDelayTimer = nil
        settingsStateTimer?.invalidate()
        settingsStateTimer = nil
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
        Task { await TaskDeduplicationService.shared.stop() }
        Task { await TaskPromotionService.shared.stop() }
        if let advice = adviceAssistant {
            Task {
                await advice.stop()
            }
        }
        if let memory = memoryAssistant {
            Task {
                await memory.stop()
            }
        }

        focusAssistant = nil
        taskAssistant = nil
        adviceAssistant = nil
        memoryAssistant = nil
        screenCaptureService = nil

        isMonitoring = false
        isStartingMonitoring = false  // Reset in case stop was called during startup
        isProcessingRewindFrame = false
        if droppedFrameCount > 0 {
            log("RewindBackpressure: Session total dropped frames: \(droppedFrameCount)")
        }
        droppedFrameCount = 0
        currentApp = nil
        currentWindowID = nil
        currentWindowTitle = nil
        lastStatus = nil
        frameCount = 0

        // Sync the persistent setting so the UI and auto-start stay in sync
        AssistantSettings.shared.screenAnalysisEnabled = false
        UserDefaults.standard.set(false, forKey: "screenAnalysisEnabled")

        // Clear FocusStorage real-time state
        FocusStorage.shared.clearRealtimeStatus()

        // Report resources after stopping
        ResourceMonitor.shared.reportResourcesNow(context: "after_monitoring_stop")

        sendEvent(type: "monitoringStopped", data: [:])
        AnalyticsManager.shared.monitoringStopped()
        NotificationCenter.default.post(
            name: .assistantMonitoringStateDidChange,
            object: nil,
            userInfo: ["isMonitoring": false]
        )
        log("Proactive assistants stopped")
    }

    /// Toggle monitoring state
    public func toggleMonitoring() {
        if isMonitoring {
            stopMonitoring()
        } else {
            startMonitoring { success, error in
                if !success, let error = error {
                    logError("Failed to start monitoring: \(error)")
                }
            }
        }
    }

    /// Check if screen recording permission is granted
    /// Uses cached value to avoid excessive permission check logging
    public var hasScreenRecordingPermission: Bool {
        if let cached = _hasScreenRecordingPermission {
            return cached
        }
        // First access - check and cache
        let result = ScreenCaptureService.checkPermission()
        _hasScreenRecordingPermission = result
        return result
    }

    /// Refresh the cached screen recording permission state
    public func refreshScreenRecordingPermission() {
        _hasScreenRecordingPermission = ScreenCaptureService.checkPermission()
    }

    /// Get current monitoring status
    var currentStatus: (isMonitoring: Bool, currentApp: String?, lastStatus: FocusStatus?) {
        return (isMonitoring, currentApp, lastStatus)
    }

    // MARK: - Frame Capture

    private func onAppActivated(appName: String) {
        guard appName != currentApp else { return }
        currentApp = appName
        currentWindowID = nil
        currentWindowTitle = nil  // Reset window title on app switch

        // Update FocusStorage immediately with detected app (before analysis)
        FocusStorage.shared.updateDetectedApp(appName)

        // Notify all assistants
        AssistantCoordinator.shared.notifyAppSwitch(newApp: appName)

        sendEvent(type: "appSwitch", data: ["app": appName])

        // Start/restart the analysis delay timer
        let delaySeconds = AssistantSettings.shared.analysisDelay

        analysisDelayTimer?.invalidate()
        analysisDelayTimer = nil

        if delaySeconds > 0 {
            isInDelayPeriod = true
            AssistantCoordinator.shared.clearAllPendingWork()
            log("App switch detected, starting \(delaySeconds)s analysis delay")

            // Update FocusStorage with delay end time
            let delayEndTime = Date().addingTimeInterval(TimeInterval(delaySeconds))
            FocusStorage.shared.updateDelayEndTime(delayEndTime)

            analysisDelayTimer = Timer.scheduledTimer(withTimeInterval: TimeInterval(delaySeconds), repeats: false) { [weak self] _ in
                Task { @MainActor in
                    self?.isInDelayPeriod = false
                    self?.analysisDelayTimer = nil
                    FocusStorage.shared.updateDelayEndTime(nil)
                    log("Analysis delay ended, resuming frame processing")
                }
            }
        } else {
            isInDelayPeriod = false
            FocusStorage.shared.updateDelayEndTime(nil)
            Task { @MainActor in
                await captureFrame()
            }
        }
    }

    private func captureFrame() async {
        guard isMonitoring, let screenCaptureService = screenCaptureService else { return }

        // Skip capture during system modes that block ScreenCaptureKit (Mission Control, Expose, etc.)
        // This avoids burning through consecutive failures and generating unnecessary error events
        if isInSpecialSystemMode() {
            return
        }

        // Get current window info (use real app name, not cached)
        let (realAppName, windowTitle, windowID) = WindowMonitor.getActiveWindowInfoStatic()

        // Check if the current app is excluded from Rewind capture
        let isRewindExcluded = realAppName.map { RewindSettings.shared.isAppExcluded($0) } ?? false

        // Throttle capture when a video call app is frontmost to reduce CPU contention.
        // Captures 1 out of every N frames (e.g., effective ~5s interval at default 1s capture rate).
        if isVideoCallApp(appName: realAppName, windowTitle: windowTitle) {
            videoCallFrameCounter += 1
            if videoCallFrameCounter < videoCallThrottleFactor {
                if videoCallFrameCounter == 1 {
                    log("VideoCallThrottle: Detected call app '\(realAppName ?? "unknown")', throttling capture to 1/\(videoCallThrottleFactor) frames")
                }
                return  // Skip this frame
            }
            // This frame will be captured — reset counter for next cycle
            videoCallFrameCounter = 0
        } else if videoCallFrameCounter > 0 {
            log("VideoCallThrottle: Left call app, resuming normal capture")
            videoCallFrameCounter = 0
        }

        // Unified context switch detection (covers app changes, window ID changes, and title changes)
        // Called BEFORE trackFrame so the coordinator's departing frame is from the previous context
        if let appForCheck = realAppName ?? currentApp {
            let switched = AssistantCoordinator.shared.checkContextSwitch(
                newApp: appForCheck,
                newWindowTitle: windowTitle
            )
            if switched && !isInDelayPeriod {
                let delaySeconds = AssistantSettings.shared.analysisDelay
                if delaySeconds > 0 {
                    isInDelayPeriod = true
                    AssistantCoordinator.shared.clearAllPendingWork()
                    log("Context switch detected, starting \(delaySeconds)s analysis delay")

                    analysisDelayTimer?.invalidate()
                    let delayEndTime = Date().addingTimeInterval(TimeInterval(delaySeconds))
                    FocusStorage.shared.updateDelayEndTime(delayEndTime)

                    analysisDelayTimer = Timer.scheduledTimer(withTimeInterval: TimeInterval(delaySeconds), repeats: false) { [weak self] _ in
                        Task { @MainActor in
                            self?.isInDelayPeriod = false
                            self?.analysisDelayTimer = nil
                            FocusStorage.shared.updateDelayEndTime(nil)
                            log("Analysis delay ended, resuming frame processing")
                        }
                    }
                }
            }
        }

        // Update local window tracking
        if let windowID = windowID {
            currentWindowID = windowID
        }
        currentWindowTitle = windowTitle

        // Use real app name from window info, fall back to cached if unavailable
        let appName = realAppName ?? currentApp

        // Always capture frames (other features may need them)
        // macOS 14+: capture CGImage directly, encode JPEG once for assistants,
        // pass CGImage to RewindIndexer (avoids redundant encode/decode round-trips)
        if #available(macOS 14.0, *) {
            if let cgImage = await screenCaptureService.captureActiveWindowCGImage(),
               let appName = appName {
                if !lastCaptureSucceeded {
                    log("Screen capture recovered after \(consecutiveFailures) failures")
                }
                consecutiveFailures = 0
                lastCaptureSucceeded = true

                frameCount += 1
                let captureTime = Date()

                // Encode JPEG off main actor — CGImageDestinationFinalize is CPU-heavy
                let captureService = screenCaptureService
                let jpegData = await Task.detached(priority: .userInitiated) {
                    captureService.encodeJPEG(from: cgImage)
                }.value
                if let jpegData = jpegData {
                    let frame = CapturedFrame(
                        jpegData: jpegData,
                        appName: appName,
                        windowTitle: currentWindowTitle,
                        frameNumber: frameCount,
                        captureTime: captureTime
                    )

                    // Always track the frame for context switch detection (even during delay)
                    AssistantCoordinator.shared.trackFrame(frame)

                    if !isInDelayPeriod {
                        AssistantCoordinator.shared.distributeFrame(frame)
                    } else {
                        // During delay, still distribute to assistants that need it (e.g. refocus detection)
                        AssistantCoordinator.shared.distributeFrameDuringDelay(frame)
                    }
                }

                // Pass CGImage directly to RewindIndexer (only if not excluded from Rewind)
                // Backpressure: skip this frame if the previous one is still being processed.
                // Without this, fire-and-forget Tasks queue up holding CGImages (~24MB each),
                // causing multi-GB memory growth when encoding can't keep up with capture rate.
                if !isRewindExcluded {
                    if isProcessingRewindFrame {
                        droppedFrameCount += 1
                        if droppedFrameCount == 1 || droppedFrameCount % 30 == 0 {
                            log("RewindBackpressure: Dropped frame (encoder busy), total dropped: \(droppedFrameCount)")
                        }
                    } else {
                        isProcessingRewindFrame = true
                        let windowTitle = self.currentWindowTitle
                        Task { [weak self] in
                            await RewindIndexer.shared.processFrame(
                                cgImage: cgImage,
                                appName: appName,
                                windowTitle: windowTitle,
                                captureTime: captureTime
                            )
                            await MainActor.run {
                                self?.isProcessingRewindFrame = false
                            }
                        }
                    }
                }
            } else {
                consecutiveFailures += 1
                lastCaptureSucceeded = false

                if consecutiveFailures == 1 || consecutiveFailures % 5 == 0 {
                    log("ProactiveAssistantsPlugin: Capture failed (\(consecutiveFailures) consecutive), frontmost: \(getFrontmostAppInfo())")
                }

                if consecutiveFailures >= maxConsecutiveFailures {
                    handleRepeatedCaptureFailures()
                }
                return
            }
        } else if let jpegData = await screenCaptureService.captureActiveWindowAsync(),
           let appName = appName {
            // macOS 13.x fallback: existing JPEG-based path
            if !lastCaptureSucceeded {
                log("Screen capture recovered after \(consecutiveFailures) failures")
            }
            consecutiveFailures = 0
            lastCaptureSucceeded = true

            frameCount += 1

            let frame = CapturedFrame(
                jpegData: jpegData,
                appName: appName,
                windowTitle: currentWindowTitle,
                frameNumber: frameCount
            )

            // Always track the frame for context switch detection (even during delay)
            AssistantCoordinator.shared.trackFrame(frame)

            if !isInDelayPeriod {
                AssistantCoordinator.shared.distributeFrame(frame)
            } else {
                // During delay, still distribute to assistants that need it (e.g. refocus detection)
                AssistantCoordinator.shared.distributeFrameDuringDelay(frame)
            }

            if !isRewindExcluded {
                if isProcessingRewindFrame {
                    droppedFrameCount += 1
                    if droppedFrameCount == 1 || droppedFrameCount % 30 == 0 {
                        log("RewindBackpressure: Dropped frame (encoder busy), total dropped: \(droppedFrameCount)")
                    }
                } else {
                    isProcessingRewindFrame = true
                    Task { [weak self] in
                        await RewindIndexer.shared.processFrame(frame)
                        await MainActor.run {
                            self?.isProcessingRewindFrame = false
                        }
                    }
                }
            }
        } else {
            // Track capture failures
            consecutiveFailures += 1
            lastCaptureSucceeded = false

            // Log first failure and every 5th failure to avoid spam
            if consecutiveFailures == 1 || consecutiveFailures % 5 == 0 {
                log("ProactiveAssistantsPlugin: Capture failed (\(consecutiveFailures) consecutive), frontmost: \(getFrontmostAppInfo())")
            }

            if consecutiveFailures >= maxConsecutiveFailures {
                handleRepeatedCaptureFailures()
            }
        }
    }


    // MARK: - Settings State Tracking

    /// Track current settings state to analytics
    private func trackSettingsState() {
        AnalyticsManager.shared.trackSettingsState(
            screenshotsEnabled: isMonitoring,
            memoryExtractionEnabled: MemoryAssistantSettings.shared.isEnabled,
            memoryNotificationsEnabled: MemoryAssistantSettings.shared.notificationsEnabled
        )
    }

    /// Start a daily timer to report settings state
    private func startSettingsStateTimer() {
        settingsStateTimer?.invalidate()
        settingsStateTimer = Timer.scheduledTimer(withTimeInterval: 86400, repeats: true) { [weak self] _ in
            Task { @MainActor in
                self?.trackSettingsState()
            }
        }
    }

    // MARK: - Event Broadcasting

    private func sendEvent(type: String, data: [String: Any]) {
        var event = data
        event["type"] = type
        event["timestamp"] = ISO8601DateFormatter().string(from: Date())

        // Post notification for any listeners
        NotificationCenter.default.post(
            name: .assistantEvent,
            object: nil,
            userInfo: event
        )
    }

    // MARK: - Utility Methods

    /// Open screen recording preferences
    public func openScreenRecordingPreferences() {
        ScreenCaptureService.openScreenRecordingPreferences()
    }

    /// Trigger glow effect manually (for testing)
    func triggerGlow(colorMode: GlowColorMode = .focused) {
        OverlayService.shared.showGlowAroundActiveWindow(colorMode: colorMode)
    }

    // MARK: - System Event Handling

    /// Set up observers for system sleep/wake and screen lock/unlock events
    private func setupSystemEventObservers() {
        // System about to sleep - track state before sleep
        let sleepObserver = NSWorkspace.shared.notificationCenter.addObserver(
            forName: NSWorkspace.willSleepNotification,
            object: nil,
            queue: .main
        ) { [weak self] _ in
            Task { @MainActor in
                self?.wasMonitoringBeforeSleep = self?.isMonitoring ?? false
                log("ProactiveAssistantsPlugin: System going to sleep, wasMonitoring=\(self?.wasMonitoringBeforeSleep ?? false)")

                // Pause the capture timer while sleeping (same as screen lock)
                self?.captureTimer?.invalidate()
                self?.captureTimer = nil
            }
        }
        systemEventObservers.append(sleepObserver)

        // System wake from sleep
        let wakeObserver = NotificationCenter.default.addObserver(
            forName: .systemDidWake,
            object: nil,
            queue: .main
        ) { [weak self] _ in
            Task { @MainActor in
                self?.handleSystemWake()
            }
        }
        systemEventObservers.append(wakeObserver)

        // Screen locked
        let lockObserver = NotificationCenter.default.addObserver(
            forName: .screenDidLock,
            object: nil,
            queue: .main
        ) { [weak self] _ in
            Task { @MainActor in
                self?.handleScreenLock()
            }
        }
        systemEventObservers.append(lockObserver)

        // Screen unlocked
        let unlockObserver = NotificationCenter.default.addObserver(
            forName: .screenDidUnlock,
            object: nil,
            queue: .main
        ) { [weak self] _ in
            Task { @MainActor in
                self?.handleScreenUnlock()
            }
        }
        systemEventObservers.append(unlockObserver)
    }

    /// Handle system wake from sleep
    private func handleSystemWake() {
        log("ProactiveAssistantsPlugin: System woke from sleep")

        // Reset failure counter
        consecutiveFailures = 0
        lastCaptureSucceeded = true

        // If we were monitoring before sleep, reinitialize capture service and restart timer
        if wasMonitoringBeforeSleep && isMonitoring {
            log("ProactiveAssistantsPlugin: Restarting screen capture after wake")

            // Reinitialize the screen capture service
            screenCaptureService = ScreenCaptureService()

            // Refresh permission state
            refreshScreenRecordingPermission()

            // Restart capture timer after a brief delay to let the system settle
            captureTimer?.invalidate()
            captureTimer = nil
            DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) { [weak self] in
                guard let self = self, self.isMonitoring else { return }
                self.captureTimer = Timer.scheduledTimer(withTimeInterval: RewindSettings.shared.captureInterval, repeats: true) { [weak self] _ in
                    Task { @MainActor in
                        await self?.captureFrame()
                    }
                }
                log("ProactiveAssistantsPlugin: Capture timer restarted after wake")
            }
        }

        wasMonitoringBeforeSleep = false
    }

    /// Handle screen lock - pause capture
    private func handleScreenLock() {
        log("ProactiveAssistantsPlugin: Screen locked - pausing capture")

        wasMonitoringBeforeLock = isMonitoring

        // Pause the capture timer while locked
        captureTimer?.invalidate()
        captureTimer = nil
    }

    /// Handle screen unlock - resume capture
    private func handleScreenUnlock() {
        log("ProactiveAssistantsPlugin: Screen unlocked - resuming capture")

        // Reset failure counter
        consecutiveFailures = 0
        lastCaptureSucceeded = true

        if wasMonitoringBeforeLock && isMonitoring {
            log("ProactiveAssistantsPlugin: Restarting capture timer after unlock")

            // Reinitialize screen capture service to ensure fresh state
            screenCaptureService = ScreenCaptureService()

            // Restart capture timer
            captureTimer = Timer.scheduledTimer(withTimeInterval: RewindSettings.shared.captureInterval, repeats: true) { [weak self] _ in
                Task { @MainActor in
                    await self?.captureFrame()
                }
            }
        } else if wasMonitoringBeforeLock && !isMonitoring {
            // We stopped monitoring while locked, restart it
            log("ProactiveAssistantsPlugin: Restarting monitoring after unlock")
            startMonitoring { success, error in
                if !success, let error = error {
                    log("Failed to restart monitoring after unlock: \(error)")
                }
            }
        }

        wasMonitoringBeforeLock = false
    }

    /// Handle repeated capture failures (likely permission issue)
    private func handleRepeatedCaptureFailures() {
        let frontApp = getFrontmostAppInfo()
        log("ProactiveAssistantsPlugin: Detected \(consecutiveFailures) consecutive capture failures (frontmost: \(frontApp))")

        // Check if we're in a special system mode (Exposé, Mission Control, etc.)
        // These modes temporarily block screen capture but aren't permission issues
        if isInSpecialSystemMode() {
            log("ProactiveAssistantsPlugin: System is in special mode, entering recovery mode instead of stopping")
            enterRecoveryMode()
            return
        }

        // Refresh permission state
        refreshScreenRecordingPermission()

        // Check if permission is actually lost
        if !hasScreenRecordingPermission {
            log("ProactiveAssistantsPlugin: Screen recording permission lost")

            // Post notification for AppState to update UI
            NotificationCenter.default.post(name: .screenCapturePermissionLost, object: nil)

            // Stop monitoring since we can't capture
            stopMonitoring()

            // Send user notification
            NotificationService.shared.sendNotification(
                title: "Screen Recording Permission Required",
                message: "Omi needs screen recording permission to continue monitoring. Please re-enable it in System Settings."
            )
        } else {
            // Permission appears granted but capture is failing
            // This could be a transient issue - enter recovery mode instead of stopping
            log("ProactiveAssistantsPlugin: Capture failing with permission granted, entering recovery mode")
            enterRecoveryMode()
        }
    }

    // MARK: - Video Call Detection

    /// Check if the frontmost app (and optionally window title) indicates an active video call.
    private func isVideoCallApp(appName: String?, windowTitle: String?) -> Bool {
        guard let appName = appName else { return false }

        // Direct match: dedicated video call apps
        if Self.videoCallApps.contains(appName) {
            return true
        }

        // Browser-based calls: check window title for call keywords
        if Self.browserApps.contains(appName), let title = windowTitle {
            let lowercaseTitle = title.lowercased()
            for keyword in Self.videoCallBrowserKeywords {
                if lowercaseTitle.contains(keyword.lowercased()) {
                    return true
                }
            }
        }

        return false
    }

    // MARK: - Special System Mode Detection

    /// Check if the system is in a special mode that blocks screen capture.
    ///
    /// Known modes that block ScreenCaptureKit:
    /// - **Exposé / Mission Control** (F3 or swipe up): Dock owns all windows
    /// - **App Exposé** (swipe down on app): Shows all windows of one app
    /// - **Notification Center**: Slide-in panel
    /// - **Lock Screen**: Captured separately via screenDidLock notification
    /// - **Screen Saver**: Similar to lock screen
    ///
    /// When in these modes, ScreenCaptureKit returns "user declined TCCs" error
    /// even though permission is actually granted. This is a transient state.
    private func isInSpecialSystemMode() -> Bool {
        // Check if Dock is the frontmost app (indicates Exposé/Mission Control)
        if let frontApp = NSWorkspace.shared.frontmostApplication {
            if frontApp.bundleIdentifier == "com.apple.dock" {
                log("SpecialModeDetection: Dock is frontmost app (Exposé/Mission Control active)")
                return true
            }
        }

        // Check for Mission Control windows using CGWindowList
        // When Mission Control is active, Dock creates a window with no name
        guard let windowList = CGWindowListCopyWindowInfo([.optionOnScreenOnly], kCGNullWindowID) as? [[String: Any]] else {
            return false
        }

        for window in windowList {
            guard let ownerName = window[kCGWindowOwnerName as String] as? String else {
                continue
            }

            // Dock window with no name indicates Mission Control/Exposé
            if ownerName == "Dock" {
                let windowName = window[kCGWindowName as String] as? String
                if windowName == nil || windowName?.isEmpty == true {
                    // Check if it's a large window (Mission Control overlay)
                    if let bounds = window[kCGWindowBounds as String] as? [String: CGFloat],
                       let width = bounds["Width"],
                       let height = bounds["Height"],
                       width > 500 && height > 300 {
                        log("SpecialModeDetection: Dock overlay window detected (\(Int(width))x\(Int(height))) - Mission Control/Exposé")
                        return true
                    }
                }
            }

            // Notification Center active
            if ownerName == "NotificationCenter" {
                log("SpecialModeDetection: Notification Center is active")
                return true
            }
        }

        return false
    }

    /// Get the current frontmost app for logging
    private func getFrontmostAppInfo() -> String {
        if let frontApp = NSWorkspace.shared.frontmostApplication {
            return "\(frontApp.localizedName ?? "unknown") (\(frontApp.bundleIdentifier ?? "no-bundle-id"))"
        }
        return "none"
    }

    // MARK: - Recovery Mode

    /// Enter recovery mode - pause capture temporarily and retry
    private func enterRecoveryMode() {
        guard !isInRecoveryMode else { return }

        isInRecoveryMode = true
        recoveryRetryCount = 0

        log("ProactiveAssistantsPlugin: Entering recovery mode, will retry capture periodically")

        // Pause the normal capture timer
        captureTimer?.invalidate()
        captureTimer = nil

        // Start recovery timer - check every 5 seconds if we can capture again
        // Using a slower interval than normal capture to reduce CPU overhead from repeated failed ScreenCaptureKit calls
        captureTimer = Timer.scheduledTimer(withTimeInterval: recoveryInterval, repeats: true) { [weak self] _ in
            Task { @MainActor in
                await self?.attemptRecovery()
            }
        }
    }

    /// Attempt to recover from transient capture failure
    private func attemptRecovery() async {
        recoveryRetryCount += 1

        // Check if system is still in special mode
        if isInSpecialSystemMode() {
            // Still in Exposé/Mission Control, keep waiting
            if recoveryRetryCount % 5 == 0 {
                log("ProactiveAssistantsPlugin: Still in special system mode, waiting... (attempt \(recoveryRetryCount))")
            }

            // Give up after max retries (likely a real issue)
            if recoveryRetryCount >= maxRecoveryRetries {
                log("ProactiveAssistantsPlugin: Recovery timeout in special mode, continuing to wait")
                // Reset counter but keep trying - user might be in Exposé for a while
                recoveryRetryCount = 0
            }
            return
        }

        // Try to capture a frame
        guard let screenCaptureService = screenCaptureService else {
            exitRecoveryMode(success: false)
            return
        }

        if let _ = await screenCaptureService.captureActiveWindowAsync() {
            // Success! Exit recovery mode
            log("ProactiveAssistantsPlugin: Recovery successful after \(recoveryRetryCount) attempts (~\(recoveryRetryCount * Int(recoveryInterval))s), resuming normal capture (frontmost: \(getFrontmostAppInfo()))")
            exitRecoveryMode(success: true)
        } else {
            // Still failing
            if recoveryRetryCount >= maxRecoveryRetries {
                // Give up and show the reset notification
                log("ProactiveAssistantsPlugin: Recovery failed after \(maxRecoveryRetries) attempts")
                exitRecoveryMode(success: false)
            }
        }
    }

    /// Exit recovery mode
    private func exitRecoveryMode(success: Bool) {
        isInRecoveryMode = false
        recoveryRetryCount = 0

        if success {
            // Reset failure counter and resume normal operation
            consecutiveFailures = 0
            lastCaptureSucceeded = true

            // Restart normal capture timer
            captureTimer?.invalidate()
            captureTimer = Timer.scheduledTimer(withTimeInterval: RewindSettings.shared.captureInterval, repeats: true) { [weak self] _ in
                Task { @MainActor in
                    await self?.captureFrame()
                }
            }
        } else {
            // Recovery failed - enter background polling before giving up
            log("ProactiveAssistantsPlugin: Initial recovery failed, entering background polling mode")
            enterBackgroundPollingMode()
        }
    }

    // MARK: - Background Polling (Extended Recovery)

    /// Enter background polling mode - check every 60s for up to 5 minutes
    /// This handles cases where the permission state resolves itself over time
    private func enterBackgroundPollingMode() {
        guard !isInBackgroundPolling else { return }

        isInBackgroundPolling = true
        backgroundPollCount = 0

        log("ProactiveAssistantsPlugin: Starting background polling (every 60s, up to \(maxBackgroundPollAttempts) attempts)")

        // Pause capture timer if still running
        captureTimer?.invalidate()
        captureTimer = nil

        backgroundPollTimer = Timer.scheduledTimer(withTimeInterval: 60, repeats: true) { [weak self] _ in
            Task { @MainActor in
                await self?.backgroundPollAttempt()
            }
        }
    }

    /// Single background poll attempt
    private func backgroundPollAttempt() async {
        backgroundPollCount += 1

        guard let screenCaptureService = screenCaptureService else {
            exitBackgroundPolling(success: false)
            return
        }

        log("ProactiveAssistantsPlugin: Background poll attempt \(backgroundPollCount)/\(maxBackgroundPollAttempts)")

        if let _ = await screenCaptureService.captureActiveWindowAsync() {
            log("ProactiveAssistantsPlugin: Background polling recovered after \(backgroundPollCount) attempts")
            exitBackgroundPolling(success: true)
        } else if backgroundPollCount >= maxBackgroundPollAttempts {
            log("ProactiveAssistantsPlugin: Background polling exhausted, attempting auto-reset")
            exitBackgroundPolling(success: false)
        }
    }

    /// Exit background polling mode
    private func exitBackgroundPolling(success: Bool) {
        isInBackgroundPolling = false
        backgroundPollCount = 0
        backgroundPollTimer?.invalidate()
        backgroundPollTimer = nil

        if success {
            consecutiveFailures = 0
            lastCaptureSucceeded = true

            // Resume normal capture
            captureTimer = Timer.scheduledTimer(withTimeInterval: RewindSettings.shared.captureInterval, repeats: true) { [weak self] _ in
                Task { @MainActor in
                    await self?.captureFrame()
                }
            }
        } else {
            attemptAutoReset()
        }
    }

    /// Attempt automatic tccutil reset + app restart (once per launch)
    private func attemptAutoReset() {
        if Self.hasAutoResetThisSession {
            // Already tried auto-reset this session - fall back to manual notification
            log("ProactiveAssistantsPlugin: Auto-reset already attempted this session, showing notification")

            AnalyticsManager.shared.screenCaptureBrokenDetected()
            NotificationCenter.default.post(name: .screenCaptureKitBroken, object: nil)
            stopMonitoring()

            NotificationService.shared.sendNotification(
                title: NotificationService.screenCaptureResetTitle,
                message: "Permission appears granted but capture is failing. Click to reset and fix this issue."
            )
            return
        }

        Self.hasAutoResetThisSession = true
        log("ProactiveAssistantsPlugin: Performing auto-reset + restart")
        AnalyticsManager.shared.screenCaptureBrokenDetected()
        ScreenCaptureService.resetScreenCapturePermissionAndRestart()
    }
}

// MARK: - Notification Names

extension Notification.Name {
    static let assistantEvent = Notification.Name("assistantEvent")
}

// MARK: - Backward Compatibility Alias

typealias FocusPlugin = ProactiveAssistantsPlugin
typealias MonitoringService = ProactiveAssistantsPlugin
