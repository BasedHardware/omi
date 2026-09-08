import ContextCore
import Foundation
import LocalAuthentication
import Security

/// The credential set Context for Claude keeps between launches.
///
/// `expiryTime` is stored already-shortened (see `OmiAuth.expiryBuffer`) so every reader gets the
/// same answer to "is this usable?" without having to remember the safety margin.
struct OmiSession: Codable, Equatable, Sendable {
    let idToken: String
    let refreshToken: String
    /// Epoch seconds.
    let expiryTime: Double
    let tokenUserId: String

    var isExpired: Bool { Date().timeIntervalSince1970 >= expiryTime }
}

/// Context for Claude's own login-Keychain item — the only secret this app stores.
///
/// Deliberately **not** the Omi desktop app's `com.omi.desktop.firebase-rest-session.*` item, even
/// though it holds the same shape of session. That item's ACL is bound to the desktop app's signing
/// Team ID and code signature; a differently-signed binary reading it does not get a clean failure,
/// it gets the login-keychain password sheet ("Context for Claude wants to use your confidential information"),
/// which is both alarming and unanswerable. A separate service name means Context for Claude only ever touches
/// an item it created and therefore owns.
///
/// Two more constraints inherited from the same fix (desktop #9167):
/// - Never opt into the data-protection keychain (`kSecUseDataProtectionKeychain`). That requires a
///   `keychain-access-groups` entitlement a non-sandboxed Developer ID app does not have, and every
///   write fails with `errSecMissingEntitlement` (-34018) on the signed build.
/// - Never let SecItem raise UI: an `LAContext` with `interactionNotAllowed` makes calls that would
///   need a prompt fail closed instead. It is not a guarantee. `interactionNotAllowed` governs the
///   *LocalAuthentication* side; the login keychain's own access-control list is enforced by
///   `securityd`, which answers a request from a binary that is not on the item's trusted-application
///   list by putting the login-keychain password sheet on screen. That is the failure everything
///   below the `Refusal` mark exists for.
enum SessionStore {
    /// Keyed to the *running* bundle for the same reason it is not the desktop app's item: the ACL
    /// documented above is bound to the creating signature, and a dev build and the release are not
    /// the same signature. Sharing one service name between them is that password sheet again, from
    /// the one direction the fix above did not cover.
    static let service = service(for: ContextPaths.bundleIdentifier)
    static let account = "omi-session"

    static func service(for bundleIdentifier: String) -> String {
        "\(bundleIdentifier).session"
    }

    // MARK: - Refusals no retry can satisfy

    /// One Keychain read, as the OS answered it.
    ///
    /// A value rather than a pair of out-parameters so the decision below can be driven with a
    /// refusal the test machine's own keychain would never produce.
    struct KeychainRead {
        let status: OSStatus
        let data: Data?

        static func failed(_ status: OSStatus) -> KeychainRead { KeychainRead(status: status, data: nil) }
        static func succeeded(_ data: Data) -> KeychainRead { KeychainRead(status: errSecSuccess, data: data) }
    }

    /// **Whether `status` means this process is never going to be allowed to read this item.**
    ///
    /// A keychain item's ACL is bound to the code signature that created it. This app's move from an
    /// ad-hoc build to a notarized Developer ID one (team 9536L8KLMP) left an item on every existing
    /// install that the new binary is not on the trusted-application list of, and macOS answers each
    /// read of it with *"Context for Claude wants to access key 'Omi Context for Claude' in your
    /// keychain."* No number of retries changes a signature, so a second read is a second password
    /// sheet with the same answer — the same shape as the Screen Recording grant this app already
    /// stopped re-asking for (`Permissions.screenGrantIsStale`).
    ///
    /// Deliberately does **not** include `errSecItemNotFound` (-25300). That is not a refusal, it is
    /// "no credential stored" — the ordinary first-run and signed-out state, it raises no prompt, and
    /// latching it would make a real sign-in on a healthy Mac unreadable for the rest of the launch.
    /// Everything else recoverable (a locked keychain, an I/O fault, `errSecNotAvailable`) keeps its
    /// existing non-latching path for the same reason: those heal, and they do not prompt.
    static func isDefinitiveRefusal(_ status: OSStatus) -> Bool {
        switch status {
        case errSecAuthFailed, errSecUserCanceled, errSecInteractionNotAllowed, errSecInteractionRequired:
            return true
        default:
            return false
        }
    }

    /// The one refusal this process remembers.
    ///
    /// **In memory and never persisted**, for the reason `Permissions.screenCaptureDeclined` is not
    /// persisted either: what it holds is a fact about *this binary's signature*, and the very next
    /// launch may be a correctly-signed one that can read the item perfectly well. A stamp carried
    /// across a launch would condemn that process on evidence about a different one.
    static let refusal = KeychainRefusal()

    // MARK: - Read

    static func load() -> OmiSession? {
        load(read: liveRead, refusal: refusal)
    }

    /// The real decision, with the OS and the process's memory injected.
    ///
    /// `read` stands in for `SecItemCopyMatching` and nothing else; every rule below is the one that
    /// ships.
    static func load(read: () -> KeychainRead, refusal: KeychainRefusal) -> OmiSession? {
        // Before the SecItem call, which is the whole point: a read that already came back refused
        // is a password sheet this process has no way to answer differently. The app is left in the
        // state it was already showing — nothing signed in, and `ActivityAccountUnreachableReason`
        // `.signedOut` telling the user to sign in to Omi — but without asking again.
        guard !refusal.isSignalled else { return nil }

        let result = read()
        switch result.status {
        case errSecSuccess:
            guard let data = result.data else { return nil }
            guard let session = try? JSONDecoder().decode(OmiSession.self, from: data) else {
                // A shape we cannot read is worse than nothing: it would keep the app "signed in"
                // with no usable credential. Drop it so the next launch offers a clean sign-in.
                ContextLog.error("Stored session is unreadable; discarding it", "auth")
                clear()
                return nil
            }
            return session
        case errSecItemNotFound:
            // No credential stored. Nothing was prompted for and nothing is latched.
            return nil
        default:
            guard isDefinitiveRefusal(result.status) else {
                ContextLog.error("Keychain read unavailable (OSStatus \(result.status))", "auth")
                return nil
            }
            refusal.signal()
            // `milestone` rather than `error`: `info` is evicted from the unified log within minutes
            // and this is the line that explains why a signed-in Mac came up signed out.
            ContextLog.milestone(
                "The stored Omi session belongs to an earlier signature of this app, so macOS refused "
                    + "this process (OSStatus \(result.status)). Not asking again this launch — sign in "
                    + "to Omi to replace it.",
                "auth")
            return nil
        }
    }

    // MARK: - Write

    /// Update-then-add, never delete-then-add: a delete followed by a failing add turns a
    /// temporarily locked keychain into permanent session loss.
    ///
    /// The one exception is `replace`, below, and it is narrow on purpose — see there.
    @discardableResult
    static func save(_ session: OmiSession) -> Bool {
        save(session, ops: .live, refusal: refusal)
    }

    @discardableResult
    static func save(_ session: OmiSession, ops: KeychainOps, refusal: KeychainRefusal) -> Bool {
        guard let data = try? JSONEncoder().encode(session) else {
            ContextLog.error("Could not encode session for storage", "auth")
            return false
        }

        let updateStatus = ops.update(data)
        if updateStatus == errSecSuccess {
            refusal.clear()
            return true
        }

        // **The stale item, handled deliberately.** An item this signature may not touch is dead
        // weight: it will refuse every read and every update for as long as it exists, on this
        // install and on every fresh install that inherits it. Replacing it is safe *here and only
        // here* — this path holds a live session that was just signed in, so the credential being
        // discarded is one nothing in this process could ever have used, and a failing add costs
        // nothing that was readable. A failed **read** must never do this: that would destroy a
        // credential a correctly-signed build could still spend.
        if isDefinitiveRefusal(updateStatus) {
            ContextLog.milestone(
                "The stored Omi session cannot be updated by this signature (OSStatus \(updateStatus)); "
                    + "replacing it with the session that just signed in",
                "auth")
            let deleteStatus = ops.delete()
            guard deleteStatus == errSecSuccess || deleteStatus == errSecItemNotFound else {
                ContextLog.error("Could not remove the unreadable Keychain item (OSStatus \(deleteStatus))", "auth")
                return false
            }
            guard add(data, ops: ops) else { return false }
            // The item is ours again, so the refusal this launch recorded is spent.
            refusal.clear()
            return true
        }

        if updateStatus != errSecItemNotFound {
            ContextLog.error("Keychain update failed (OSStatus \(updateStatus))", "auth")
            return false
        }

        guard add(data, ops: ops) else { return false }
        refusal.clear()
        return true
    }

    private static func add(_ data: Data, ops: KeychainOps) -> Bool {
        let addStatus = ops.add(data)
        if addStatus == errSecSuccess { return true }
        if addStatus == errSecDuplicateItem {
            // Another process wrote between our update and our add.
            let retry = ops.update(data)
            if retry == errSecSuccess { return true }
            ContextLog.error("Keychain add/update race failed (OSStatus \(retry))", "auth")
            return false
        }
        ContextLog.error("Keychain add failed (OSStatus \(addStatus))", "auth")
        return false
    }

    // MARK: - Delete

    static func clear() {
        var query = baseQuery()
        applySilentAuth(&query)
        let status = SecItemDelete(query as CFDictionary)
        if status != errSecSuccess, status != errSecItemNotFound {
            ContextLog.error("Keychain delete failed (OSStatus \(status))", "auth")
        }
    }

    // MARK: - The OS

    /// The three writes, as closures, so `save` can be driven without a keychain.
    ///
    /// Only the calls themselves are behind this; every decision about what they mean lives in
    /// `save` above.
    struct KeychainOps {
        let update: (Data) -> OSStatus
        let add: (Data) -> OSStatus
        let delete: () -> OSStatus

        static let live = KeychainOps(update: liveUpdate, add: liveAdd, delete: liveDelete)
    }

    private static func liveRead() -> KeychainRead {
        var query = baseQuery()
        query[kSecReturnData as String] = true
        query[kSecMatchLimit as String] = kSecMatchLimitOne
        applySilentAuth(&query)

        var item: CFTypeRef?
        let status = SecItemCopyMatching(query as CFDictionary, &item)
        return KeychainRead(status: status, data: item as? Data)
    }

    private static func liveUpdate(_ data: Data) -> OSStatus {
        var query = baseQuery()
        applySilentAuth(&query)
        let attributes: [String: Any] = [
            kSecValueData as String: data,
            kSecAttrAccessible as String: kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly,
        ]
        return SecItemUpdate(query as CFDictionary, attributes as CFDictionary)
    }

    private static func liveAdd(_ data: Data) -> OSStatus {
        var addQuery = baseQuery()
        applySilentAuth(&addQuery)
        addQuery[kSecValueData as String] = data
        addQuery[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        addQuery[kSecAttrLabel as String] = "Omi Context for Claude"
        return SecItemAdd(addQuery as CFDictionary, nil)
    }

    private static func liveDelete() -> OSStatus {
        var query = baseQuery()
        applySilentAuth(&query)
        return SecItemDelete(query as CFDictionary)
    }

    // MARK: - Query construction

    private static func baseQuery() -> [String: Any] {
        [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
        ]
    }

    private static func applySilentAuth(_ query: inout [String: Any]) {
        let context = LAContext()
        context.interactionNotAllowed = true
        query[kSecUseAuthenticationContext as String] = context
    }
}

/// One-shot, resettable flag readable from another thread without blocking it.
///
/// The same shape as `Permissions`' private `Latch`, with a `clear()` the screen one has no use for:
/// a successful write proves the item is this signature's again, which is the one event that makes
/// the recorded refusal stale.
final class KeychainRefusal: @unchecked Sendable {
    private let lock = NSLock()
    private var signalled = false

    func signal() {
        lock.lock()
        signalled = true
        lock.unlock()
    }

    func clear() {
        lock.lock()
        signalled = false
        lock.unlock()
    }

    var isSignalled: Bool {
        lock.lock()
        defer { lock.unlock() }
        return signalled
    }
}
