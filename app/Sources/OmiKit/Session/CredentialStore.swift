import Foundation
#if !SKIP && canImport(Security)
import Security
#endif

// Credential storage seam for the native session. Tokens never cross into
// product code: the transport injects the Bearer and the auth flows own
// minting/refresh.

public struct StoredSession: Sendable, Equatable {
    public var idToken: String
    public var refreshToken: String
    /// Epoch milliseconds; 0 when unknown (refresh on every use).
    public var expiresAtMs: Int64
    public var uid: String?
    public var firebaseApiKey: String?

    public init(
        idToken: String, refreshToken: String, expiresAtMs: Int64 = 0,
        uid: String? = nil, firebaseApiKey: String? = nil
    ) {
        self.idToken = idToken
        self.refreshToken = refreshToken
        self.expiresAtMs = expiresAtMs
        self.uid = uid
        self.firebaseApiKey = firebaseApiKey
    }
}

public protocol CredentialStoring: Sendable {
    func load() async -> StoredSession?
    func store(_ session: StoredSession) async
    func clear() async
}

/// In-memory store for tests and unsigned hosts.
public final class InMemoryCredentialStore: CredentialStoring, @unchecked Sendable {
    private var session: StoredSession?
    private let lock = NSLock()

    public init() {}

    public func load() async -> StoredSession? {
        loadSync()
    }

    public func store(_ session: StoredSession) async {
        storeSync(session)
    }

    public func clear() async {
        clearSync()
    }

    private func loadSync() -> StoredSession? {
        lock.lock()
        defer { lock.unlock() }
        return session
    }

    private func storeSync(_ session: StoredSession) {
        lock.lock()
        self.session = session
        lock.unlock()
    }

    private func clearSync() {
        lock.lock()
        session = nil
        lock.unlock()
    }
}

#if !SKIP && canImport(Security)
/// Apple Keychain-backed store. Session items live in the app's keychain
/// access group with `kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly`.
public final class KeychainCredentialStore: CredentialStoring, @unchecked Sendable {
    public static let service = "app.omi.v5.session"

    private let account: String

    public init(account: String = "default") {
        self.account = account
    }

    private func baseQuery() -> [String: Any] {
        [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: Self.service,
            kSecAttrAccount as String: account,
        ]
    }

    public func load() async -> StoredSession? {
        var query = baseQuery()
        query[kSecReturnData as String] = true
        query[kSecMatchLimit as String] = kSecMatchLimitOne
        var item: CFTypeRef?
        let status = SecItemCopyMatching(query as CFDictionary, &item)
        guard status == errSecSuccess, let data = item as? Data else { return nil }
        guard let payload = try? JSONDecoder().decode(Payload.self, from: data) else {
            return nil
        }
        return StoredSession(
            idToken: payload.idToken, refreshToken: payload.refreshToken,
            expiresAtMs: payload.expiresAtMs, uid: payload.uid,
            firebaseApiKey: payload.firebaseApiKey)
    }

    public func store(_ session: StoredSession) async {
        let payload = Payload(
            idToken: session.idToken, refreshToken: session.refreshToken,
            expiresAtMs: session.expiresAtMs, uid: session.uid,
            firebaseApiKey: session.firebaseApiKey)
        guard let data = try? JSONEncoder().encode(payload) else { return }
        let status = SecItemUpdate(
            baseQuery() as CFDictionary,
            [kSecValueData as String: data] as CFDictionary)
        if status == errSecItemNotFound {
            var add = baseQuery()
            add[kSecValueData as String] = data
            add[kSecAttrAccessible as String] =
                kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
            SecItemAdd(add as CFDictionary, nil)
        }
    }

    public func clear() async {
        SecItemDelete(baseQuery() as CFDictionary)
    }

    private struct Payload: Codable {
        var idToken: String
        var refreshToken: String
        var expiresAtMs: Int64
        var uid: String?
        var firebaseApiKey: String?
    }
}
#endif
