import SwiftUI
import Combine
import UserNotifications
import AVFoundation
@preconcurrency import ObjectiveC

/// Speaker segment for diarized transcription
struct SpeakerSegment: Identifiable {
    /// Stable identity derived from speaker + start time (unique per segment)
    var id: String { "\(speaker)-\(start)" }
    var speaker: Int
    var text: String
    var start: Double
    var end: Double
}

/// Result of finalizing a conversation
enum FinishConversationResult {
    case saved
    case discarded
    case error(String)
}

@MainActor
class AppState: ObservableObject {
    @AppStorage("hasCompletedOnboarding") var hasCompletedOnboarding = false

    // Transcription state
    @Published var isTranscribing = false
    @Published var isSavingConversation = false
    // currentTranscript is internal-only (not observed by views), so no @Published needed
    private var currentTranscript: String = ""
    @Published var hasMicrophonePermission = false
    @Published var hasSystemAudioPermission = false
    @Published var isSystemAudioSupported = false

    // Audio source (microphone or BLE device)
    @Published var audioSource: AudioSource = .microphone
    /// Tracks the source for the current recording (for API tagging)
    private var currentConversationSource: ConversationSource = .desktop

    // Audio levels moved to AudioLevelMonitor to avoid triggering global re-renders
    // Access via AudioLevelMonitor.shared.microphoneLevel / .systemLevel
    var microphoneAudioLevel: Float { AudioLevelMonitor.shared.microphoneLevel }
    var systemAudioLevel: Float { AudioLevelMonitor.shared.systemLevel }

    // Recording timer moved to RecordingTimer to avoid triggering global re-renders
    // Access via RecordingTimer.shared.duration
    var recordingDuration: TimeInterval { RecordingTimer.shared.duration }

    // Live speaker segments moved to LiveTranscriptMonitor to avoid triggering global re-renders
    // Access via LiveTranscriptMonitor.shared.segments
    var liveSpeakerSegments: [SpeakerSegment] { LiveTranscriptMonitor.shared.segments }

    // Conversation state
    @Published var conversations: [ServerConversation] = []
    @Published var isLoadingConversations: Bool = false
    @Published var conversationsError: String? = nil
    @Published var totalConversationsCount: Int? = nil  // Total count (fetched separately)

    // Conversation filters
    @Published var showStarredOnly: Bool = false
    @Published var selectedDateFilter: Date? = nil
    @Published var selectedFolderId: String? = nil

    // Folders
    @Published var folders: [Folder] = []
    @Published var isLoadingFolders: Bool = false

    // People (speaker voice profiles)
    @Published var people: [Person] = []
    var peopleById: [String: Person] {
        Dictionary(uniqueKeysWithValues: people.map { ($0.id, $0) })
    }

    /// Maps live speaker IDs to person IDs during recording (cleared on finalize)
    @Published var liveSpeakerPersonMap: [Int: String] = [:]

    // Permission states for onboarding
    @Published var hasNotificationPermission = false
    @Published var notificationAlertStyle: UNAlertStyle = .none  // .none, .banner, or .alert
    @Published var hasScreenRecordingPermission = false
    @Published var hasBluetoothPermission = false

    // Track last notification settings for change detection (avoid duplicate analytics)
    private var lastNotificationAuthStatus: String?
    private var lastNotificationAlertStyle: String?
    private var lastNotificationSoundEnabled: Bool?
    private var lastNotificationBadgeEnabled: Bool?
    @Published var isScreenCaptureKitBroken = false  // TCC says yes but ScreenCaptureKit says no
    @Published var hasAutomationPermission = false
    @Published var automationPermissionError: OSStatus = 0  // Non-zero when check fails unexpectedly (e.g. -600 procNotFound)
    private var isCheckingAutomationPermission = false  // Prevent concurrent checks (retry path has a 1s sleep)
    @Published var hasAccessibilityPermission = false
    @Published var isAccessibilityBroken = false  // TCC says yes but AX calls actually fail (common after macOS updates/app re-signs)

    /// True if notifications are enabled but won't show visual banners
    var isNotificationBannerDisabled: Bool {
        hasNotificationPermission && notificationAlertStyle == .none
    }


    /// Returns list of missing permissions that are required for full functionality
    var missingPermissions: [String] {
        var missing: [String] = []
        if !hasMicrophonePermission { missing.append("Microphone") }
        if !hasScreenRecordingPermission || isScreenCaptureKitBroken { missing.append("Screen Recording") }
        if !hasNotificationPermission { missing.append("Notifications") }
        else if isNotificationBannerDisabled { missing.append("Notification Banners") }
        if !hasAccessibilityPermission || isAccessibilityBroken { missing.append("Accessibility") }
        return missing
    }

    /// Check if notification permission was explicitly denied
    func isNotificationPermissionDenied() -> Bool {
        // We need to check synchronously, so use a semaphore pattern
        // This is cached from checkNotificationPermission() calls
        return hasCompletedOnboarding && !hasNotificationPermission
    }

    /// Open notification preferences in System Settings (directly to Omi's settings)
    func openNotificationPreferences() {
        let bundleId = Bundle.main.bundleIdentifier ?? "com.omi.computer-macos"
        if let url = URL(string: "x-apple.systempreferences:com.apple.preference.notifications?id=\(bundleId)") {
            NSWorkspace.shared.open(url)
        }
    }

    /// True if any required permissions are missing
    var hasMissingPermissions: Bool {
        !missingPermissions.isEmpty
    }

    // Transcription services
    private var audioCaptureService: AudioCaptureService?
    private var transcriptionService: TranscriptionService?
    private var systemAudioCaptureService: Any?  // SystemAudioCaptureService (macOS 14.4+)
    private var audioMixer: AudioMixer?

    // Speaker segments for diarized transcription
    private var speakerSegments: [SpeakerSegment] = []

    // Conversation tracking for auto-save
    private var recordingStartTime: Date?
    private var recordingInputDeviceName: String?  // Microphone name used for this recording
    private var maxRecordingTimer: Timer?
    private let maxRecordingDuration: TimeInterval = 4 * 60 * 60  // 4 hours

    // Periodic notification health check timer
    private var notificationHealthTimer: Timer?

    // Crash-safe transcription storage
    private var currentSessionId: Int64?

    // Observers for app lifecycle
    private var willTerminateObserver: NSObjectProtocol?
    private var willSleepObserver: NSObjectProtocol?
    private var didWakeObserver: NSObjectProtocol?
    private var screenLockedObserver: NSObjectProtocol?
    private var screenUnlockedObserver: NSObjectProtocol?
    private var screenCapturePermissionLostObserver: NSObjectProtocol?
    private var screenCaptureKitBrokenObserver: NSObjectProtocol?

    // Track transcription state across sleep/wake cycles
    private var wasTranscribingBeforeSleep = false

    // Debounce timestamps to prevent duplicate system notifications
    private var lastScreenLockTime: Date?
    private var lastScreenUnlockTime: Date?

    // BLE device button handling
    private var buttonStreamTask: Task<Void, Never>?

    // Combine subscriptions
    private var bluetoothStateCancellable: AnyCancellable?

    init() {
        // Load API key from environment or .env file
        loadEnvironment()

        // Setup lifecycle observers for saving conversations
        setupLifecycleObservers()

        // Listen for screen capture permission loss notifications
        screenCapturePermissionLostObserver = NotificationCenter.default.addObserver(
            forName: .screenCapturePermissionLost,
            object: nil,
            queue: .main
        ) { [weak self] _ in
            Task { @MainActor in
                self?.hasScreenRecordingPermission = false
                self?.isScreenCaptureKitBroken = false  // Not broken, just lost
                log("AppState: Screen recording permission lost")
            }
        }

        // Listen for ScreenCaptureKit broken notifications (TCC granted but SCK declined)
        screenCaptureKitBrokenObserver = NotificationCenter.default.addObserver(
            forName: .screenCaptureKitBroken,
            object: nil,
            queue: .main
        ) { [weak self] _ in
            Task { @MainActor in
                self?.hasScreenRecordingPermission = false
                self?.isScreenCaptureKitBroken = true  // Needs reset
                log("AppState: ScreenCaptureKit broken - needs reset")
            }
        }

        // Check if system audio capture is supported (macOS 14.4+)
        // Note: hasSystemAudioPermission stays false until actually tested during onboarding
        if #available(macOS 14.4, *) {
            isSystemAudioSupported = true
        }

        // Note: Bluetooth subscription is initialized lazily via initializeBluetoothIfNeeded()
        // to avoid triggering the permission dialog before the user reaches the Bluetooth step

        // Start periodic notification health check (every 30 min)
        // Detects when macOS silently revokes notification authorization and auto-repairs
        notificationHealthTimer = Timer.scheduledTimer(withTimeInterval: 30 * 60, repeats: true) { [weak self] _ in
            DispatchQueue.main.async {
                self?.checkNotificationPermission()
            }
        }
    }

    /// Initialize Bluetooth manager and subscribe to state changes
    /// Call this only when the user reaches the Bluetooth onboarding step
    func initializeBluetoothIfNeeded() {
        guard bluetoothStateCancellable == nil else {
            log("Bluetooth already initialized, skipping")
            return
        }

        log("Initializing Bluetooth manager...")

        // Also initialize DeviceProvider's Bluetooth bindings
        DeviceProvider.shared.initializeBluetoothBindingsIfNeeded()

        // Subscribe to Bluetooth state changes for reactive permission updates
        bluetoothStateCancellable = BluetoothManager.shared.$bluetoothState
            .receive(on: DispatchQueue.main)
            .sink { [weak self] state in
                guard let self = self else { return }
                let oldValue = self.hasBluetoothPermission
                // poweredOn = ready to use, poweredOff = allowed but BT is off
                let newValue = state == .poweredOn || state == .poweredOff
                log("BLUETOOTH_SUBSCRIPTION: state=\(BluetoothManager.shared.bluetoothStateDescription), stateRaw=\(state.rawValue), auth=\(BluetoothManager.shared.authorizationDescription), granted=\(newValue)")
                if newValue != oldValue {
                    log("Bluetooth permission changed via subscription: \(oldValue) -> \(newValue), state=\(BluetoothManager.shared.bluetoothStateDescription)")
                    self.hasBluetoothPermission = newValue
                }
            }
    }

    /// Setup observers for app quit and system sleep to finalize conversations
    private func setupLifecycleObservers() {
        // App is about to quit
        willTerminateObserver = NotificationCenter.default.addObserver(
            forName: NSApplication.willTerminateNotification,
            object: nil,
            queue: .main
        ) { [weak self] _ in
            guard let self = self else { return }
            Task { @MainActor in
                if self.isTranscribing {
                    log("App terminating - finalizing conversation")
                    _ = await self.finalizeConversation()
                }
            }
        }

        // Computer is about to sleep
        willSleepObserver = NSWorkspace.shared.notificationCenter.addObserver(
            forName: NSWorkspace.willSleepNotification,
            object: nil,
            queue: .main
        ) { [weak self] _ in
            guard let self = self else { return }
            Task { @MainActor in
                self.wasTranscribingBeforeSleep = self.isTranscribing
                if self.isTranscribing {
                    log("Computer sleeping - finalizing conversation (will restart on wake)")
                    _ = await self.finalizeConversation()
                    self.stopAudioCapture()
                    self.clearTranscriptionState()
                }
                // Flush final sync changes before sleep
                await AgentSyncService.shared.stop()
            }
        }

        // Computer woke from sleep
        didWakeObserver = NSWorkspace.shared.notificationCenter.addObserver(
            forName: NSWorkspace.didWakeNotification,
            object: nil,
            queue: .main
        ) { [weak self] _ in
            log("System woke from sleep")
            NotificationCenter.default.post(name: .systemDidWake, object: nil)

            // Restart transcription if it was active before sleep
            Task { @MainActor in
                guard let self = self else { return }
                if self.wasTranscribingBeforeSleep && AssistantSettings.shared.transcriptionEnabled {
                    log("System wake: Restarting transcription (was active before sleep)")
                    // Brief delay to let audio subsystem settle after wake
                    try? await Task.sleep(for: .seconds(2))
                    if !self.isTranscribing {
                        self.startTranscription()
                    }
                }
                self.wasTranscribingBeforeSleep = false
            }
        }

        // Screen locked (debounced - macOS sometimes fires multiple times)
        screenLockedObserver = DistributedNotificationCenter.default().addObserver(
            forName: NSNotification.Name("com.apple.screenIsLocked"),
            object: nil,
            queue: .main
        ) { [weak self] _ in
            Task { @MainActor in
                let now = Date()
                if let lastTime = self?.lastScreenLockTime, now.timeIntervalSince(lastTime) < 1.0 {
                    return // Ignore duplicate within 1 second
                }
                self?.lastScreenLockTime = now
                log("Screen locked")
                NotificationCenter.default.post(name: .screenDidLock, object: nil)
            }
        }

        // Screen unlocked (debounced - macOS sometimes fires multiple times)
        screenUnlockedObserver = DistributedNotificationCenter.default().addObserver(
            forName: NSNotification.Name("com.apple.screenIsUnlocked"),
            object: nil,
            queue: .main
        ) { [weak self] _ in
            Task { @MainActor in
                let now = Date()
                if let lastTime = self?.lastScreenUnlockTime, now.timeIntervalSince(lastTime) < 1.0 {
                    return // Ignore duplicate within 1 second
                }
                self?.lastScreenUnlockTime = now
                log("Screen unlocked")
                NotificationCenter.default.post(name: .screenDidUnlock, object: nil)
            }
        }
    }

    deinit {
        if let observer = willTerminateObserver {
            NotificationCenter.default.removeObserver(observer)
        }
        if let observer = willSleepObserver {
            NSWorkspace.shared.notificationCenter.removeObserver(observer)
        }
        if let observer = didWakeObserver {
            NSWorkspace.shared.notificationCenter.removeObserver(observer)
        }
        if let observer = screenLockedObserver {
            DistributedNotificationCenter.default().removeObserver(observer)
        }
        if let observer = screenUnlockedObserver {
            DistributedNotificationCenter.default().removeObserver(observer)
        }
        if let observer = screenCapturePermissionLostObserver {
            NotificationCenter.default.removeObserver(observer)
        }
        if let observer = screenCaptureKitBrokenObserver {
            NotificationCenter.default.removeObserver(observer)
        }
    }

    private func loadEnvironment() {
        // Try to load from .env file in various locations
        let envPaths = [
            Bundle.main.path(forResource: ".env", ofType: nil),
            FileManager.default.currentDirectoryPath + "/.env",
            NSHomeDirectory() + "/.hartford.env",
            NSHomeDirectory() + "/.omi.env",
            // Explicit paths for development
            "/Users/matthewdi/omi-computer-swift/.env",
            "/Users/matthewdi/omi/backend/.env"
        ].compactMap { $0 }

        for path in envPaths {
            if let contents = try? String(contentsOfFile: path, encoding: .utf8) {
                log("Loading environment from: \(path)")
                for line in contents.components(separatedBy: .newlines) {
                    let parts = line.split(separator: "=", maxSplits: 1)
                    if parts.count == 2 {
                        let key = String(parts[0]).trimmingCharacters(in: .whitespaces)
                        // Skip comments
                        guard !key.hasPrefix("#") else { continue }
                        let value = String(parts[1]).trimmingCharacters(in: .whitespaces)
                            .trimmingCharacters(in: CharacterSet(charactersIn: "\"'"))
                        setenv(key, value, 1)
                        // Log key names (not values for security)
                        if key.contains("API_KEY") || key.contains("KEY") {
                            log("  Set \(key)=***")
                        }
                    }
                }
                // Don't break - load all .env files to merge keys
            }
        }

        // Log final state of important keys
        if ProcessInfo.processInfo.environment["DEEPGRAM_API_KEY"] != nil {
            log("DEEPGRAM_API_KEY is set")
        } else {
            log("WARNING: DEEPGRAM_API_KEY is NOT set")
        }
    }

    func openScreenRecordingPreferences() {
        ScreenCaptureService.openScreenRecordingPreferences()
    }

    func openAutomationPreferences() {
        if let url = URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_Automation") {
            NSWorkspace.shared.open(url)
        }
    }

    func requestNotificationPermission() {
        // First check current authorization status
        UNUserNotificationCenter.current().getNotificationSettings { [weak self] settings in
            DispatchQueue.main.async {
                guard let self = self else { return }

                if settings.authorizationStatus == .notDetermined {
                    // First time - show the system prompt
                    NSApp.activate(ignoringOtherApps: true)
                    UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound, .badge]) { [weak self] granted, error in
                        if let error = error {
                            let nsError = error as NSError
                            log("Notification permission error: \(error) (domain=\(nsError.domain) code=\(nsError.code))")

                            // UNErrorDomain code 1 = notificationsNotAllowed
                            // This happens when LaunchServices has the app marked as launch-disabled,
                            // which prevents the notification center from registering the app.
                            // Fix: unregister from LaunchServices and re-register to clear the flag, then retry.
                            if nsError.domain == "UNErrorDomain" && nsError.code == 1 {
                                DispatchQueue.main.async {
                                    AnalyticsManager.shared.notificationRepairTriggered(
                                        reason: "launch_disabled_error",
                                        previousStatus: "notDetermined",
                                        currentStatus: "error_code_1"
                                    )
                                    self?.repairNotificationRegistrationAndRetry()
                                }
                                return
                            }
                        }
                        DispatchQueue.main.async {
                            self?.checkNotificationPermission()
                        }
                    }
                } else if settings.authorizationStatus == .denied {
                    // Previously denied - open System Settings so user can enable manually
                    self.openNotificationPreferences()
                }
                // If already authorized, checkNotificationPermission() will handle it
            }
        }
    }

    /// Repair LaunchServices registration when notification authorization fails.
    /// The "launch-disabled" flag in LaunchServices prevents the notification center
    /// from registering the app. This unregisters and re-registers to clear the flag.
    private func repairNotificationRegistrationAndRetry() {
        // Use the shared repair utility (also used by ProactiveAssistantsPlugin)
        ProactiveAssistantsPlugin.repairNotificationRegistration()

        // After the repair + retry, update our permission state and open System Settings as fallback
        DispatchQueue.main.asyncAfter(deadline: .now() + 3.0) { [weak self] in
            UNUserNotificationCenter.current().getNotificationSettings { settings in
                DispatchQueue.main.async {
                    let isNowGranted = settings.authorizationStatus == .authorized
                    self?.hasNotificationPermission = isNowGranted
                    if !isNowGranted {
                        log("Notification permission still not granted after repair. Opening System Settings.")
                        self?.openNotificationPreferences()
                    }
                }
            }
        }
    }

    /// Repair notification registration via lsregister, then fall back to System Settings if still broken.
    /// Called from sidebar and settings "Fix" buttons when auth is not authorized.
    func repairNotificationAndFallback() {
        log("Fix button tapped — running lsregister repair for notifications")
        ProactiveAssistantsPlugin.repairNotificationRegistration()

        // Wait for repair + re-authorization, then check if it worked
        DispatchQueue.main.asyncAfter(deadline: .now() + 4.0) { [weak self] in
            UNUserNotificationCenter.current().getNotificationSettings { settings in
                DispatchQueue.main.async {
                    let isNowGranted = settings.authorizationStatus == .authorized
                    self?.hasNotificationPermission = isNowGranted
                    self?.notificationAlertStyle = settings.alertStyle
                    if isNowGranted {
                        log("Notification repair succeeded — auth is now authorized")
                    } else {
                        log("Notification repair didn't restore auth (status=\(settings.authorizationStatus.rawValue)) — opening System Settings")
                        self?.openNotificationPreferences()
                    }
                }
            }
        }
    }

    /// Trigger screen recording permission prompt
    func triggerScreenRecordingPermission() {
        // Request both traditional TCC and ScreenCaptureKit permissions
        ScreenCaptureService.requestAllScreenCapturePermissions()
    }

    /// Trigger automation permission by attempting to use Apple Events
    nonisolated func triggerAutomationPermission() {
        // Run a simple AppleScript to trigger the permission prompt
        // This must be done on a background thread since it's nonisolated
        Task.detached {
            // First, ensure System Events is running — without it, the TCC prompt won't appear
            // and checkAutomationPermission returns -600 (procNotFound)
            let launchScript = NSAppleScript(source: """
                launch application "System Events"
            """)
            var launchError: NSDictionary?
            launchScript?.executeAndReturnError(&launchError)
            if let launchError = launchError {
                log("AUTOMATION_TRIGGER: Failed to launch System Events: \(launchError)")
            } else {
                log("AUTOMATION_TRIGGER: System Events launched successfully")
            }

            // Small delay to let System Events initialize
            try? await Task.sleep(nanoseconds: 500_000_000)

            // Now trigger the actual TCC prompt
            let script = NSAppleScript(source: """
                tell application "System Events"
                    return name of first process whose frontmost is true
                end tell
            """)
            var error: NSDictionary?
            script?.executeAndReturnError(&error)

            if let error = error {
                let errorNum = error[NSAppleScript.errorNumber] as? Int ?? 0
                let errorMsg = error[NSAppleScript.errorMessage] as? String ?? "unknown"
                log("AUTOMATION_TRIGGER: AppleScript failed: \(errorNum) - \(errorMsg)")
            } else {
                log("AUTOMATION_TRIGGER: AppleScript succeeded, permission may have been granted")
            }

            // Re-check permission status before opening settings
            await MainActor.run { [weak self] in
                self?.checkAutomationPermission()
            }

            // Small delay to let the check complete
            try? await Task.sleep(nanoseconds: 300_000_000)

            // Open settings so user can toggle if needed
            await MainActor.run {
                if let url = URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_Automation") {
                    NSWorkspace.shared.open(url)
                }
            }
        }
    }

    // MARK: - Permission Status Checks

    /// Check and update all permission states
    func checkAllPermissions() {
        checkNotificationPermission()
        checkScreenRecordingPermission()
        checkAutomationPermission()
        checkMicrophonePermission()
        checkSystemAudioPermission()
        checkAccessibilityPermission()
        // One-time startup diagnostic for accessibility
        let osVersion = ProcessInfo.processInfo.operatingSystemVersion
        let bundleId = Bundle.main.bundleIdentifier ?? "unknown"
        log("ACCESSIBILITY_STARTUP: bundleId=\(bundleId), macOS=\(osVersion.majorVersion).\(osVersion.minorVersion).\(osVersion.patchVersion), TCC=\(hasAccessibilityPermission), broken=\(isAccessibilityBroken), onboarded=\(hasCompletedOnboarding)")
        // Only check Bluetooth if already initialized (to avoid triggering permission prompt early)
        if bluetoothStateCancellable != nil {
            checkBluetoothPermission()
        }
    }

    /// Check Bluetooth permission status
    /// Bluetooth is considered "granted" if state is poweredOn or poweredOff (allowed but BT off)
    /// IMPORTANT: Only call this after initializeBluetoothIfNeeded() has been called
    func checkBluetoothPermission() {
        // Guard: Only check if Bluetooth has been initialized (to avoid triggering permission prompt early)
        guard bluetoothStateCancellable != nil else {
            log("BLUETOOTH_CHECK: Skipping - Bluetooth not initialized yet")
            return
        }
        let state = BluetoothManager.shared.bluetoothState
        let oldValue = hasBluetoothPermission
        // poweredOn = ready to use, poweredOff = allowed but BT is off
        // unauthorized = denied
        let newValue = state == .poweredOn || state == .poweredOff
        log("BLUETOOTH_CHECK: state=\(BluetoothManager.shared.bluetoothStateDescription), stateRaw=\(state.rawValue), auth=\(BluetoothManager.shared.authorizationDescription), granted=\(newValue)")
        if newValue != oldValue {
            log("Bluetooth permission changed: \(oldValue) -> \(newValue), state=\(BluetoothManager.shared.bluetoothStateDescription)")
        }
        hasBluetoothPermission = newValue
    }

    /// Trigger Bluetooth permission by attempting to scan
    /// On macOS, the permission dialog only appears when actually using Bluetooth
    func triggerBluetoothPermission() {
        // Ensure Bluetooth is initialized first (this is expected to be called from the Bluetooth onboarding step)
        initializeBluetoothIfNeeded()

        log("triggerBluetoothPermission: Starting, state=\(BluetoothManager.shared.bluetoothStateDescription), auth=\(BluetoothManager.shared.authorizationDescription)")
        // Trigger the permission prompt by attempting to scan
        // This bypasses state checks because we specifically want the system dialog
        BluetoothManager.shared.triggerPermissionPrompt()
        // Check permission state after a delay to allow user to respond
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.0) {
            log("triggerBluetoothPermission: After 1s delay, state=\(BluetoothManager.shared.bluetoothStateDescription), auth=\(BluetoothManager.shared.authorizationDescription)")
            self.checkBluetoothPermission()
        }
        // Also check again after 3 seconds in case state updates slowly
        DispatchQueue.main.asyncAfter(deadline: .now() + 3.0) {
            log("triggerBluetoothPermission: After 3s delay, state=\(BluetoothManager.shared.bluetoothStateDescription), auth=\(BluetoothManager.shared.authorizationDescription)")
            self.checkBluetoothPermission()
        }
    }

    /// Check if Bluetooth permission was explicitly denied
    /// Returns false if Bluetooth hasn't been initialized yet (to avoid triggering permission prompt)
    func isBluetoothPermissionDenied() -> Bool {
        // Guard: Only check if Bluetooth has been initialized
        guard bluetoothStateCancellable != nil else {
            return false
        }
        return BluetoothManager.shared.bluetoothState == .unauthorized
    }

    /// Check if Bluetooth is reported as unsupported (may be macOS version issue)
    /// Returns false if Bluetooth hasn't been initialized yet (to avoid triggering permission prompt)
    func isBluetoothUnsupported() -> Bool {
        // Guard: Only check if Bluetooth has been initialized
        guard bluetoothStateCancellable != nil else {
            return false
        }
        return BluetoothManager.shared.bluetoothState == .unsupported
    }

    /// Open Bluetooth preferences in System Settings
    func openBluetoothPreferences() {
        if let url = URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_Bluetooth") {
            NSWorkspace.shared.open(url)
        }
    }

    /// Check notification permission status and alert style
    func checkNotificationPermission() {
        UNUserNotificationCenter.current().getNotificationSettings { settings in
            DispatchQueue.main.async {
                let isNowGranted = settings.authorizationStatus == .authorized
                self.hasNotificationPermission = isNowGranted
                self.notificationAlertStyle = settings.alertStyle

                // Log the current notification settings
                let authStatus = switch settings.authorizationStatus {
                    case .notDetermined: "notDetermined"
                    case .denied: "denied"
                    case .authorized: "authorized"
                    case .provisional: "provisional"
                    case .ephemeral: "ephemeral"
                    @unknown default: "unknown"
                }
                let alertStyleName = switch settings.alertStyle {
                    case .none: "NONE (no banners)"
                    case .banner: "BANNER"
                    case .alert: "ALERT"
                    @unknown default: "unknown"
                }
                log("Notification settings: auth=\(authStatus), alertStyle=\(alertStyleName), sound=\(settings.soundSetting.rawValue), badge=\(settings.badgeSetting.rawValue)")

                // Track notification settings in analytics only when they change
                let soundEnabled = settings.soundSetting == .enabled
                let badgeEnabled = settings.badgeSetting == .enabled
                let settingsChanged = authStatus != self.lastNotificationAuthStatus ||
                                      alertStyleName != self.lastNotificationAlertStyle ||
                                      soundEnabled != self.lastNotificationSoundEnabled ||
                                      badgeEnabled != self.lastNotificationBadgeEnabled

                if settingsChanged {
                    AnalyticsManager.shared.notificationSettingsChecked(
                        authStatus: authStatus,
                        alertStyle: alertStyleName,
                        soundEnabled: soundEnabled,
                        badgeEnabled: badgeEnabled,
                        bannersDisabled: settings.alertStyle == .none
                    )

                    // Detect regression: was authorized, now reverted to notDetermined
                    // This happens on macOS 26+ where the OS silently revokes notification permission
                    if self.lastNotificationAuthStatus == "authorized" && authStatus == "notDetermined" {
                        log("Notification permission REGRESSED from authorized to notDetermined — triggering auto-repair")
                        AnalyticsManager.shared.notificationRepairTriggered(
                            reason: "auth_regression",
                            previousStatus: "authorized",
                            currentStatus: "notDetermined"
                        )
                        self.repairNotificationRegistrationAndRetry()
                    }

                    // Update last known state
                    self.lastNotificationAuthStatus = authStatus
                    self.lastNotificationAlertStyle = alertStyleName
                    self.lastNotificationSoundEnabled = soundEnabled
                    self.lastNotificationBadgeEnabled = badgeEnabled
                }

            }
        }
    }

    /// Check screen recording permission status
    func checkScreenRecordingPermission() {
        let tccGranted = CGPreflightScreenCaptureAccess()
        hasScreenRecordingPermission = tccGranted

        // If TCC is not granted, clear the "broken" flag
        // (broken = TCC granted but SCK failing, not applicable if TCC not granted)
        if !tccGranted {
            isScreenCaptureKitBroken = false
        }
        // If TCC is granted AND broken flag is set, leave it set until reset/restart
    }

    /// Check automation permission without triggering a prompt
    /// Uses AEDeterminePermissionToAutomateTarget to query TCC status for System Events
    func checkAutomationPermission() {
        guard !isCheckingAutomationPermission else { return }
        isCheckingAutomationPermission = true
        Task.detached {
            defer { Task { @MainActor in self.isCheckingAutomationPermission = false } }
            let status = Self.queryAutomationPermissionStatus()

            // noErr (0) = granted, errAEEventNotPermitted (-1743) = denied, -1744 = not determined
            // -600 (procNotFound) = System Events not running — try to launch it and retry
            if status == -600 {
                log("AUTOMATION_CHECK: status=-600 (procNotFound), launching System Events and retrying...")
                let launchScript = NSAppleScript(source: "launch application \"System Events\"")
                var launchError: NSDictionary?
                launchScript?.executeAndReturnError(&launchError)

                // Wait for System Events to initialize
                try? await Task.sleep(nanoseconds: 1_000_000_000)

                let retryStatus = Self.queryAutomationPermissionStatus()
                let hasPermission = retryStatus == noErr
                log("AUTOMATION_CHECK: retry status=\(retryStatus), hasPermission=\(hasPermission)")

                await MainActor.run {
                    self.hasAutomationPermission = hasPermission
                    self.automationPermissionError = hasPermission ? 0 : retryStatus
                }
            } else {
                let hasPermission = status == noErr
                log("AUTOMATION_CHECK: status=\(status), hasPermission=\(hasPermission)")

                await MainActor.run {
                    self.hasAutomationPermission = hasPermission
                    // Track unexpected errors (not denied/not-determined, which are normal states)
                    self.automationPermissionError = (status == noErr || status == -1743 || status == -1744) ? 0 : status
                }
            }
        }
    }

    /// Query the TCC automation permission status for System Events without triggering a prompt
    nonisolated private static func queryAutomationPermissionStatus() -> OSStatus {
        let bundleIDString = "com.apple.systemevents"
        var addressDesc = AEAddressDesc()

        let status: OSStatus = bundleIDString.withCString { cString in
            AECreateDesc(typeApplicationBundleID, cString, strlen(cString), &addressDesc)
            let result = AEDeterminePermissionToAutomateTarget(
                &addressDesc,
                typeWildCard,
                typeWildCard,
                false // askUserIfNeeded = false → never shows dialog
            )
            AEDisposeDesc(&addressDesc)
            return result
        }

        return status
    }

    /// Check accessibility permission status
    /// AXIsProcessTrusted() can return stale data after macOS updates or app re-signs,
    /// so we also do a functional AX test to detect the "broken" state.
    func checkAccessibilityPermission() {
        let tccGranted = AXIsProcessTrusted()
        let previouslyGranted = hasAccessibilityPermission

        if tccGranted {
            hasAccessibilityPermission = true

            // Log transitions
            if !previouslyGranted {
                let bundleId = Bundle.main.bundleIdentifier ?? "unknown"
                log("ACCESSIBILITY_CHECK: Permission granted (bundleId=\(bundleId))")
            }

            // TCC says yes — verify with an actual AX call
            let broken = !testAccessibilityPermission()
            if broken != isAccessibilityBroken {
                isAccessibilityBroken = broken
                if broken {
                    log("ACCESSIBILITY_CHECK: TCC says granted but AX calls fail — stuck/broken state detected")
                } else {
                    log("ACCESSIBILITY_CHECK: AX calls working normally")
                }
            }
        } else {
            // AXIsProcessTrusted() says not granted — but on macOS 26 this may be stale.
            // Probe via event tap which checks the live TCC database.
            if probeAccessibilityViaEventTap() {
                log("ACCESSIBILITY_CHECK: AXIsProcessTrusted() returned false but event tap succeeded — stale cache detected")
                let axWorks = testAccessibilityPermission()
                hasAccessibilityPermission = true
                if !axWorks {
                    isAccessibilityBroken = true
                    log("ACCESSIBILITY_CHECK: Event tap OK but AX calls fail — marking as broken")
                } else {
                    isAccessibilityBroken = false
                    log("ACCESSIBILITY_CHECK: Permission confirmed via event tap probe, AX calls working")
                }
            } else {
                // Event tap also failed — permission genuinely not granted
                if previouslyGranted {
                    let bundleId = Bundle.main.bundleIdentifier ?? "unknown"
                    log("ACCESSIBILITY_CHECK: Permission revoked (bundleId=\(bundleId))")
                }
                hasAccessibilityPermission = false
                isAccessibilityBroken = false
            }
        }
    }

    /// Test if Accessibility API actually works by attempting a real AX call.
    /// Returns true if AX calls succeed, false if permission is stuck/broken.
    private func testAccessibilityPermission() -> Bool {
        guard let frontApp = NSWorkspace.shared.frontmostApplication else {
            // No frontmost app to test against — can't determine, assume OK
            return true
        }

        let appElement = AXUIElementCreateApplication(frontApp.processIdentifier)
        var focusedWindow: CFTypeRef?
        let result = AXUIElementCopyAttributeValue(appElement, kAXFocusedWindowAttribute as CFString, &focusedWindow)

        // .success or .noValue (app has no windows) both mean AX is working
        // .cannotComplete or .apiDisabled mean the permission is stuck
        switch result {
        case .success, .noValue, .notImplemented, .attributeUnsupported:
            return true
        case .apiDisabled:
            log("ACCESSIBILITY_CHECK: AXError.apiDisabled — permission stuck (tested against pid \(frontApp.processIdentifier), app: \(frontApp.localizedName ?? "unknown"))")
            return false
        case .cannotComplete:
            log("ACCESSIBILITY_CHECK: AXError.cannotComplete — permission may be stuck (tested against pid \(frontApp.processIdentifier), app: \(frontApp.localizedName ?? "unknown"))")
            return false
        default:
            log("ACCESSIBILITY_CHECK: AXError code \(result.rawValue) from app \(frontApp.localizedName ?? "unknown") — not permission-related, treating as OK")
            return true
        }
    }

    /// Probe accessibility permission by attempting to create a CGEvent tap.
    /// Unlike AXIsProcessTrusted(), event tap creation checks the live TCC database,
    /// bypassing the per-process cache that can go stale on macOS 26 (Tahoe).
    private func probeAccessibilityViaEventTap() -> Bool {
        let tap = CGEvent.tapCreate(
            tap: .cgSessionEventTap,
            place: .tailAppendEventTap,
            options: .listenOnly,
            eventsOfInterest: CGEventMask(1 << CGEventType.mouseMoved.rawValue),
            callback: { _, _, event, _ in Unmanaged.passRetained(event) },
            userInfo: nil
        )
        if let tap = tap {
            CFMachPortInvalidate(tap)
            return true
        }
        return false
    }

    /// Check if accessibility permission was explicitly denied
    func isAccessibilityPermissionDenied() -> Bool {
        return hasCompletedOnboarding && (!hasAccessibilityPermission || isAccessibilityBroken)
    }

    /// Trigger accessibility permission prompt
    func triggerAccessibilityPermission() {
        let osVersion = ProcessInfo.processInfo.operatingSystemVersion
        let bundleId = Bundle.main.bundleIdentifier ?? "unknown"
        log("ACCESSIBILITY_TRIGGER: User clicked Grant Access — bundleId=\(bundleId), macOS \(osVersion.majorVersion).\(osVersion.minorVersion).\(osVersion.patchVersion)")

        // This will prompt the user if not already trusted
        let options = [kAXTrustedCheckOptionPrompt.takeUnretainedValue() as String: true] as CFDictionary
        let trusted = AXIsProcessTrustedWithOptions(options)
        if trusted {
            hasAccessibilityPermission = true
        }
        // Don't set hasAccessibilityPermission = false here — the API may return
        // stale data on macOS 26. Let checkAccessibilityPermission() handle detection
        // via the event tap probe on the next poll cycle.
        log("ACCESSIBILITY_TRIGGER: AXIsProcessTrustedWithOptions returned \(trusted)")

        // On macOS Sequoia+, AXIsProcessTrustedWithOptions no longer shows a visible dialog,
        // so explicitly open System Settings to the Accessibility pane
        if !trusted {
            log("ACCESSIBILITY_TRIGGER: Not trusted, opening System Settings Accessibility pane")
            openAccessibilityPreferences()
        }
    }

    /// Open Accessibility preferences in System Settings
    func openAccessibilityPreferences() {
        if let url = URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility") {
            NSWorkspace.shared.open(url)
        }
    }

    /// Reset accessibility permission (requires terminal command)
    nonisolated func resetAccessibilityPermissionDirect(shouldRestart: Bool = false) -> Bool {
        let bundleId = Bundle.main.bundleIdentifier ?? "com.omi.computer-macos"
        log("Resetting accessibility permission for \(bundleId) via tccutil...")

        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/tccutil")
        process.arguments = ["reset", "Accessibility", bundleId]

        do {
            try process.run()
            process.waitUntilExit()
            let success = process.terminationStatus == 0
            log("tccutil reset completed with exit code: \(process.terminationStatus)")

            if success && shouldRestart {
                restartApp()
            }

            return success
        } catch {
            log("Failed to run tccutil: \(error)")
            return false
        }
    }

    /// Reset accessibility permission via tccutil and restart the app.
    /// Mirrors ScreenCaptureService.resetScreenCapturePermissionAndRestart().
    func resetAccessibilityPermissionAndRestart() {
        if UpdaterViewModel.isUpdateInProgress {
            log("Sparkle update in progress, skipping accessibility reset restart")
            return
        }

        Task.detached { [weak self] in
            guard let self = self else { return }
            let success = self.resetAccessibilityPermissionDirect(shouldRestart: false)

            await MainActor.run {
                if success {
                    log("Accessibility permission reset, restarting app...")
                    self.restartApp()
                } else {
                    log("Accessibility permission reset failed")
                }
            }
        }
    }

    private func showPermissionAlert() {
        let alert = NSAlert()
        alert.messageText = "Permission Required"
        alert.informativeText = "Screen Recording permission is needed.\n\nClick 'Grant Screen Permission' in the menu, then add this app and restart."
        alert.alertStyle = .warning
        alert.addButton(withTitle: "OK")
        alert.runModal()
    }

    private func showAlert(title: String, message: String) {
        let alert = NSAlert()
        alert.messageText = title
        alert.informativeText = message
        alert.alertStyle = .warning
        alert.addButton(withTitle: "OK")
        alert.runModal()
    }

    // MARK: - Transcription

    /// Toggle transcription on/off
    func toggleTranscription() {
        if isTranscribing {
            stopTranscription()
        } else {
            startTranscription()
        }
    }

    /// Start real-time transcription
    /// - Parameter source: Audio source to use (defaults to current audioSource setting)
    func startTranscription(source: AudioSource? = nil) {
        guard !isTranscribing else { return }

        // Use provided source or fall back to current setting
        let effectiveSource = source ?? audioSource

        // For BLE device, check if device is connected
        if effectiveSource == .bleDevice {
            guard DeviceProvider.shared.isConnected else {
                showAlert(title: "Device Not Connected", message: "Please connect a wearable device first.")
                return
            }
        } else {
            // For microphone, check permission
            guard AudioCaptureService.checkPermission() else {
                requestMicrophonePermission()
                return
            }
        }

        do {
            // Get effective language from settings (handles auto-detect vs single language)
            let effectiveLanguage = AssistantSettings.shared.effectiveTranscriptionLanguage
            let vocabulary = AssistantSettings.shared.effectiveVocabulary
            log("Transcription: Using language=\(effectiveLanguage) (autoDetect=\(AssistantSettings.shared.transcriptionAutoDetect), selected=\(AssistantSettings.shared.transcriptionLanguage))")
            log("Transcription: Custom vocabulary: \(vocabulary.joined(separator: ", "))")

            // Initialize transcription service with language and vocabulary
            transcriptionService = try TranscriptionService(language: effectiveLanguage, vocabulary: vocabulary)

            // Set conversation source based on audio source
            if effectiveSource == .bleDevice, let device = DeviceProvider.shared.connectedDevice {
                currentConversationSource = ConversationSource.from(deviceType: device.type)
                recordingInputDeviceName = device.displayName
            } else {
                currentConversationSource = .desktop
                recordingInputDeviceName = AudioCaptureService.getCurrentMicrophoneName()
            }

            // Initialize audio services based on source
            if effectiveSource == .microphone {
                // Initialize audio capture service
                audioCaptureService = AudioCaptureService()

                // Initialize audio mixer for combining mic and system audio
                audioMixer = AudioMixer()

                // Initialize system audio capture if supported (macOS 14.4+)
                if #available(macOS 14.4, *) {
                    systemAudioCaptureService = SystemAudioCaptureService()
                    log("Transcription: System audio capture initialized (macOS 14.4+)")
                } else {
                    log("Transcription: System audio capture not available (requires macOS 14.4+)")
                }
            }
            // For BLE device, BleAudioService will be used in startAudioCapture

            // Start transcription service first
            transcriptionService?.start(
                onTranscript: { [weak self] segment in
                    Task { @MainActor in
                        self?.handleTranscriptSegment(segment)
                    }
                },
                onError: { [weak self] error in
                    Task { @MainActor in
                        logError("Transcription error", error: error)
                        AnalyticsManager.shared.recordingError(error: error.localizedDescription)
                        self?.stopTranscription()
                    }
                },
                onConnected: { [weak self] in
                    Task { @MainActor in
                        log("Transcription: Connected to DeepGram")
                        // Start audio capture once connected
                        await self?.startAudioCapture(source: effectiveSource)
                    }
                },
                onDisconnected: {
                    log("Transcription: Disconnected from DeepGram")
                }
            )

            isTranscribing = true
            audioSource = effectiveSource
            currentTranscript = ""
            speakerSegments = []
            liveSpeakerPersonMap = [:]
            LiveTranscriptMonitor.shared.clear()
            recordingStartTime = Date()
            AudioLevelMonitor.shared.reset()
            RecordingTimer.shared.start()

            log("Transcription: Using source: \(effectiveSource.rawValue), device: \(recordingInputDeviceName ?? "Unknown")")

            // Create crash-safe DB session for persistence
            Task {
                do {
                    let sessionId = try await TranscriptionStorage.shared.startSession(
                        source: currentConversationSource.rawValue,
                        language: effectiveLanguage,
                        timezone: TimeZone.current.identifier,
                        inputDeviceName: recordingInputDeviceName
                    )
                    await MainActor.run {
                        self.currentSessionId = sessionId
                        // Start live notes session
                        LiveNotesMonitor.shared.startSession(sessionId: sessionId)
                    }
                    log("Transcription: Created DB session \(sessionId)")
                } catch {
                    logError("Transcription: Failed to create DB session", error: error)
                    // Non-fatal - continue recording even if DB fails
                }
            }

            // Start 4-hour max recording timer
            maxRecordingTimer = Timer.scheduledTimer(withTimeInterval: maxRecordingDuration, repeats: false) { [weak self] _ in
                Task { @MainActor in
                    guard let self = self, self.isTranscribing else { return }
                    log("Transcription: 4-hour limit reached - finalizing conversation")
                    _ = await self.finalizeConversation()
                    // Start a new recording session automatically
                    self.stopAudioCapture()
                    self.clearTranscriptionState()
                    self.startTranscription()
                }
            }

            // Track transcription started
            AnalyticsManager.shared.transcriptionStarted()

            log("Transcription: Starting...")

        } catch {
            AnalyticsManager.shared.recordingError(error: error.localizedDescription)
            showAlert(title: "Transcription Error", message: error.localizedDescription)
        }
    }

    /// Start audio capture and pipe to transcription service
    /// - Parameter source: Audio source to capture from
    private func startAudioCapture(source: AudioSource = .microphone) async {
        if source == .bleDevice {
            // Use BLE device audio
            await startBleAudioCapture()
        } else {
            // Use microphone (+ optional system audio)
            startMicrophoneAudioCapture()
        }
    }

    /// Start microphone audio capture (original implementation)
    private func startMicrophoneAudioCapture() {
        guard let audioCaptureService = audioCaptureService,
              let audioMixer = audioMixer else { return }

        // Start the audio mixer - it will send stereo audio to transcription service
        audioMixer.start { [weak self] stereoData in
            self?.transcriptionService?.sendAudio(stereoData)
        }

        do {
            // Start microphone capture - sends to mixer channel 0 (left/user)
            try audioCaptureService.startCapture(
                onAudioChunk: { [weak self] audioData in
                    self?.audioMixer?.setMicAudio(audioData)
                },
                onAudioLevel: { level in
                    // Use dedicated monitor to avoid triggering AppState re-renders
                    AudioLevelMonitor.shared.updateMicrophoneLevel(level)
                }
            )
            log("Transcription: Microphone capture started")

            // Start system audio capture if available (macOS 14.4+)
            if #available(macOS 14.4, *) {
                if let systemService = systemAudioCaptureService as? SystemAudioCaptureService {
                    do {
                        try systemService.startCapture(
                            onAudioChunk: { [weak self] audioData in
                                self?.audioMixer?.setSystemAudio(audioData)
                            },
                            onAudioLevel: { level in
                                // Use dedicated monitor to avoid triggering AppState re-renders
                                AudioLevelMonitor.shared.updateSystemLevel(level)
                            }
                        )
                        log("Transcription: System audio capture started")
                    } catch {
                        // System audio is optional - continue with mic only
                        logError("Transcription: System audio capture failed (continuing with mic only)", error: error)
                    }
                }
            }

            log("Transcription: Audio capture started (multichannel)")
        } catch {
            logError("Transcription: Failed to start audio capture", error: error)
            stopTranscription()
        }
    }

    /// Start BLE device audio capture
    private func startBleAudioCapture() async {
        guard let connection = DeviceProvider.shared.activeConnection,
              let transcriptionService = transcriptionService else {
            logError("Transcription: No device connection or transcription service", error: nil)
            stopTranscription()
            return
        }

        // Start BLE audio processing and pipe directly to transcription
        await BleAudioService.shared.startProcessing(
            from: connection,
            transcriptionService: transcriptionService,
            audioDataHandler: { _ in
                // Audio level is updated by BleAudioService
                Task { @MainActor in
                    AudioLevelMonitor.shared.updateMicrophoneLevel(BleAudioService.shared.audioLevel)
                }
            }
        )

        // Start listening for button events
        startButtonEventListener()

        log("Transcription: BLE audio capture started (device: \(connection.device.displayName))")
    }

    /// Start listening for button events from BLE device
    private func startButtonEventListener() {
        guard let buttonStream = DeviceProvider.shared.getButtonStream() else {
            log("Transcription: Device does not support button events")
            return
        }

        buttonStreamTask?.cancel()
        buttonStreamTask = Task { [weak self] in
            do {
                for try await buttonState in buttonStream {
                    self?.handleButtonEvent(buttonState)
                }
            } catch {
                log("Transcription: Button stream ended: \(error.localizedDescription)")
            }
        }
    }

    /// Handle button events from BLE device
    private func handleButtonEvent(_ buttonState: [UInt8]) {
        guard !buttonState.isEmpty else { return }

        let state = buttonState[0]
        log("Transcription: Device button event: \(state)")

        switch state {
        case 1:
            // Single tap - could be used for voice command mode (future feature)
            log("Transcription: Single tap - no action configured")

        case 2:
            // Double tap - finalize conversation and continue recording
            log("Transcription: Double tap - finalizing conversation")
            Task {
                _ = await finalizeConversation()
                clearTranscriptionState()
                // Restart with same source
                startTranscription(source: audioSource)
            }

        case 3:
            // Long press - stop transcription completely
            log("Transcription: Long press - stopping transcription")
            stopTranscription()

        default:
            log("Transcription: Unknown button state: \(state)")
        }
    }

    /// Stop button event listener
    private func stopButtonEventListener() {
        buttonStreamTask?.cancel()
        buttonStreamTask = nil
    }

    /// Stop real-time transcription and finalize the conversation
    func stopTranscription() {
        // Immediately stop audio capture but show saving state
        stopAudioCapture()
        isSavingConversation = true

        Task {
            _ = await finalizeConversation()
            isSavingConversation = false
            clearTranscriptionState()

            // Refresh conversations after stopping
            await loadConversations()
        }
    }

    /// Finish the current conversation and keep recording for a new one
    func finishConversation() async -> FinishConversationResult {
        guard !speakerSegments.isEmpty else {
            log("Transcription: No segments to finish")
            return .discarded
        }

        log("Transcription: Finishing conversation, keeping recording active")

        let result = await finalizeConversation()

        // Clear segments for the next conversation but keep recording
        speakerSegments = []
        liveSpeakerPersonMap = [:]
        LiveTranscriptMonitor.shared.clear()
        LiveNotesMonitor.shared.endSession()
        LiveNotesMonitor.shared.clear()

        // Reset the recording start time for the next conversation
        recordingStartTime = Date()
        RecordingTimer.shared.restart()

        // Restart the 4-hour max recording timer
        maxRecordingTimer?.invalidate()
        maxRecordingTimer = Timer.scheduledTimer(withTimeInterval: maxRecordingDuration, repeats: false) { [weak self] _ in
            Task { @MainActor in
                guard let self = self, self.isTranscribing else { return }
                log("Transcription: 4-hour limit reached - finalizing conversation")
                _ = await self.finalizeConversation()
                self.stopAudioCapture()
                self.clearTranscriptionState()
                self.startTranscription()
            }
        }

        // Start a new DB session for the next conversation
        let lang = AssistantSettings.shared.effectiveTranscriptionLanguage
        Task {
            do {
                let sessionId = try await TranscriptionStorage.shared.startSession(
                    source: currentConversationSource.rawValue,
                    language: lang,
                    timezone: TimeZone.current.identifier,
                    inputDeviceName: recordingInputDeviceName
                )
                await MainActor.run {
                    self.currentSessionId = sessionId
                    LiveNotesMonitor.shared.startSession(sessionId: sessionId)
                }
                log("Transcription: Created new DB session \(sessionId) for next conversation")
            } catch {
                logError("Transcription: Failed to create DB session for next conversation", error: error)
            }
        }

        // Refresh the conversations list to show the new conversation
        await loadConversations()

        log("Transcription: Ready for next conversation")
        return result
    }

    /// Stop audio capture services (but keep transcript data for saving)
    private func stopAudioCapture() {
        // Cancel timers
        maxRecordingTimer?.invalidate()
        maxRecordingTimer = nil
        RecordingTimer.shared.stop()

        // Reset audio levels
        AudioLevelMonitor.shared.reset()

        // Stop BLE audio if active
        if audioSource == .bleDevice {
            BleAudioService.shared.stopProcessing()
            stopButtonEventListener()
        }

        // Stop system audio capture first (if available)
        if #available(macOS 14.4, *) {
            if let systemService = systemAudioCaptureService as? SystemAudioCaptureService {
                systemService.stopCapture()
            }
        }
        systemAudioCaptureService = nil

        // Stop microphone capture
        audioCaptureService?.stopCapture()
        audioCaptureService = nil

        // Stop audio mixer
        audioMixer?.stop()
        audioMixer = nil

        // Stop transcription service
        transcriptionService?.stop()
        transcriptionService = nil

        isTranscribing = false
    }

    /// Clear transcription state after saving
    private func clearTranscriptionState() {
        let wordCount = currentTranscript.split(separator: " ").count

        log("Transcription: Final segments count: \(speakerSegments.count)")

        // End live notes session
        LiveNotesMonitor.shared.endSession()

        // Clear segments after finalization
        speakerSegments = []
        liveSpeakerPersonMap = [:]
        LiveTranscriptMonitor.shared.clear()
        LiveNotesMonitor.shared.clear()
        recordingStartTime = nil
        currentSessionId = nil

        // Track transcription stopped
        AnalyticsManager.shared.transcriptionStopped(wordCount: wordCount)

        log("Transcription: Stopped")
    }

    // MARK: - Conversations

    /// Load conversations - first from local cache (instant), then from API (background refresh)
    func loadConversations() async {
        guard !isLoadingConversations else { return }

        isLoadingConversations = true
        conversationsError = nil

        // Step 1: Load from local cache first (instant display)
        // Use timeout to avoid blocking UI if database is initializing (e.g. recovery)
        do {
            let cachedConversations = try await withThrowingTaskGroup(of: [ServerConversation].self) { group in
                group.addTask {
                    try await TranscriptionStorage.shared.getLocalConversations(
                        limit: 50,
                        starredOnly: self.showStarredOnly,
                        folderId: self.selectedFolderId
                    )
                }
                group.addTask {
                    try await Task.sleep(nanoseconds: 3_000_000_000) // 3 second timeout
                    throw CancellationError()
                }
                let result = try await group.next()!
                group.cancelAll()
                return result
            }

            if !cachedConversations.isEmpty {
                conversations = cachedConversations
                log("Conversations: Loaded \(cachedConversations.count) from local cache (instant)")

                // Get local count
                let localCount = try await TranscriptionStorage.shared.getLocalConversationsCount(starredOnly: showStarredOnly)
                totalConversationsCount = localCount

                // Stop loading state so UI shows cached data immediately
                isLoadingConversations = false
                // Notify sidebar immediately so loading indicator clears with cached data
                NotificationCenter.default.post(name: .conversationsPageDidLoad, object: nil)
            }
        } catch {
            log("Conversations: Local cache unavailable, falling back to API")
            // Continue to API fetch even if local fails
        }

        // Step 2: Fetch from API in background to get fresh data
        // Calculate date range if date filter is set
        let startDate: Date?
        let endDate: Date?
        if let filterDate = selectedDateFilter {
            let calendar = Calendar.current
            startDate = calendar.startOfDay(for: filterDate)
            endDate = calendar.date(byAdding: .day, value: 1, to: startDate!)
        } else {
            startDate = nil
            endDate = nil
        }

        // Fetch conversations and count in parallel
        async let conversationsTask = APIClient.shared.getConversations(
            limit: 50,
            offset: 0,
            statuses: [.completed, .processing],
            includeDiscarded: false,
            startDate: startDate,
            endDate: endDate,
            folderId: selectedFolderId,
            starred: showStarredOnly ? true : nil
        )
        async let countTask = APIClient.shared.getConversationsCount(includeDiscarded: false)

        do {
            let fetchedConversations = try await conversationsTask
            conversations = fetchedConversations
            log("Conversations: Refreshed \(fetchedConversations.count) from API (starred=\(showStarredOnly), date=\(selectedDateFilter?.description ?? "nil"))")

            // DEBUG: Log any conversations with empty titles
            for conv in fetchedConversations where conv.structured.title.isEmpty {
                log("DEBUG: Conversation \(conv.id) has EMPTY title! overview=\(conv.structured.overview.prefix(50))...")
            }

            // Sync conversations to local database in background
            Task.detached(priority: .background) {
                var syncedCount = 0
                for conversation in fetchedConversations {
                    do {
                        try await TranscriptionStorage.shared.syncServerConversation(conversation)
                        syncedCount += 1
                    } catch {
                        log("Conversations: Failed to sync \(conversation.id) to local DB: \(error.localizedDescription)")
                    }
                }
                log("Conversations: Synced \(syncedCount)/\(fetchedConversations.count) to local database")
            }
        } catch {
            logError("Conversations: API fetch failed", error: error)
            // Only set error if we don't have cached data
            if conversations.isEmpty {
                conversationsError = error.localizedDescription
            } else {
                log("Conversations: Using cached data after API failure")
            }
        }

        // Update total count from API (more accurate than local)
        do {
            let count = try await countTask
            totalConversationsCount = count
            log("Conversations: Total count from API = \(count)")
        } catch {
            logError("Conversations: Failed to get count from API", error: error)
            // Keep local count if API fails
        }

        isLoadingConversations = false
        NotificationCenter.default.post(name: .conversationsPageDidLoad, object: nil)
    }

    /// Refresh conversations silently (for auto-refresh timer and app-activate).
    /// Fetches from API only, merges in-place, and only triggers @Published if data actually changed.
    func refreshConversations() async {
        // Skip if user is signed out (tokens are cleared)
        guard AuthState.shared.isSignedIn else { return }
        // Skip if currently doing a full load
        guard !isLoadingConversations else { return }

        // Calculate date range if date filter is set
        let startDate: Date?
        let endDate: Date?
        if let filterDate = selectedDateFilter {
            let calendar = Calendar.current
            startDate = calendar.startOfDay(for: filterDate)
            endDate = calendar.date(byAdding: .day, value: 1, to: startDate!)
        } else {
            startDate = nil
            endDate = nil
        }

        do {
            let fetchedConversations = try await APIClient.shared.getConversations(
                limit: 50,
                offset: 0,
                statuses: [.completed, .processing],
                includeDiscarded: false,
                startDate: startDate,
                endDate: endDate,
                folderId: selectedFolderId,
                starred: showStarredOnly ? true : nil
            )

            // Merge in-place: update existing, add new, remove gone
            let merged = mergeConversations(source: fetchedConversations, current: conversations)
            if merged != conversations {
                conversations = merged
                log("Conversations: Auto-refresh updated (\(merged.count) items)")
            }

            // Sync to local database in background
            Task.detached(priority: .background) {
                for conversation in fetchedConversations {
                    _ = try? await TranscriptionStorage.shared.syncServerConversation(conversation)
                }
            }
        } catch {
            // Silently ignore errors during auto-refresh — cached data stays visible
            logError("Conversations: Auto-refresh failed", error: error)
        }

        // Update total count
        do {
            let count = try await APIClient.shared.getConversationsCount(includeDiscarded: false)
            if totalConversationsCount != count {
                totalConversationsCount = count
            }
        } catch {
            // Keep existing count
        }
    }

    /// Merge fetched conversations into the current list in-place.
    /// Updates changed items, adds new ones, removes ones no longer in source.
    private func mergeConversations(source: [ServerConversation], current: [ServerConversation]) -> [ServerConversation] {
        let sourceById = Dictionary(uniqueKeysWithValues: source.map { ($0.id, $0) })
        let sourceIds = Set(source.map { $0.id })
        let currentIds = Set(current.map { $0.id })

        var result = current

        // Update existing items in-place
        for i in result.indices {
            if let updated = sourceById[result[i].id], updated != result[i] {
                result[i] = updated
            }
        }

        // Remove items no longer in source
        result.removeAll { !sourceIds.contains($0.id) }

        // Add new items from source that aren't in current
        let newIds = sourceIds.subtracting(currentIds)
        if !newIds.isEmpty {
            let newItems = source.filter { newIds.contains($0.id) }
            result.append(contentsOf: newItems)
            // Re-sort by createdAt descending (newest first) to maintain order
            result.sort { $0.createdAt > $1.createdAt }
        }

        return result
    }

    /// Update the starred status of a conversation locally
    func setConversationStarred(_ conversationId: String, starred: Bool) {
        if let index = conversations.firstIndex(where: { $0.id == conversationId }) {
            conversations[index].starred = starred
        }
    }

    /// Toggle starred filter and reload conversations
    func toggleStarredFilter() async {
        showStarredOnly.toggle()
        await loadConversations()
    }

    /// Set date filter and reload conversations
    func setDateFilter(_ date: Date?) async {
        selectedDateFilter = date
        await loadConversations()
    }

    /// Clear all filters and reload conversations
    func clearFilters() async {
        showStarredOnly = false
        selectedDateFilter = nil
        selectedFolderId = nil
        await loadConversations()
    }

    /// Set folder filter and reload conversations
    func setFolderFilter(_ folderId: String?) async {
        selectedFolderId = folderId
        await loadConversations()
    }

    // MARK: - Folder Management

    /// Load folders from API
    func loadFolders() async {
        guard !isLoadingFolders else { return }

        isLoadingFolders = true

        do {
            let fetchedFolders = try await APIClient.shared.getFolders()
            folders = fetchedFolders
            log("Folders: Loaded \(fetchedFolders.count) folders")
        } catch {
            logError("Folders: Failed to load", error: error)
        }

        isLoadingFolders = false
    }

    /// Create a new folder
    func createFolder(name: String, description: String? = nil, color: String? = nil) async -> Folder? {
        do {
            let folder = try await APIClient.shared.createFolder(name: name, description: description, color: color)
            folders.append(folder)
            log("Folders: Created folder '\(name)'")
            return folder
        } catch {
            logError("Folders: Failed to create folder", error: error)
            return nil
        }
    }

    /// Delete a folder
    func deleteFolder(_ folderId: String, moveToFolderId: String? = nil) async {
        do {
            try await APIClient.shared.deleteFolder(id: folderId, moveToFolderId: moveToFolderId)
            folders.removeAll { $0.id == folderId }
            if selectedFolderId == folderId {
                selectedFolderId = nil
            }
            log("Folders: Deleted folder \(folderId)")
        } catch {
            logError("Folders: Failed to delete folder", error: error)
        }
    }

    /// Update a folder
    func updateFolder(_ folderId: String, name: String?, description: String?, color: String?) async {
        do {
            let updated = try await APIClient.shared.updateFolder(id: folderId, name: name, description: description, color: color)
            if let index = folders.firstIndex(where: { $0.id == folderId }) {
                folders[index] = updated
            }
            log("Folders: Updated folder \(folderId)")
        } catch {
            logError("Folders: Failed to update folder", error: error)
        }
    }

    /// Move a conversation to a folder
    func moveConversationToFolder(_ conversationId: String, folderId: String?) async {
        do {
            try await APIClient.shared.moveConversationToFolder(conversationId: conversationId, folderId: folderId)

            // Sync to local SQLite cache so reload doesn't revert the change
            try await TranscriptionStorage.shared.updateFolderByBackendId(conversationId, folderId: folderId)

            // Update local state
            if conversations.contains(where: { $0.id == conversationId }) {
                // Reload to get updated conversation
                await loadConversations()
            }
            log("Folders: Moved conversation \(conversationId) to folder \(folderId ?? "none")")
        } catch {
            logError("Folders: Failed to move conversation to folder", error: error)
        }
    }

    /// Delete a conversation locally (after successful API call)
    func deleteConversationLocally(_ conversationId: String) {
        withAnimation {
            conversations.removeAll { $0.id == conversationId }
        }
    }

    /// Update a conversation title locally (after successful API call)
    func updateConversationTitle(_ conversationId: String, title: String) {
        if let index = conversations.firstIndex(where: { $0.id == conversationId }) {
            conversations[index].structured.title = title
        }
    }

    // MARK: - People (Speaker Profiles)

    /// Fetches all people from the OMI API
    func fetchPeople() async {
        do {
            let fetchedPeople = try await APIClient.shared.getPeople()
            people = fetchedPeople
            log("People: Loaded \(fetchedPeople.count) people")
        } catch {
            logError("People: Failed to load", error: error)
        }
    }

    /// Creates a new person and adds to local cache
    func createPerson(name: String) async -> Person? {
        do {
            let person = try await APIClient.shared.createPerson(name: name)
            people.append(person)
            log("People: Created person '\(name)' with id \(person.id)")
            return person
        } catch {
            logError("People: Failed to create person", error: error)
            return nil
        }
    }

    /// Assigns segments to a person or user via bulk API
    func assignSpeakerToSegments(
        conversationId: String,
        segmentIds: [Int],
        personId: String?,
        isUser: Bool
    ) async -> Bool {
        do {
            try await APIClient.shared.assignSegmentsBulk(
                conversationId: conversationId,
                segmentIds: segmentIds.map(String.init),
                isUser: isUser,
                personId: personId
            )
            log("People: Assigned \(segmentIds.count) segments in conversation \(conversationId)")
            return true
        } catch {
            logError("People: Failed to assign segments", error: error)
            return false
        }
    }

    /// Finalize and save the current conversation to the backend
    /// Uses DB as source of truth for crash safety
    private func finalizeConversation() async -> FinishConversationResult {
        guard let startTime = recordingStartTime else {
            log("Transcription: No recording start time")
            return .discarded
        }

        let endTime = Date()
        let sessionId = currentSessionId

        // Try to load segments from DB if we have a session, fall back to in-memory
        var segmentsToUpload: [SpeakerSegment] = speakerSegments

        if let sessionId = sessionId {
            do {
                // Mark session as finished in DB first
                try await TranscriptionStorage.shared.finishSession(id: sessionId)

                // Load segments from DB (source of truth for crash recovery)
                let dbSegments = try await TranscriptionStorage.shared.getSegments(sessionId: sessionId)
                if !dbSegments.isEmpty {
                    // Convert DB segments to SpeakerSegment format
                    segmentsToUpload = dbSegments.map { dbSeg in
                        SpeakerSegment(
                            speaker: dbSeg.speaker,
                            text: dbSeg.text,
                            start: dbSeg.startTime,
                            end: dbSeg.endTime
                        )
                    }
                    log("Transcription: Loaded \(segmentsToUpload.count) segments from DB")
                }
            } catch {
                logError("Transcription: Failed to load segments from DB, using in-memory", error: error)
                // Fall through to use in-memory segments
            }
        }

        guard !segmentsToUpload.isEmpty else {
            log("Transcription: No segments to save")
            // Clean up empty session
            if let sessionId = sessionId {
                try? await TranscriptionStorage.shared.deleteSession(id: sessionId)
            }
            return .discarded
        }

        log("Transcription: Finalizing conversation with \(segmentsToUpload.count) segments")

        // Convert SpeakerSegment to API request format (include person_id from live naming)
        let speakerPersonMap = liveSpeakerPersonMap
        let apiSegments = segmentsToUpload.map { segment in
            APIClient.TranscriptSegmentRequest(
                text: segment.text,
                speaker: "SPEAKER_\(String(format: "%02d", segment.speaker))",
                speakerId: segment.speaker,
                isUser: segment.speaker == 0,  // Assume speaker 0 is the user
                personId: speakerPersonMap[segment.speaker],
                start: segment.start,
                end: segment.end
            )
        }

        // Mark session as uploading
        if let sessionId = sessionId {
            try? await TranscriptionStorage.shared.markSessionUploading(id: sessionId)
        }

        do {
            let response = try await APIClient.shared.createConversationFromSegments(
                segments: apiSegments,
                startedAt: startTime,
                finishedAt: endTime,
                source: currentConversationSource,
                inputDeviceName: recordingInputDeviceName
            )
            log("Transcription: Conversation saved - id=\(response.id), status=\(response.status), discarded=\(response.discarded), source=\(currentConversationSource.rawValue), device=\(recordingInputDeviceName ?? "Unknown")")

            // Mark session as completed in DB
            if let sessionId = sessionId {
                do {
                    try await TranscriptionStorage.shared.markSessionCompleted(id: sessionId, backendId: response.id)
                } catch {
                    logError("Transcription: Failed to mark session \(sessionId) as completed (backendId: \(response.id))", error: error)
                    // Session is stuck in 'uploading' state — mark as failed so retry service can recover it
                    try? await TranscriptionStorage.shared.markSessionFailed(id: sessionId, error: "markSessionCompleted failed: \(error.localizedDescription)")
                }
            }

            if response.discarded {
                return .discarded
            }

            // Track successful conversation creation in analytics (Mixpanel + PostHog)
            let durationSeconds = Int(endTime.timeIntervalSince(startTime))
            AnalyticsManager.shared.conversationCreated(
                conversationId: response.id,
                source: currentConversationSource.rawValue,
                durationSeconds: durationSeconds
            )

            // Fire-and-forget: extract goal progress from conversation transcript
            let transcriptText = segmentsToUpload.map { $0.text }.joined(separator: " ")
            if transcriptText.count >= 10 {
                Task.detached(priority: .background) {
                    await GoalsAIService.shared.extractProgressFromAllGoals(text: transcriptText)
                }
            }

            // Check daily goal generation
            Task { @MainActor in
                GoalGenerationService.shared.onConversationCreated()
            }

            return .saved
        } catch {
            logError("Transcription: Failed to save conversation", error: error)
            AnalyticsManager.shared.recordingError(error: "Failed to save: \(error.localizedDescription)")

            // Mark session as failed in DB for later retry
            if let sessionId = sessionId {
                try? await TranscriptionStorage.shared.markSessionFailed(id: sessionId, error: error.localizedDescription)
            }

            return .error(error.localizedDescription)
        }
    }

    /// Handle incoming transcript segment with speaker diarization
    /// Uses channel index for primary speaker attribution:
    ///   - Channel 0 = microphone = user (speaker 0)
    ///   - Channel 1 = system audio = others (speaker 1+)
    private func handleTranscriptSegment(_ segment: TranscriptionService.TranscriptSegment) {
        // Only process final segments (speechFinal or isFinal)
        guard segment.speechFinal || segment.isFinal else { return }

        // Determine speaker based on channel index
        // Channel 0 = mic = user (speaker 0)
        // Channel 1 = system audio = others (speaker 1+)
        let channelBasedSpeaker = segment.channelIndex == 0 ? 0 : 1

        // Process words and merge by speaker
        let words = segment.words
        guard !words.isEmpty else {
            // Fallback: no words, just append text with channel-based speaker
            if segment.speechFinal && !segment.text.isEmpty {
                appendToTranscript(segment.text)
                log("Transcript [FINAL no words] Ch\(segment.channelIndex) Speaker \(channelBasedSpeaker): \(segment.text)")
            }
            return
        }

        // Word-to-segment aggregation: merge consecutive words from same speaker
        // For channel 1 (system audio), use diarization speaker ID + 1 to distinguish multiple remote speakers
        var newSegments: [SpeakerSegment] = []
        for word in words {
            // Speaker assignment:
            // - Channel 0 (mic): Always speaker 0 (user)
            // - Channel 1 (system): Use diarization speaker + 1, or default to 1
            let speaker: Int
            if segment.channelIndex == 0 {
                speaker = 0  // Mic is always user
            } else {
                // System audio: offset diarization speakers by 1
                // This allows distinguishing multiple remote speakers (1, 2, 3, etc.)
                speaker = (word.speaker ?? 0) + 1
            }

            if let last = newSegments.last, last.speaker == speaker {
                // Same speaker - append word to existing segment
                newSegments[newSegments.count - 1].text += " " + word.punctuatedWord
                newSegments[newSegments.count - 1].end = word.end
            } else {
                // Different speaker - create new segment
                newSegments.append(SpeakerSegment(
                    speaker: speaker,
                    text: word.punctuatedWord,
                    start: word.start,
                    end: word.end
                ))
            }
        }

        // Log new segments from this chunk
        for seg in newSegments {
            let channelLabel = segment.channelIndex == 0 ? "mic" : "sys"
            log("Transcript [NEW] Ch\(segment.channelIndex)(\(channelLabel)) Speaker \(seg.speaker) [\(String(format: "%.1f", seg.start))s-\(String(format: "%.1f", seg.end))s]: \(seg.text)")
        }

        // Gap-based merging: combine with existing segments if same speaker and gap < 3 seconds
        for newSeg in newSegments {
            if let lastIdx = speakerSegments.indices.last,
               speakerSegments[lastIdx].speaker == newSeg.speaker,
               newSeg.start - speakerSegments[lastIdx].end < 3.0 {
                // Same speaker and gap < 3s - merge
                let gap = newSeg.start - speakerSegments[lastIdx].end
                log("Transcript [MERGE] Speaker \(newSeg.speaker) gap=\(String(format: "%.2f", gap))s: merging into existing segment")
                speakerSegments[lastIdx].text += " " + newSeg.text
                speakerSegments[lastIdx].end = newSeg.end
            } else {
                // Different speaker or gap >= 3s - add as new segment
                if let lastIdx = speakerSegments.indices.last {
                    let gap = newSeg.start - speakerSegments[lastIdx].end
                    log("Transcript [ADD] Speaker \(newSeg.speaker) gap=\(String(format: "%.2f", gap))s: new segment (different speaker or gap >= 3s)")
                } else {
                    log("Transcript [ADD] Speaker \(newSeg.speaker): first segment")
                }
                speakerSegments.append(newSeg)
            }
        }

        // Log current segments summary (only last 5 segments when count > 20 to avoid log spam)
        log("Transcript [SEGMENTS] Total: \(speakerSegments.count) segments")
        let logSegments = speakerSegments.count > 20
            ? Array(speakerSegments.suffix(5))
            : speakerSegments
        let startIdx = speakerSegments.count > 20 ? speakerSegments.count - 5 : 0
        if speakerSegments.count > 20 {
            log("  ... (\(speakerSegments.count - 5) earlier segments omitted)")
        }
        for (offset, seg) in logSegments.enumerated() {
            let i = startIdx + offset
            let speakerLabel = seg.speaker == 0 ? "user" : "other"
            log("  [\(i)] Speaker \(seg.speaker)(\(speakerLabel)) [\(String(format: "%.1f", seg.start))s-\(String(format: "%.1f", seg.end))s]: \(seg.text)")
        }

        // Update published segments for UI (via isolated monitor)
        LiveTranscriptMonitor.shared.updateSegments(speakerSegments)

        // Update display transcript
        updateTranscriptDisplay()

        // Persist new segments to DB for crash safety
        if let sessionId = currentSessionId {
            Task {
                for newSeg in newSegments {
                    do {
                        try await TranscriptionStorage.shared.appendSegment(
                            sessionId: sessionId,
                            speaker: newSeg.speaker,
                            text: newSeg.text,
                            startTime: newSeg.start,
                            endTime: newSeg.end
                        )
                    } catch {
                        logError("Transcription: Failed to persist segment to DB", error: error)
                        await RewindDatabase.shared.reportQueryError(error)
                        // Non-fatal - continue recording
                    }
                }
            }
        }
    }

    /// Update the display transcript from speaker segments
    private func updateTranscriptDisplay() {
        currentTranscript = speakerSegments.map { seg in
            let speakerLabel = seg.speaker == 0 ? "You" : "Speaker \(seg.speaker)"
            return "\(speakerLabel): \(seg.text)"
        }.joined(separator: "\n")
    }

    /// Append text to transcript (fallback when no word-level data)
    private func appendToTranscript(_ text: String) {
        if !currentTranscript.isEmpty {
            currentTranscript += "\n"
        }
        currentTranscript += text
    }

    /// Request microphone permission
    func requestMicrophonePermission() {
        // Activate app to ensure permission dialog appears
        NSApp.activate(ignoringOtherApps: true)

        log("Requesting microphone permission, current status: \(AudioCaptureService.authorizationStatus().rawValue)")

        Task {
            let granted = await AudioCaptureService.requestPermission()
            await MainActor.run {
                self.hasMicrophonePermission = granted
                log("Microphone permission request completed, granted: \(granted)")
                if granted {
                    log("Microphone permission granted")
                    // Only start transcription if onboarding is complete
                    // During onboarding, we just update the permission state
                    if self.hasCompletedOnboarding {
                        self.startTranscription()
                    }
                } else {
                    log("Microphone permission denied")
                    // UI will show the denied state with reset options inline
                }
            }
        }
    }

    /// Check microphone permission status
    func checkMicrophonePermission() {
        hasMicrophonePermission = AudioCaptureService.checkPermission()
    }

    /// Check if microphone permission was explicitly denied
    func isMicrophonePermissionDenied() -> Bool {
        return AudioCaptureService.isPermissionDenied()
    }

    /// Check if screen recording permission is denied (onboarding complete but permission not granted)
    func isScreenRecordingPermissionDenied() -> Bool {
        return hasCompletedOnboarding && !CGPreflightScreenCaptureAccess()
    }

    /// Restart the app by launching a new instance and terminating the current one
    nonisolated func restartApp() {
        if UpdaterViewModel.isUpdateInProgress {
            log("Sparkle update in progress, skipping independent restart (Sparkle will handle relaunch)")
            return
        }

        log("Restarting app...")

        guard let bundleURL = Bundle.main.bundleURL as URL? else {
            log("Failed to get bundle URL for restart")
            return
        }

        // Use a shell script to wait briefly, then relaunch the app
        let task = Process()
        task.executableURL = URL(fileURLWithPath: "/bin/sh")
        task.arguments = ["-c", "sleep 0.5 && open \"\(bundleURL.path)\""]

        do {
            try task.run()
            log("Restart scheduled, terminating current instance...")

            // Terminate the current app
            DispatchQueue.main.async {
                NSApplication.shared.terminate(nil)
            }
        } catch {
            log("Failed to schedule restart: \(error)")
        }
    }

    /// Reset onboarding state and all TCC permissions, then restart the app
    /// This clears UserDefaults onboarding keys and resets permissions so the user
    /// can go through onboarding again with fresh permission prompts.
    /// Performs thorough cleanup matching reset-and-run.sh behavior.
    nonisolated func resetOnboardingAndRestart() {
        log("Resetting onboarding (full cleanup)...")

        // Clear onboarding-related UserDefaults keys (thread-safe, do first)
        let onboardingKeys = [
            "hasCompletedOnboarding",
            "onboardingStep",
            "hasSeenRewindIntro",
            "hasTriggeredNotification",
            "hasTriggeredAutomation",
            "hasTriggeredScreenRecording",
            "hasTriggeredMicrophone",
            "hasTriggeredSystemAudio",
            "hasTriggeredAccessibility",
            "hasTriggeredBluetooth"
        ]
        for key in onboardingKeys {
            UserDefaults.standard.removeObject(forKey: key)
        }
        UserDefaults.standard.synchronize()
        log("Cleared onboarding UserDefaults keys")

        // Also clear UserDefaults for both bundle IDs
        if let prodDefaults = UserDefaults(suiteName: "com.omi.computer-macos") {
            for key in onboardingKeys {
                prodDefaults.removeObject(forKey: key)
            }
        }
        if let devDefaults = UserDefaults(suiteName: "com.omi.desktop-dev") {
            for key in onboardingKeys {
                devDefaults.removeObject(forKey: key)
            }
        }

        // Run all blocking Process calls on a background thread
        DispatchQueue.global(qos: .utility).async { [self] in
            // 1. Clean conflicting app bundles from Trash, DerivedData, DMG staging
            cleanConflictingAppBundles()

            // 2. Eject any mounted Omi DMG volumes
            ejectMountedDMGVolumes()

            // 3. Reset Launch Services database to clear stale registrations
            resetLaunchServicesDatabase()

            // 4. Ensure this app is the authoritative version in Launch Services
            ScreenCaptureService.ensureLaunchServicesRegistration()

            // 5. Reset ALL TCC permissions using tccutil for BOTH bundle IDs
            let bundleIds = [
                "com.omi.computer-macos",       // Production
                "com.omi.desktop-dev"           // Development
            ]

            for id in bundleIds {
                let process = Process()
                process.executableURL = URL(fileURLWithPath: "/usr/bin/tccutil")
                process.arguments = ["reset", "All", id]

                do {
                    try process.run()
                    process.waitUntilExit()
                    log("tccutil reset All for \(id) completed with exit code: \(process.terminationStatus)")
                } catch {
                    log("Failed to run tccutil for \(id): \(error)")
                }
            }

            // 6. Also clean user TCC database directly via sqlite3
            self.cleanUserTCCDatabase()

            // 7. Restart the app
            self.restartApp()
        }
    }

    /// Clean conflicting app bundles from Trash, DerivedData, and DMG staging directories
    private nonisolated func cleanConflictingAppBundles() {
        let fileManager = FileManager.default
        let homeDir = fileManager.homeDirectoryForCurrentUser.path

        // Clean Omi apps from Trash (they still pollute Launch Services!)
        let trashPath = "\(homeDir)/.Trash"
        if let contents = try? fileManager.contentsOfDirectory(atPath: trashPath) {
            for item in contents where item.lowercased().contains("omi") {
                let itemPath = "\(trashPath)/\(item)"
                do {
                    try fileManager.removeItem(atPath: itemPath)
                    log("Cleaned from Trash: \(item)")
                } catch {
                    log("Failed to clean from Trash: \(item) - \(error.localizedDescription)")
                }
            }
        }

        // Clean DMG staging directories
        let tmpDir = "/private/tmp"
        if let contents = try? fileManager.contentsOfDirectory(atPath: tmpDir) {
            for item in contents where item.hasPrefix("omi-dmg-staging") || item.hasPrefix("omi-dmg-test") {
                let itemPath = "\(tmpDir)/\(item)"
                do {
                    try fileManager.removeItem(atPath: itemPath)
                    log("Cleaned DMG staging: \(item)")
                } catch {
                    log("Failed to clean DMG staging: \(item) - \(error.localizedDescription)")
                }
            }
        }

        // Clean Xcode DerivedData Omi builds
        let derivedDataPath = "\(homeDir)/Library/Developer/Xcode/DerivedData"
        if let contents = try? fileManager.contentsOfDirectory(atPath: derivedDataPath) {
            for item in contents where item.lowercased().contains("omi") {
                let buildProductsPath = "\(derivedDataPath)/\(item)/Build/Products"
                if let buildDirs = try? fileManager.contentsOfDirectory(atPath: buildProductsPath) {
                    for buildDir in buildDirs {
                        let appPath = "\(buildProductsPath)/\(buildDir)/Omi.app"
                        let appPath2 = "\(buildProductsPath)/\(buildDir)/Omi Computer.app"
                        let appPath3 = "\(buildProductsPath)/\(buildDir)/Omi Beta.app"
                        let appPath4 = "\(buildProductsPath)/\(buildDir)/Omi Dev.app"
                        for path in [appPath, appPath2, appPath3, appPath4] {
                            if fileManager.fileExists(atPath: path) {
                                do {
                                    try fileManager.removeItem(atPath: path)
                                    log("Cleaned DerivedData: \(path)")
                                } catch {
                                    log("Failed to clean DerivedData: \(path) - \(error.localizedDescription)")
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    /// Eject any mounted Omi DMG volumes
    private nonisolated func ejectMountedDMGVolumes() {
        let fileManager = FileManager.default
        let volumesPath = "/Volumes"

        guard let contents = try? fileManager.contentsOfDirectory(atPath: volumesPath) else { return }

        for volume in contents where volume.lowercased().contains("omi") || volume.hasPrefix("dmg.") {
            let volumePath = "\(volumesPath)/\(volume)"

            // Try diskutil eject first
            let process = Process()
            process.executableURL = URL(fileURLWithPath: "/usr/sbin/diskutil")
            process.arguments = ["eject", volumePath]
            process.standardOutput = FileHandle.nullDevice
            process.standardError = FileHandle.nullDevice

            do {
                try process.run()
                process.waitUntilExit()
                if process.terminationStatus == 0 {
                    log("Ejected volume: \(volume)")
                } else {
                    // Try hdiutil detach as fallback
                    let detachProcess = Process()
                    detachProcess.executableURL = URL(fileURLWithPath: "/usr/bin/hdiutil")
                    detachProcess.arguments = ["detach", volumePath]
                    detachProcess.standardOutput = FileHandle.nullDevice
                    detachProcess.standardError = FileHandle.nullDevice
                    try? detachProcess.run()
                    detachProcess.waitUntilExit()
                }
            } catch {
                log("Failed to eject volume: \(volume) - \(error.localizedDescription)")
            }
        }
    }

    /// Reset Launch Services database to clear stale app registrations
    private nonisolated func resetLaunchServicesDatabase() {
        let lsregisterPath = "/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister"

        let process = Process()
        process.executableURL = URL(fileURLWithPath: lsregisterPath)
        process.arguments = ["-kill", "-r", "-domain", "local", "-domain", "user"]
        process.standardOutput = FileHandle.nullDevice
        process.standardError = FileHandle.nullDevice

        do {
            try process.run()
            process.waitUntilExit()
            log("Launch Services database reset (exit code: \(process.terminationStatus))")
        } catch {
            log("Failed to reset Launch Services: \(error.localizedDescription)")
        }
    }

    /// Clean user TCC database entries for Omi apps
    private nonisolated func cleanUserTCCDatabase() {
        let homeDir = FileManager.default.homeDirectoryForCurrentUser.path
        let tccDbPath = "\(homeDir)/Library/Application Support/com.apple.TCC/TCC.db"

        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/sqlite3")
        process.arguments = [tccDbPath, "DELETE FROM access WHERE client LIKE '%com.omi.computer-macos%';"]
        process.standardOutput = FileHandle.nullDevice
        process.standardError = FileHandle.nullDevice

        do {
            try process.run()
            process.waitUntilExit()
            log("User TCC database cleaned (exit code: \(process.terminationStatus))")
        } catch {
            log("Failed to clean user TCC database: \(error.localizedDescription)")
        }

        // Also clean entries for new dev bundle ID pattern (com.omi.desktop-dev)
        let process2 = Process()
        process2.executableURL = URL(fileURLWithPath: "/usr/bin/sqlite3")
        process2.arguments = [tccDbPath, "DELETE FROM access WHERE client LIKE '%com.omi.desktop%';"]
        process2.standardOutput = FileHandle.nullDevice
        process2.standardError = FileHandle.nullDevice

        do {
            try process2.run()
            process2.waitUntilExit()
            log("User TCC database cleaned for desktop-dev (exit code: \(process2.terminationStatus))")
        } catch {
            log("Failed to clean user TCC database for desktop-dev: \(error.localizedDescription)")
        }
    }

    /// Reset microphone permission using tccutil (Option 1: Direct)
    /// Returns true if the reset command was executed successfully
    /// If shouldRestart is true, the app will restart after reset
    nonisolated func resetMicrophonePermissionDirect(shouldRestart: Bool = false) -> Bool {
        let bundleId = Bundle.main.bundleIdentifier ?? "com.omi.computer-macos"
        log("Resetting microphone permission for \(bundleId) via tccutil...")

        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/tccutil")
        process.arguments = ["reset", "Microphone", bundleId]

        do {
            try process.run()
            process.waitUntilExit()
            let success = process.terminationStatus == 0
            log("tccutil reset completed with exit code: \(process.terminationStatus)")

            if success && shouldRestart {
                restartApp()
            }

            return success
        } catch {
            log("Failed to run tccutil: \(error)")
            return false
        }
    }

    /// Reset microphone permission via Terminal (Option 2: Visible to user)
    /// If shouldRestart is true, the app will restart after the terminal command
    func resetMicrophonePermissionViaTerminal(shouldRestart: Bool = false) {
        let bundleId = Bundle.main.bundleIdentifier ?? "com.omi.computer-macos"
        let appPath = Bundle.main.bundleURL.path
        log("Opening Terminal to reset microphone permission for \(bundleId)...")

        // Build the shell command - escape single quotes in path for shell
        let escapedPath = appPath.replacingOccurrences(of: "'", with: "'\\''")
        let restartCommand = shouldRestart ? " && open '\(escapedPath)'" : ""
        let shellCommand = "tccutil reset Microphone \(bundleId) && echo 'Done! Permission reset.'\(restartCommand)"

        // AppleScript to open Terminal and run the command
        let script = "tell application \"Terminal\"\nactivate\ndo script \"\(shellCommand)\"\nend tell"

        var error: NSDictionary?
        if let appleScript = NSAppleScript(source: script) {
            appleScript.executeAndReturnError(&error)
            if let error = error {
                log("AppleScript error: \(error)")
            } else if shouldRestart {
                // Terminate current app after terminal script is running
                DispatchQueue.main.asyncAfter(deadline: .now() + 1.0) {
                    NSApplication.shared.terminate(nil)
                }
            }
        }
    }

    /// Check system audio permission status
    /// This checks if the test capture was successful (set by triggerSystemAudioPermission)
    func checkSystemAudioPermission() {
        // Permission is set by triggerSystemAudioPermission after successful test
        // No-op here - we rely on the test result
    }

    /// Trigger system audio permission by actually testing capture
    /// This verifies system audio works by briefly starting and stopping capture
    func triggerSystemAudioPermission() {
        guard #available(macOS 14.4, *) else {
            log("System audio not supported on this macOS version")
            hasSystemAudioPermission = false
            return
        }

        log("System audio: Testing capture...")

        // Create a test capture service
        let testService = SystemAudioCaptureService()

        do {
            // Try to start capture - this will fail if permission is not granted
            try testService.startCapture { _ in
                // We don't need the audio data, just testing if it works
            }

            // If we get here, capture started successfully
            log("System audio: Test capture started successfully")

            // Stop the test capture
            testService.stopCapture()
            log("System audio: Test capture stopped")

            // Mark permission as granted
            hasSystemAudioPermission = true
            log("System audio: Permission verified")

        } catch {
            logError("System audio: Test capture failed", error: error)
            hasSystemAudioPermission = false

            // Open System Settings to Screen Recording section
            if let url = URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture") {
                NSWorkspace.shared.open(url)
            }
        }
    }
}

// MARK: - System Event Notification Names

extension Notification.Name {
    /// Posted when the system wakes from sleep
    static let systemDidWake = Notification.Name("systemDidWake")
    /// Posted when the screen is locked
    static let screenDidLock = Notification.Name("screenDidLock")
    /// Posted when the screen is unlocked
    static let screenDidUnlock = Notification.Name("screenDidUnlock")
    /// Posted when screen capture permission is detected as lost
    static let screenCapturePermissionLost = Notification.Name("screenCapturePermissionLost")
    /// Posted when ScreenCaptureKit is broken (TCC granted but SCK declined)
    static let screenCaptureKitBroken = Notification.Name("screenCaptureKitBroken")
    /// Posted to navigate to Rewind settings
    static let navigateToRewindSettings = Notification.Name("navigateToRewindSettings")
    /// Posted to navigate to Rewind page (global hotkey: Cmd+Option+R)
    static let navigateToRewind = Notification.Name("navigateToRewind")
    /// Posted to navigate to Device settings
    static let navigateToDeviceSettings = Notification.Name("navigateToDeviceSettings")
    /// Posted to navigate to Task Assistant settings (Developer Settings)
    static let navigateToTaskSettings = Notification.Name("navigateToTaskSettings")
    /// Posted to navigate to Ask Omi Floating Bar settings
    static let navigateToFloatingBarSettings = Notification.Name("navigateToFloatingBarSettings")
    /// Posted to navigate to AI Chat settings
    static let navigateToAIChatSettings = Notification.Name("navigateToAIChatSettings")
    /// Posted when a new Rewind frame is captured (for live frame count updates)
    static let rewindFrameCaptured = Notification.Name("rewindFrameCaptured")
    /// Posted when Rewind page finishes loading initial data
    static let rewindPageDidLoad = Notification.Name("rewindPageDidLoad")
    /// Posted when Conversations page finishes loading initial data
    static let conversationsPageDidLoad = Notification.Name("conversationsPageDidLoad")
    /// Posted when Tasks page finishes loading initial data
    static let tasksPageDidLoad = Notification.Name("tasksPageDidLoad")
    /// Posted when Focus page finishes loading initial data
    static let focusPageDidLoad = Notification.Name("focusPageDidLoad")
    /// Posted when Advice page finishes loading initial data
    static let advicePageDidLoad = Notification.Name("advicePageDidLoad")
    /// Posted when Apps page finishes loading initial data
    static let appsPageDidLoad = Notification.Name("appsPageDidLoad")
    /// Posted when a goal is auto-created by GoalGenerationService
    static let goalAutoCreated = Notification.Name("goalAutoCreated")
    /// Posted when a goal is completed (current_value >= target_value)
    static let goalCompleted = Notification.Name("goalCompleted")
    /// Posted to navigate to AI Chat page
    static let navigateToChat = Notification.Name("navigateToChat")
    static let navigateToTasks = Notification.Name("navigateToTasks")
    /// Posted when file indexing completes (userInfo: ["totalFiles": Int])
    static let fileIndexingComplete = Notification.Name("fileIndexingComplete")
    /// Posted from Settings to trigger the file indexing sheet
    static let triggerFileIndexing = Notification.Name("triggerFileIndexing")
}
