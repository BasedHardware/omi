import SwiftUI

import OmiKit
import OmiUI

// iOS host shell. Bootstrap + injection + URL plumbing only; all product UI
// comes from OmiUI.RootView driving the injected AppStore.
//
// Injection contract (see ../README.md):
//   - OmiKit.Policy.bridge defaults to DefaultPolicyBridge, which links the
//     real native-core C++ through CNativeCore — nothing to replace on iOS.
//   - Services come from OmiBootstrap: keychain credentials, the
//     authenticated HTTP transport, UserDefaults-backed settings, and the
//     CoreBluetooth device transport. Auth callbacks arrive via the
//     app-specific `omi-rnruntime://auth/callback` scheme
//     (docs/auth-and-sessions.md); the host hands the callback URL to the
//     auth session's browser leg.

@main
struct OmiHostApp: App {
    @StateObject private var store: AppStore

    init() {
        let credentials = KeychainCredentialStore()
        let auth = OmiAuthSession(
            config: AuthSessionConfig(
                firebaseApiKey: Bundle.main.object(
                    forInfoDictionaryKey: "OMIFirebaseAPIKey") as? String ?? ""),
            credentials: credentials)
        let transport = HTTPBackendTransport(
            credentials: credentials,
            planeSelection: HTTPBackendTransport.PlaneSelection(
                storedPlane: UserDefaults.standard.string(
                    forKey: SOFTWARE_PLANE_DEFAULTS_KEY),
                stampedValid: false))
        _store = StateObject(
            wrappedValue: AppStore(
                services: AppServices(
                    auth: auth,
                    chat: ChatService(transport: transport),
                    reads: ReadsService(transport: transport),
                    tasks: TasksService(transport: transport),
                    cloud: CloudService(transport: transport),
                    settings: SettingsStore(storage: UserDefaultsKeyValueStore()),
                    devices: CoreBluetoothDeviceTransport(),
                    transport: transport)))
    }

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(store)
                .onOpenURL { url in
                    handleCallback(url)
                }
        }
    }

    /// The auth callback route is `omi-rnruntime://auth/callback?...`.
    /// Non-auth URLs are ignored here — hosts carry no product logic.
    private func handleCallback(_ url: URL) {
        guard url.scheme?.lowercased() == "omi-rnruntime",
            url.host == "auth",
            url.path == "/callback" || url.path.isEmpty
        else {
            return
        }
        // The OAuth callback query lands here once the iOS browser leg is
        // wired to OmiAuthSession's BrowserAuthControlling; the session
        // module owns the exchange.
    }
}

/// `UserDefaults` backend for `SettingsStore` (same typing rules as the
/// macOS host: CFBoolean → bool, integer, string).
struct UserDefaultsKeyValueStore: KeyValueStoring {
    func value(forKey key: String) -> PreferenceValue? {
        guard let object = UserDefaults.standard.object(forKey: key) else {
            return nil
        }
        if let number = object as? NSNumber {
            if CFGetTypeID(number) == CFBooleanGetTypeID() {
                return .bool(number.boolValue)
            }
            return .integer(number.intValue)
        }
        if let string = object as? String {
            return .string(string)
        }
        return nil
    }

    func set(_ value: PreferenceValue?, forKey key: String) {
        let defaults = UserDefaults.standard
        guard let value else {
            defaults.removeObject(forKey: key)
            return
        }
        switch value {
        case .bool(let bool): defaults.set(bool, forKey: key)
        case .integer(let int): defaults.set(int, forKey: key)
        case .string(let string): defaults.set(string, forKey: key)
        }
    }
}
