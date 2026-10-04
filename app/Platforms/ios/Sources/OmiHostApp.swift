import SwiftUI

#if canImport(AuthenticationServices)
import AuthenticationServices
import UIKit
#endif

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
//     CoreBluetooth device transport. Sign-in presents the system
//     authentication session with the app-specific
//     `omi-rnruntime://auth/callback` redirect and PKCE
//     (docs/auth-and-sessions.md); the session owns the exchange.

@main
struct OmiHostApp: App {
    @StateObject private var store: AppStore

    init() {
        let credentials = KeychainCredentialStore()
        let planeStore = UserDefaultsSoftwarePlaneStore()
        let origin = Self.stampedV5Origin()
        let auth = OmiAuthSession(
            config: AuthSessionConfig(
                firebaseApiKey: Bundle.main.object(
                    forInfoDictionaryKey: "OMIFirebaseAPIKey") as? String ?? "",
                v5BackendOrigin: origin,
                legacyRedirectURI: AppSchemeBrowserAuth.redirectURI),
            credentials: credentials,
            browserAuth: AppSchemeBrowserAuth(), planeStore: planeStore)
        let backend = HTTPBackendTransport(
            credentials: credentials,
            planeSelection: HTTPBackendTransport.PlaneSelection(
                storedPlane: UserDefaults.standard.string(
                    forKey: SOFTWARE_PLANE_DEFAULTS_KEY),
                stampedValid: origin != nil),
            originOverride: origin,
            bearerResolver: { await auth.resolveBearerToken() }, planeStore: planeStore)
        let journalRoot = FileManager.default.urls(
            for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("Omi/RecordingJournals", isDirectory: true)
        let transport = EncryptedRecordingJournalTransport(
            backend: backend,
            ownerProvider: AppleRecordingJournalOwnerProvider(transport: backend),
            vault: AppleKeychainRecordingJournalVault(),
            files: POSIXAtomicRecordingJournalFiles(), root: journalRoot)
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
        }
    }

    /// The stamped New-plane origin, per RELEASE.md (`OMI_V5_BACKEND_URL`,
    /// allowlisted). Nil when unset, so sign-in uses the legacy flow.
    private static func stampedV5Origin() -> String? {
        guard
            let raw = ProcessInfo.processInfo.environment[V5_BACKEND_URL_ENV],
            let origin = parseOrigin(raw),
            isAllowedV5Hostname(origin.hostname)
        else {
            return nil
        }
        return origin.origin
    }
}

#if canImport(AuthenticationServices)
/// The iOS browser leg: the system authentication session with the
/// app-specific callback scheme, mirroring the RN iOS module. The session
/// intercepts `omi-rnruntime://auth/callback` itself, so no `onOpenURL`
/// plumbing is involved.
@MainActor
final class AppSchemeBrowserAuth: NSObject, BrowserAuthControlling {
    static let redirectURI = "omi-rnruntime://auth/callback"
    private static let callbackScheme = "omi-rnruntime"

    private var activeSession: ASWebAuthenticationSession?
    private var sessionGeneration = BrowserAuthSessionGeneration()

    func presentAuthorizeURL(_ url: String, state: String) async -> String? {
        // One outstanding browser leg at a time: a new request cancels the
        // previous wait (matches OmiAuthSession attempt fencing).
        activeSession?.cancel()
        activeSession = nil
        let generation = sessionGeneration.beginAttempt()
        guard let authorizeURL = URL(string: url) else { return nil }
        return await startBrowserAuthSession { completion in
            let session = ASWebAuthenticationSession(
                url: authorizeURL,
                callbackURLScheme: Self.callbackScheme
            ) { [weak self] callbackURL, error in
                let result = error == nil ? callbackURL?.absoluteString : nil
                Task { @MainActor in
                    if self?.sessionGeneration.isCurrent(generation) == true {
                        self?.activeSession = nil
                    }
                    completion(result)
                }
            }
            session.presentationContextProvider = self
            activeSession = session
            let started = session.start()
            if !started, sessionGeneration.isCurrent(generation) {
                activeSession = nil
            }
            return started
        }
    }
}

extension AppSchemeBrowserAuth: ASWebAuthenticationPresentationContextProviding {
    func presentationAnchor(for session: ASWebAuthenticationSession)
        -> ASPresentationAnchor
    {
        let scenes = UIApplication.shared.connectedScenes
        let windowScene = scenes.first { $0.activationState == .foregroundActive }
            as? UIWindowScene
        return windowScene?.windows.first ?? ASPresentationAnchor()
    }
}
#endif

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
