import Foundation
import ServiceManagement

/// Launch at login, so an ambient recorder is actually ambient — a user who has to remember to
/// start it every morning has already lost the day's context.
///
/// `SMAppService.mainApp` registers *this bundle by its location*. The registration only survives a
/// reboot when the app lives somewhere LaunchServices trusts — `/Applications` for a released build.
/// Registering from a `.build` directory or the Downloads folder appears to work and then silently
/// stops after the app is moved or the copy is deleted, which is why `scripts/build.sh` installs to
/// `/Applications/Context for Claude.app` rather than running in place.
enum LoginItem {
    private static let logCategory = "login"

    /// Reads the live system state rather than a stored preference: the user can remove a login
    /// item in System Settings at any time, and the UI has to reflect that, not our last write.
    static var isEnabled: Bool {
        SMAppService.mainApp.status == .enabled
    }

    @discardableResult
    static func enable() -> Bool {
        do {
            try SMAppService.mainApp.register()
            if SMAppService.mainApp.status == .requiresApproval {
                // Registration succeeded; macOS is holding it until the user approves the item in
                // System Settings > General > Login Items. `isEnabled` stays false until they do.
                ContextLog.info("Launch at login registered, waiting on approval in System Settings", logCategory)
            } else {
                ContextLog.info("Launch at login enabled", logCategory)
            }
            return true
        } catch {
            ContextLog.error("Could not enable launch at login: \(error.localizedDescription)", logCategory)
            return false
        }
    }

    static func disable() {
        do {
            try SMAppService.mainApp.unregister()
            ContextLog.info("Launch at login disabled", logCategory)
        } catch {
            ContextLog.error("Could not disable launch at login: \(error.localizedDescription)", logCategory)
        }
    }
}
