import SwiftUI
import Combine
import UserNotifications

@MainActor
class AppState: ObservableObject {
    @AppStorage("hasCompletedOnboarding") var hasCompletedOnboarding = false
    @Published var isMonitoring = false
    @Published var currentApp: String?
    @Published var lastStatus: FocusStatus?

    // Permission states for onboarding
    @Published var hasNotificationPermission = false
    @Published var hasScreenRecordingPermission = false
    @Published var hasAutomationPermission = false

    private var screenCaptureService: ScreenCaptureService?
    private var windowMonitor: WindowMonitor?
    private var geminiService: GeminiService?
    private var captureTimer: Timer?

    init() {
        // Load API key from environment or .env file
        loadEnvironment()
    }

    private func loadEnvironment() {
        // Try to load from .env file in bundle or current directory
        let envPaths = [
            Bundle.main.path(forResource: ".env", ofType: nil),
            FileManager.default.currentDirectoryPath + "/.env",
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
                break
            }
        }
    }

    func toggleMonitoring() {
        if isMonitoring {
            stopMonitoring()
        } else {
            startMonitoring()
        }
    }

    func startMonitoring() {
        // Check screen recording permission
        guard ScreenCaptureService.checkPermission() else {
            showPermissionAlert()
            return
        }

        // Initialize services
        screenCaptureService = ScreenCaptureService()

        do {
            geminiService = try GeminiService(
                onAlert: { message in
                    NotificationService.shared.sendNotification(
                        title: "Focus Alert",
                        message: message,
                        applyCooldown: true
                    )
                },
                onStatusChange: { [weak self] status in
                    Task { @MainActor in
                        self?.lastStatus = status
                    }
                },
                onRefocus: {
                    Task { @MainActor in
                        GlowOverlayController.shared.showGlowAroundActiveWindow()
                    }
                }
            )
        } catch {
            showAlert(title: "Error", message: error.localizedDescription)
            return
        }

        // Get initial app state
        let (appName, _) = WindowMonitor.getActiveWindowInfoStatic()
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
                self?.captureFrame()
            }
        }

        isMonitoring = true

        NotificationService.shared.sendNotification(
            title: "Monitoring Started",
            message: "Watching for distractions...",
            applyCooldown: false
        )

        log("OMI monitoring started")
    }

    func stopMonitoring() {
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
            title: "Monitoring Stopped",
            message: "Focus monitoring disabled",
            applyCooldown: false
        )

        log("OMI monitoring stopped")
    }

    private func onAppActivated(appName: String) {
        guard appName != currentApp else { return }
        currentApp = appName
        geminiService?.onAppSwitch(newApp: appName)

        // Capture immediately on app switch for faster response
        captureFrame()
    }

    private func captureFrame() {
        guard isMonitoring, let screenCaptureService = screenCaptureService else { return }

        if let jpegData = screenCaptureService.captureActiveWindow(),
           let appName = currentApp {
            geminiService?.submitFrame(jpegData: jpegData, appName: appName)
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
        // Activate app to ensure permission dialog appears
        NSApp.activate(ignoringOtherApps: true)

        UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound, .badge]) { granted, error in
            if let error = error {
                print("Notification permission error: \(error)")
                return
            }

            if granted {
                // Send a test notification to confirm it works
                DispatchQueue.main.async {
                    NotificationService.shared.sendNotification(
                        title: "Notifications Enabled",
                        message: "You'll receive focus alerts from OMI.",
                        applyCooldown: false
                    )
                }
            }
        }
    }

    /// Trigger screen recording permission prompt
    func triggerScreenRecordingPermission() {
        // Use the official API to request screen capture access
        // This shows a system dialog with "Open System Settings" button
        CGRequestScreenCaptureAccess()
    }

    /// Trigger automation permission by attempting to use Apple Events
    nonisolated func triggerAutomationPermission() {
        // Run a simple AppleScript to trigger the permission prompt
        // This must be done on a background thread since it's nonisolated
        Task.detached {
            let script = NSAppleScript(source: """
                tell application "System Events"
                    return name of first process whose frontmost is true
                end tell
            """)
            var error: NSDictionary?
            script?.executeAndReturnError(&error)
            // Then open settings on main thread
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
    }

    /// Check notification permission status
    func checkNotificationPermission() {
        UNUserNotificationCenter.current().getNotificationSettings { settings in
            DispatchQueue.main.async {
                self.hasNotificationPermission = settings.authorizationStatus == .authorized
            }
        }
    }

    /// Check screen recording permission status
    func checkScreenRecordingPermission() {
        hasScreenRecordingPermission = CGPreflightScreenCaptureAccess()
    }

    /// Check automation permission by attempting to use Apple Events
    func checkAutomationPermission() {
        Task.detached {
            let script = NSAppleScript(source: """
                tell application "System Events"
                    return name of first process whose frontmost is true
                end tell
            """)
            var error: NSDictionary?
            let result = script?.executeAndReturnError(&error)
            let hasPermission = result != nil && error == nil

            await MainActor.run {
                self.hasAutomationPermission = hasPermission
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
}
