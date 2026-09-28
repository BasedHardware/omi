#if compiler(>=6.4)
import Foundation
import Security
import FirebaseAuth
import FirebaseCore
import UIKit

/// A short-lived mirror lets an intent run before the Flutter engine exists.
/// Tokens are never stored in UserDefaults or in the Spotlight snapshot.
final class SiriSession {
    static let shared = SiriSession()
    #if OMI_SIRI_PROBE
    var beforeTokenLookup: (() -> Void)?
    var simulateKeychainDeleteFailureOnce = false
    var simulateKeychainDeleteFailuresRemaining = 0
    var simulateFirebaseTokenFailure = false
    #endif
    private let defaults: UserDefaults?
    private let keychainService = SiriStorageNamespace.current.keychainService
    private let keychainAccount = SiriStorageNamespace.current.keychainAccount
    private let configKey = SiriStorageNamespace.current.sessionConfigKey

    init(defaults: UserDefaults? = UserDefaults(suiteName: "group.com.friend-app-with-wearable.ios12")) {
        self.defaults = defaults
    }

    struct Config: Codable {
        let uid: String
        /// Optional for snapshots written before the generation was mirrored.
        let generation: Int64?
        let baseUrl: String
        let profile: String
        let appVersion: String
        let appBuild: String
        let deviceIdHash: String
        let expiresAtMs: Int64?
    }

    enum Failure: Error { case auth, invalidConfiguration, network, quota, rateLimited, server }

    func publish(_ input: SiriSessionConfig) throws {
        guard let defaults else { throw Failure.auth }
        guard !input.uid.isEmpty, let url = URL(string: input.baseUrl),
              ["http", "https"].contains(url.scheme ?? ""), url.host != nil else {
            throw Failure.invalidConfiguration
        }
        let config = Config(uid: input.uid, generation: input.generation,
                            baseUrl: input.baseUrl, profile: input.profile,
                            appVersion: input.appVersion, appBuild: input.appBuild,
                            deviceIdHash: input.deviceIdHash, expiresAtMs: input.tokenExpiresAtMs)
        let previous = currentConfig()
        if let previous, previous.uid != config.uid {
            clear()
        }
        defaults.set(try JSONEncoder().encode(config), forKey: configKey)
        SecItemDelete(keychainQuery() as CFDictionary)
        if let token = input.token, !token.isEmpty, let expiry = input.tokenExpiresAtMs,
           expiry > Int64(Date().timeIntervalSince1970 * 1000) + 60_000 {
            let bytes = Data(token.utf8)
            let item: [String: Any] = [kSecClass as String: kSecClassGenericPassword,
                                       kSecAttrService as String: keychainService,
                                       kSecAttrAccount as String: keychainAccount,
                                       kSecAttrAccessible as String: kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly,
                                       kSecValueData as String: bytes]
            guard SecItemAdd(item as CFDictionary, nil) == errSecSuccess else { throw Failure.auth }
        }
    }

    func currentConfig() -> Config? {
        guard let data = defaults?.data(forKey: configKey) else { return nil }
        return try? JSONDecoder().decode(Config.self, from: data)
    }

    func clear() {
        defaults?.removeObject(forKey: configKey)
        SecItemDelete(keychainQuery() as CFDictionary)
    }

    /// Revoke the engine-free credential independently of the pending-wipe
    /// marker. Keep the config until the queued wipe so either fence can deny
    /// requests even when the other persistence operation fails.
    @discardableResult
    func revokeMirroredTokenForSignOut() -> Bool {
        #if OMI_SIRI_PROBE
        if simulateKeychainDeleteFailuresRemaining > 0 {
            simulateKeychainDeleteFailuresRemaining -= 1
            return false
        }
        if simulateKeychainDeleteFailureOnce {
            simulateKeychainDeleteFailureOnce = false
            return false
        }
        #endif
        let status = SecItemDelete(keychainQuery() as CFDictionary)
        return status == errSecSuccess || status == errSecItemNotFound
    }

    func hasMirroredToken() -> Bool {
        var query = keychainQuery()
        query[kSecReturnAttributes as String] = true
        query[kSecMatchLimit as String] = kSecMatchLimitOne
        return SecItemCopyMatching(query as CFDictionary, nil) == errSecSuccess
    }

    /// Pinned FirebaseAuth 11.10.0, Auth.swift:1671-1705, enqueues saved-user
    /// Keychain hydration on kAuthGlobalWorkQueue. Auth.swift:174-178 makes
    /// currentUser synchronize on that same queue, so this read waits
    /// for the initial hydration attempt. A locked Keychain is the exception:
    /// Firebase retries after protected data becomes available, and Siri must
    /// deny temporarily without destroying the signed-in account's index.
    func requireFirebaseOwner(_ uid: String) throws -> User? {
        #if OMI_SIRI_PROBE
        // The legacy loopback probe deliberately uses synthetic UIDs. The
        // separate Auth-emulator probe exercises this real authorization gate.
        if ProcessInfo.processInfo.arguments.contains("-omi-siri-probe") { return nil }
        #endif
        if FirebaseApp.app() == nil { FirebaseApp.configure() }
        let user = Auth.auth().currentUser
        guard let user, user.uid == uid else {
            if user == nil && !UIApplication.shared.isProtectedDataAvailable {
                SiriSnapshotStore.shared.setAuthResolutionPending(true)
            } else {
                SiriSnapshotStore.shared.prepareForSignOut()
            }
            throw Failure.auth
        }
        SiriSnapshotStore.shared.setAuthResolutionPending(false)
        return user
    }

    /// A pure check for callers already holding the snapshot lock. The public
    /// request/read entry points run requireFirebaseOwner first to fence a
    /// definitive mismatch outside that lock.
    func hasCurrentFirebaseOwner(_ uid: String) -> Bool {
        #if OMI_SIRI_PROBE
        if ProcessInfo.processInfo.arguments.contains("-omi-siri-probe") { return true }
        #endif
        return FirebaseApp.app() != nil && Auth.auth().currentUser?.uid == uid
    }

    func validateOwner(_ config: Config) throws {
        _ = try requireFirebaseOwner(config.uid)
        guard hasMirroredToken(), let current = currentConfig(), current.uid == config.uid,
              (current.generation ?? 0) == (config.generation ?? 0),
              SiriSnapshotStore.shared.generationForOwner(config.uid) == (config.generation ?? 0)
        else { throw Failure.auth }
    }

    func token(for config: Config) async throws -> String {
        #if OMI_SIRI_PROBE
        beforeTokenLookup?()
        #endif
        try validateOwner(config)
        let user = try requireFirebaseOwner(config.uid)
        // The mirror is only a token fallback for this same native Firebase
        // user, never an alternative source of account authorization.
        #if OMI_SIRI_PROBE
        let skipFirebaseToken = simulateFirebaseTokenFailure
        #else
        let skipFirebaseToken = false
        #endif
        if !skipFirebaseToken, let user,
           let fresh = try? await user.getIDToken(), !fresh.isEmpty {
            try validateOwner(config)
            return fresh
        }
        guard let expiry = config.expiresAtMs,
              expiry > Int64(Date().timeIntervalSince1970 * 1000) + 60_000 else {
            throw Failure.auth
        }
        var query = keychainQuery()
        query[kSecReturnData as String] = true
        query[kSecMatchLimit as String] = kSecMatchLimitOne
        var result: CFTypeRef?
        guard SecItemCopyMatching(query as CFDictionary, &result) == errSecSuccess,
              let data = result as? Data, let token = String(data: data, encoding: .utf8),
              !token.isEmpty else { throw Failure.auth }
        try validateOwner(config)
        return token
    }

    func token() async throws -> String {
        guard let config = currentConfig() else { throw Failure.auth }
        return try await token(for: config)
    }

    private func keychainQuery() -> [String: Any] {
        [kSecClass as String: kSecClassGenericPassword,
         kSecAttrService as String: keychainService,
         kSecAttrAccount as String: keychainAccount]
    }
}

struct OmiNativeAPI {
    #if OMI_SIRI_PROBE
    static var testSession: URLSession?
    #endif
    func request(method: String, path: String, body: [String: Any],
                 owner: SiriSession.Config? = nil) async throws -> [String: Any] {
        guard let config = owner ?? SiriSession.shared.currentConfig() else { throw SiriSession.Failure.auth }
        guard let base = URL(string: config.baseUrl),
              let url = URL(string: path, relativeTo: base)?.absoluteURL,
              url.host == base.host else { throw SiriSession.Failure.invalidConfiguration }
        var request = URLRequest(url: url)
        request.httpMethod = method
        request.timeoutInterval = 8
        request.setValue("Bearer \(try await SiriSession.shared.token(for: config))", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue(String(Date().timeIntervalSince1970), forHTTPHeaderField: "X-Request-Start-Time")
        request.setValue("ios", forHTTPHeaderField: "X-App-Platform")
        request.setValue(config.deviceIdHash, forHTTPHeaderField: "X-Device-Id-Hash")
        request.setValue(config.appVersion, forHTTPHeaderField: "X-App-Version")
        request.setValue(config.appBuild, forHTTPHeaderField: "X-App-Build")
        request.httpBody = try JSONSerialization.data(withJSONObject: body)
        try SiriSession.shared.validateOwner(config)
        let data: Data
        let response: URLResponse
        #if OMI_SIRI_PROBE
        let session = Self.testSession ?? .shared
        #else
        let session = URLSession.shared
        #endif
        do { (data, response) = try await session.data(for: request) }
        catch { throw SiriSession.Failure.network }
        try SiriSession.shared.validateOwner(config)
        guard let http = response as? HTTPURLResponse else { throw SiriSession.Failure.network }
        switch http.statusCode {
        case 200...299:
            guard let object = try? JSONSerialization.jsonObject(with: data),
                  let json = object as? [String: Any] else { throw SiriSession.Failure.server }
            return json
        case 401, 403: throw SiriSession.Failure.auth
        case 402: throw SiriSession.Failure.quota
        case 429: throw SiriSession.Failure.rateLimited
        default: throw SiriSession.Failure.server
        }
    }
}
#endif
