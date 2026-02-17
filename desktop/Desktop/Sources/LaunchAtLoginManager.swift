import Foundation
import ServiceManagement

/// Manages the app's launch at login status using SMAppService (macOS 13+)
@MainActor
class LaunchAtLoginManager: ObservableObject {
    static let shared = LaunchAtLoginManager()

    @Published private(set) var isEnabled: Bool = false
    @Published private(set) var statusDescription: String = "Checking..."

    private init() {
        // Check current status on init
        updateStatus()
    }

    /// Updates the published status from the system (reads SMAppService off main thread)
    func updateStatus() {
        Task.detached {
            let status = SMAppService.mainApp.status
            let enabled = status == .enabled
            let description: String
            switch status {
            case .enabled:
                description = "App will start when you log in"
            case .notRegistered:
                description = "App won't start automatically"
            case .notFound:
                description = "Login item not found"
            case .requiresApproval:
                description = "Requires approval in System Settings"
            @unknown default:
                description = "Unknown status"
            }
            await MainActor.run {
                self.isEnabled = enabled
                self.statusDescription = description
            }
        }
    }

    /// Enables or disables launch at login
    /// - Parameter enabled: Whether the app should launch at login
    /// - Returns: true if the operation succeeded
    @discardableResult
    func setEnabled(_ enabled: Bool) -> Bool {
        do {
            if enabled {
                try SMAppService.mainApp.register()
                log("LaunchAtLogin: Successfully registered for launch at login")
            } else {
                try SMAppService.mainApp.unregister()
                log("LaunchAtLogin: Successfully unregistered from launch at login")
            }
            updateStatus()
            return true
        } catch {
            log("LaunchAtLogin: Failed to \(enabled ? "register" : "unregister"): \(error.localizedDescription)")
            updateStatus()
            return false
        }
    }
}
