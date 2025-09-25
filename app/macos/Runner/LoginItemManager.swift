import Foundation
import ServiceManagement

enum StartupBehavior: String {
    case showMainWindow
    case showFloatingButton
}

class LoginItemManager {
    static let shared = LoginItemManager()

    // The bundle identifier of the login helper application.
    // This must be embedded in the main application's bundle.
    private let helperBundleIdentifier = "com.omi.OmiLauncher" as CFString
    private let userDefaultsKey = "loginItemEnabled"
    private let startupBehaviorKey = "startupBehavior"

    private init() {}

    var isEnabled: Bool {
        get {
            return UserDefaults.standard.bool(forKey: userDefaultsKey)
        }
        set {
            if newValue {
                enable()
            } else {
                disable()
            }
        }
    }

    var startupBehavior: StartupBehavior {
        get {
            guard let rawValue = UserDefaults.standard.string(forKey: startupBehaviorKey) else {
                return .showMainWindow // Default behavior
            }
            return StartupBehavior(rawValue: rawValue) ?? .showMainWindow
        }
        set {
            UserDefaults.standard.set(newValue.rawValue, forKey: startupBehaviorKey)
        }
    }

    func enable() {
        if #available(macOS 13.0, *) {
            do {
                try SMAppService.mainApp.register()
                UserDefaults.standard.set(true, forKey: userDefaultsKey)
            } catch {
                print("Failed to register login item: \(error)")
                UserDefaults.standard.set(false, forKey: userDefaultsKey)
            }
        } else {
            if SMLoginItemSetEnabled(helperBundleIdentifier, true) {
                UserDefaults.standard.set(true, forKey: userDefaultsKey)
            } else {
                UserDefaults.standard.set(false, forKey: userDefaultsKey)
            }
        }
    }

    func disable() {
        if #available(macOS 13.0, *) {
            do {
                try SMAppService.mainApp.unregister()
                UserDefaults.standard.set(false, forKey: userDefaultsKey)
            } catch {
                print("Failed to unregister login item: \(error)")
            }
        } else {
            if SMLoginItemSetEnabled(helperBundleIdentifier, false) {
                UserDefaults.standard.set(false, forKey: userDefaultsKey)
            }
        }
    }
}
