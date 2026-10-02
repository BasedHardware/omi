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
    public var loginGeneration: String?
    public var recordingOwner: StoredRecordingOwner?

    public init(
        idToken: String, refreshToken: String, expiresAtMs: Int64 = 0,
        uid: String? = nil, firebaseApiKey: String? = nil,
        loginGeneration: String? = nil, recordingOwner: StoredRecordingOwner? = nil
    ) {
        self.idToken = idToken
        self.refreshToken = refreshToken
        self.expiresAtMs = expiresAtMs
        self.uid = uid
        self.firebaseApiKey = firebaseApiKey
        self.loginGeneration = loginGeneration
        self.recordingOwner = recordingOwner
    }
}

/// Persisted only inside the platform credential store, never journal files.
public struct StoredRecordingOwner: Codable, Sendable, Equatable {
    public var backendOrigin: String
    public var ownerKey: String
    public var receipt: String

    public init(backendOrigin: String, ownerKey: String, receipt: String) {
        self.backendOrigin = backendOrigin
        self.ownerKey = ownerKey
        self.receipt = receipt
    }
}

#if !SKIP && canImport(Security)
/// Synchronous, serialized secure transactions fence every asynchronous auth
/// response. The revision also changes on logout of an already empty session.
public struct SecureSessionSnapshot: Sendable {
    public let revision: String
    public let session: StoredSession?
    public init(revision: String, session: StoredSession?) {
        self.revision = revision
        self.session = session
    }
}

public enum SecureSessionError: Error { case unavailable, changed }

public protocol SecureSessionCredentialStoring: CredentialStoring {
    func secureSnapshot() throws -> SecureSessionSnapshot
    func replaceSession(_ session: StoredSession?, expecting revision: String) throws
    func clearSecureSession() throws
}
#endif

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
public final class KeychainCredentialStore: SecureSessionCredentialStoring, @unchecked Sendable {
    public static let service = "app.omi.v5.session"
    private let account: String
    private let lock = NSLock()
    private var revision = UUID().uuidString
    private var fenced = false

    public init(account: String = "default") { self.account = account }

    private func baseQuery() -> [String: Any] {
        [kSecClass as String: kSecClassGenericPassword,
         kSecAttrService as String: Self.service,
         kSecAttrAccount as String: account]
    }

    public func secureSnapshot() throws -> SecureSessionSnapshot {
        try lock.withLock {
            SecureSessionSnapshot(revision: revision, session: try readLocked())
        }
    }

    private func readLocked() throws -> StoredSession? {
        if fenced { return nil }
        var query = baseQuery()
        query[kSecReturnData as String] = true
        query[kSecMatchLimit as String] = kSecMatchLimitOne
        var item: CFTypeRef?
        let status = SecItemCopyMatching(query as CFDictionary, &item)
        if status == errSecItemNotFound { return nil }
        guard status == errSecSuccess, let data = item as? Data,
            let payload = try? JSONDecoder().decode(Payload.self, from: data)
        else { throw SecureSessionError.unavailable }
        return StoredSession(
            idToken: payload.idToken, refreshToken: payload.refreshToken,
            expiresAtMs: payload.expiresAtMs, uid: payload.uid,
            firebaseApiKey: payload.firebaseApiKey,
            loginGeneration: payload.loginGeneration, recordingOwner: payload.recordingOwner)
    }

    public func replaceSession(_ session: StoredSession?, expecting expected: String) throws {
        try lock.withLock {
            guard revision == expected else { throw SecureSessionError.changed }
            try writeLocked(session)
        }
    }

    private func writeLocked(_ session: StoredSession?) throws {
        // Invalidate in-flight snapshots even if the secure write fails.
        revision = UUID().uuidString
        guard let session else {
            fenced = true
            let status = SecItemDelete(baseQuery() as CFDictionary)
            guard status == errSecSuccess || status == errSecItemNotFound else {
                throw SecureSessionError.unavailable
            }
            return
        }
        let data = try JSONEncoder().encode(Payload(
            idToken: session.idToken, refreshToken: session.refreshToken,
            expiresAtMs: session.expiresAtMs, uid: session.uid,
            firebaseApiKey: session.firebaseApiKey,
            loginGeneration: session.loginGeneration, recordingOwner: session.recordingOwner))
        var status = SecItemUpdate(baseQuery() as CFDictionary,
            [kSecValueData as String: data] as CFDictionary)
        if status == errSecItemNotFound {
            var add = baseQuery()
            add[kSecValueData as String] = data
            add[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
            status = SecItemAdd(add as CFDictionary, nil)
        }
        guard status == errSecSuccess else { throw SecureSessionError.unavailable }
        fenced = false
        guard try readLocked() == session else {
            fenced = true
            throw SecureSessionError.unavailable
        }
    }

    public func clearSecureSession() throws {
        try lock.withLock { try writeLocked(nil) }
    }
    public func load() async -> StoredSession? { try? secureSnapshot().session }
    public func store(_ session: StoredSession) async {
        try? lock.withLock { try writeLocked(session) }
    }
    public func clear() async { try? clearSecureSession() }

    private struct Payload: Codable {
        var idToken: String
        var refreshToken: String
        var expiresAtMs: Int64
        var uid: String?
        var firebaseApiKey: String?
        var loginGeneration: String?
        var recordingOwner: StoredRecordingOwner?
    }
}
#endif
