import Foundation
import Security
import FirebaseAuth
import FirebaseCore

/// A short-lived mirror lets an intent run before the Flutter engine exists.
/// Tokens are never stored in UserDefaults or in the Spotlight snapshot.
final class SiriSession {
    static let shared = SiriSession()
    private let defaults = UserDefaults(suiteName: "group.com.friend-app-with-wearable.ios12")!
    private let keychainService = "com.omi.siri.session"
    private let keychainAccount = "firebase-id-token"
    private let configKey = "siri.session.config"

    struct Config: Codable {
        let uid: String
        let baseUrl: String
        let profile: String
        let appVersion: String
        let appBuild: String
        let deviceIdHash: String
        let expiresAtMs: Int64?
    }

    enum Failure: Error { case auth, invalidConfiguration, network, quota, rateLimited, server }

    func publish(_ input: SiriSessionConfig) throws {
        guard !input.uid.isEmpty, let url = URL(string: input.baseUrl),
              ["http", "https"].contains(url.scheme ?? ""), url.host != nil else {
            throw Failure.invalidConfiguration
        }
        let config = Config(uid: input.uid, baseUrl: input.baseUrl, profile: input.profile,
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
        guard let data = defaults.data(forKey: configKey) else { return nil }
        return try? JSONDecoder().decode(Config.self, from: data)
    }

    func clear() {
        defaults.removeObject(forKey: configKey)
        SecItemDelete(keychainQuery() as CFDictionary)
    }

    func token() async throws -> String {
        guard let config = currentConfig() else { throw Failure.auth }
        // Try Firebase first. On a clean background Runner launch, the SDK can
        // lack a hydrated user; the bounded mirror below is the fallback.
        if FirebaseApp.app() == nil { FirebaseApp.configure() }
        if let user = Auth.auth().currentUser, user.uid == config.uid {
            if let fresh = try? await user.getIDToken(), !fresh.isEmpty { return fresh }
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
        return token
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
    func request(method: String, path: String, body: [String: Any]) async throws -> [String: Any] {
        guard let config = SiriSession.shared.currentConfig(),
              let base = URL(string: config.baseUrl),
              let url = URL(string: path, relativeTo: base)?.absoluteURL,
              url.host == base.host else { throw SiriSession.Failure.invalidConfiguration }
        var request = URLRequest(url: url)
        request.httpMethod = method
        request.timeoutInterval = 8
        request.setValue("Bearer \(try await SiriSession.shared.token())", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue(String(Date().timeIntervalSince1970), forHTTPHeaderField: "X-Request-Start-Time")
        request.setValue("ios", forHTTPHeaderField: "X-App-Platform")
        request.setValue(config.deviceIdHash, forHTTPHeaderField: "X-Device-Id-Hash")
        request.setValue(config.appVersion, forHTTPHeaderField: "X-App-Version")
        request.setValue(config.appBuild, forHTTPHeaderField: "X-App-Build")
        request.httpBody = try JSONSerialization.data(withJSONObject: body)
        let data: Data
        let response: URLResponse
        #if OMI_SIRI_PROBE
        let session = Self.testSession ?? .shared
        #else
        let session = URLSession.shared
        #endif
        do { (data, response) = try await session.data(for: request) }
        catch { throw SiriSession.Failure.network }
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
