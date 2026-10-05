import Foundation

// Session/auth flows that are transport-level, ported from the native auth
// modules (see docs/auth-and-sessions.md):
//   - Firebase REST session refresh (securetoken.googleapis.com/v1/token)
//   - Firebase custom-token redemption
//     (identitytoolkit.googleapis.com/v1/accounts:signInWithCustomToken)
//   - Desktop handoff against the v5 Worker (/v1/auth/desktop/start, poll
//     /v1/auth/desktop/exchange) with PKCE-style SHA-256 challenges
//   - Legacy OAuth PKCE exchange (api.omi.me/v1/auth/token), with the
//     browser/loopback leg supplied by the host via `BrowserAuthControlling`
//
// The plane is pinned AFTER the session stores: a failed redemption can
// never flip the user's chosen plane.

public enum AuthError: Error, Sendable, Equatable {
    case unconfigured
    case unauthorized(String)
    case transport
    case cancelled
    case expired
}

/// Copy the card can show. Sign-in must not fail without a reason.
public func signInFailureCopy(_ error: AuthError) -> String {
    switch error {
    case .unconfigured:
        return "Sign in is not configured on this build."
    case .unauthorized(let message):
        return message
    case .transport:
        return "Could not reach Omi to finish sign in."
    case .cancelled:
        return "Sign in was cancelled."
    case .expired:
        return "Sign in expired. Try again."
    }
}

/// Host-supplied browser leg for the legacy loopback OAuth flow.
public protocol BrowserAuthControlling: Sendable {
    /// Presents the authorize URL and resolves with the loopback callback
    /// URL, or nil when the user cancelled.
    func presentAuthorizeURL(_ url: String, state: String) async -> String?
}

#if !SKIP
/// Fences callbacks from a browser session that was replaced by a newer
/// sign-in attempt.
public struct BrowserAuthSessionGeneration: Sendable {
    private var current: UInt64 = 0

    public init() {}

    public mutating func beginAttempt() -> UInt64 {
        current &+= 1
        return current
    }

    public func isCurrent(_ generation: UInt64) -> Bool {
        generation == current
    }
}

/// Bridges a native browser session's synchronous start result and its later
/// callback. A failed `start()` has no callback to resume the waiter, so it
/// must finish immediately; the one-shot completion also tolerates a callback
/// racing with that failure result.
@MainActor
public func startBrowserAuthSession(
    _ start: @MainActor (@escaping @MainActor @Sendable (String?) -> Void) -> Bool
) async -> String? {
    await withCheckedContinuation { continuation in
        var didResume = false
        let finish: @MainActor @Sendable (String?) -> Void = { result in
            guard !didResume else { return }
            didResume = true
            continuation.resume(returning: result)
        }
        if !start(finish) {
            finish(nil)
        }
    }
}
#endif

public struct AuthSessionConfig: Sendable {
    public var firebaseApiKey: String
    /// The stamped, validated v5 origin, when the New plane is stamped.
    public var v5BackendOrigin: String?
    public var legacyAuthorizeURL: String
    public var legacyRedirectURI: String

    public init(
        firebaseApiKey: String, v5BackendOrigin: String? = nil,
        legacyAuthorizeURL: String = "https://api.omi.me/v1/auth/authorize",
        legacyRedirectURI: String = "http://127.0.0.1:0/callback"
    ) {
        self.firebaseApiKey = firebaseApiKey
        self.v5BackendOrigin = v5BackendOrigin
        self.legacyAuthorizeURL = legacyAuthorizeURL
        self.legacyRedirectURI = legacyRedirectURI
    }
}

/// SHA-256 → base64url, shared by PKCE and the desktop handoff.
public enum AuthCrypto {
    public static func sha256Base64URL(_ value: String) -> String? {
        sha256Base64URL(bytes: Array(value.utf8))
    }

    static func sha256Base64URL(bytes: [UInt8]) -> String? {
        guard let digest = Policy.authSHA256(bytes) else { return nil }
        return Base64Codec.encodeURL(digest)
    }

    /// `sha256url(challenge + "\0" + confirmationChallenge)` — mirrors the
    /// Worker's `deriveSessionId`.
    public static func deriveDesktopSessionId(
        challenge: String, confirmationChallenge: String
    ) -> String? {
        sha256Base64URL(
            bytes: Array(challenge.utf8) + [UInt8(0)] + Array(confirmationChallenge.utf8))
    }

    /// Six decimal digits, rejection-sampled over 000000-999999.
    public static func confirmationCode() -> String? {
        for _ in 0..<16 {
            guard let bytes = Policy.authRandomBytes(4), bytes.count == 4 else { return nil }
            let raw =
                (Int64(bytes[0]) << 24) | (Int64(bytes[1]) << 16)
                | (Int64(bytes[2]) << 8) | Int64(bytes[3])
            if raw < Int64(4_294_000_000) {
                return String(format: "%06d", Int(raw % Int64(1_000_000)))
            }
        }
        return nil
    }
    public static func randomValue() -> String? {
        guard let bytes = Policy.authRandomBytes(32), bytes.count == 32 else { return nil }
        return Base64Codec.encodeURL(bytes)
    }
}

/// The legacy browser-leg authorize URL, mirroring the native module's
/// query (`OmiAuthModule.mm`): `provider=google`, the redirect URI, state,
/// and the PKCE S256 challenge. api.omi.me 307s this to Google OAuth with
/// its own client — the client sends no client_id or response_type. The
/// old default path `/v1/auth/google` does not exist upstream (404).
public func legacyAuthorizeURL(
    base: String, redirectURI: String, state: String, codeChallenge: String
) -> String? {
    guard !base.isEmpty, !base.contains("?"), !base.contains("#"), URL(string: base) != nil
    else { return nil }
    let items = [
        ("provider", "google"),
        ("redirect_uri", redirectURI),
        ("state", state),
        ("code_challenge", codeChallenge),
        ("code_challenge_method", "S256"),
    ]
    return base + "?"
        + items.map { encodeQueryItemPart($0.0) + "=" + encodeQueryItemPart($0.1) }
            .joined(separator: "&")
}

/// The callback shape check the native module applies before exchange: the
/// callback must match the armed redirect URI (macOS loopback `http://
/// 127.0.0.1:<port>/callback` or the iOS app scheme
/// `omi-rnruntime://auth/callback`), carry no fragment, and echo the state
/// with a non-empty code. Returns that code, or nil.
public func authCallbackCode(
    _ callback: String, redirectURI: String, expectedState: String
) -> String? {
    for value in [callback, redirectURI, expectedState] where Array(value.utf8).contains(UInt8(0)) {
        return nil
    }
    return Policy.authCallbackCode(callback, redirectURI: redirectURI, expectedState: expectedState)
}

/// Collect one bounded HTTP header block from a fragmented loopback callback.
/// TCP does not preserve HTTP request boundaries, so the macOS host must wait
/// for the header terminator before parsing the callback query.
public struct AuthHTTPRequestHeaderAccumulator: Sendable {
    public enum AppendResult: Equatable, Sendable {
        case incomplete
        case complete(String)
        case invalidEncoding
        case tooLarge
    }

    private let maximumBytes: Int
    private var bytes: [UInt8] = []

    public init(maximumBytes: Int = 16 * 1024) {
        self.maximumBytes = max(1, maximumBytes)
    }

    public mutating func append(_ chunk: Data) -> AppendResult {
        guard chunk.count <= maximumBytes - bytes.count else { return .tooLarge }
        for index in 0..<chunk.count {
            bytes.append(chunk[index])
        }

        let headerEnd =
            Self.terminatorEnd(
                bytes,
                [UInt8(13), UInt8(10), UInt8(13), UInt8(10)])
            ?? Self.terminatorEnd(bytes, [UInt8(10), UInt8(10)])

        if let headerEnd {
            guard
                let request = String(
                    data: Data(Array(bytes[0..<headerEnd])), encoding: String.Encoding.utf8)
            else {
                return .invalidEncoding
            }
            return .complete(request)
        }
        return bytes.count == maximumBytes ? .tooLarge : .incomplete
    }

    private static func terminatorEnd(_ bytes: [UInt8], _ terminator: [UInt8]) -> Int? {
        guard bytes.count >= terminator.count else { return nil }
        for start in 0...(bytes.count - terminator.count) {
            var matches = true
            for offset in 0..<terminator.count where bytes[start + offset] != terminator[offset] {
                matches = false
                break
            }
            if matches { return start + terminator.count }
        }
        return nil
    }
}

public final class OmiAuthSession: Authenticating, SessionProbeCapable, @unchecked Sendable {
    private let config: AuthSessionConfig
    private let credentials: CredentialStoring
    private let browserAuth: BrowserAuthControlling?
    private let handoffStream: AsyncStream<DesktopHandoff>
    private let emitHandoff: @Sendable (DesktopHandoff) -> Void
    private let invalidationStream: AsyncStream<Void>
    private let invalidationContinuation: AsyncStream<Void>.Continuation
    private let lock = NSLock()
    private var signInAttempt: Int = 0
    private var settled = true
    private var attemptRevision: String?
    private let urlSession: URLSession
    private let planeStore: SoftwarePlaneStoring

    public init(
        config: AuthSessionConfig, credentials: CredentialStoring,
        browserAuth: BrowserAuthControlling? = nil, urlSession: URLSession = .shared,
        planeStore: SoftwarePlaneStoring = UserDefaultsSoftwarePlaneStore()
    ) {
        self.config = config
        self.credentials = credentials
        self.browserAuth = browserAuth
        self.urlSession = urlSession
        self.planeStore = planeStore
        let handoffs = AsyncStream.makeStream(of: DesktopHandoff.self)
        self.handoffStream = handoffs.stream
        let handoffContinuation = handoffs.continuation
        self.emitHandoff = { handoffContinuation.yield($0) }
        let invalidations = AsyncStream.makeStream(of: Void.self)
        self.invalidationStream = invalidations.stream
        self.invalidationContinuation = invalidations.continuation
    }

    public var desktopHandoffs: AsyncStream<DesktopHandoff> { handoffStream }
    public var sessionInvalidated: AsyncStream<Void> { invalidationStream }

    // MARK: Session refresh (Firebase REST)

    /// Returns a fresh Bearer id token, or nil when no session is stored.
    /// A definitive refresh failure clears the stored session.
    public func resolveBearerToken() async -> String? {
        #if !SKIP && canImport(Security)
        let secure = credentials as? SecureSessionCredentialStoring
        let snapshot: SecureSessionSnapshot?
        do { snapshot = try secure?.secureSnapshot() } catch { return nil }
        #endif
        guard var session = await credentials.load() else { return nil }
        #if !SKIP && canImport(Security)
        if let snapshot, snapshot.session != session { return nil }
        #endif
        let nowMs = Int64(Date().timeIntervalSince1970 * 1000)
        if session.expiresAtMs > nowMs + 60_000, !session.idToken.isEmpty {
            return session.idToken
        }
        guard !session.refreshToken.isEmpty else {
            #if !SKIP && canImport(Security)
            if let secure, let snapshot {
                do { try secure.replaceSession(nil, expecting: snapshot.revision) }
                catch { return nil }
            } else { await credentials.clear() }
            #else
            await credentials.clear()
            #endif
            invalidationContinuation.yield()
            return nil
        }
        let apiKey = session.firebaseApiKey ?? config.firebaseApiKey
        guard !apiKey.isEmpty else { return nil }
        var request = URLRequest(
            url: URL(string: "https://securetoken.googleapis.com/v1/token?key=\(apiKey)")!)
        request.httpMethod = "POST"
        request.setValue(
            "application/x-www-form-urlencoded", forHTTPHeaderField: "content-type")
        request.httpBody = Data(
            "grant_type=refresh_token&refresh_token=\(encodeQueryComponent(session.refreshToken))"
                .utf8)
        guard let (data, response) = try? await urlSession.data(for: request),
            let http = response as? HTTPURLResponse, http.statusCode == 200,
            let body = JSON.parseOrNull(String(data: data, encoding: String.Encoding.utf8)),
            body.isRecord,
            let idToken = body["id_token"]?.stringValue,
            let refreshToken = body["refresh_token"]?.stringValue
        else {
            // Transient failures keep the session; only the caller can decide
            // to clear it through definitive handling at the transport layer.
            #if !SKIP && canImport(Security)
            if secure != nil { return nil }
            #endif
            return session.idToken.isEmpty ? nil : session.idToken
        }
        let expiresIn = body["expires_in"]?.numberValue ?? 3600.0
        let userId = body["user_id"]?.stringValue ?? session.uid
        session.idToken = idToken
        session.refreshToken = refreshToken
        session.expiresAtMs = nowMs + Int64(expiresIn * 1000)
        session.uid = userId
        session.firebaseApiKey = apiKey
        #if !SKIP && canImport(Security)
        if let secure, let snapshot {
            // A refresh may update tokens only for the snapshot it started with.
            // A concurrent owner receipt write or logout makes it retry later.
            if let previousUID = snapshot.session?.uid, userId != previousUID { return nil }
            do { try secure.replaceSession(session, expecting: snapshot.revision) }
            catch { return nil }
        } else { await credentials.store(session) }
        #else
        await credentials.store(session)
        #endif
        return idToken
    }

    public func hasCloudSession() async -> Bool {
        await resolveBearerToken() != nil
    }

    // MARK: Custom-token redemption

    /// Redeems a Firebase custom token and stores the refreshable session.
    /// Returns true when signed in. `pinPlane` is applied ONLY after a
    /// successful store.
    @discardableResult
    public func redeemCustomToken(
        _ customToken: String, pinPlane storedPlane: String?
    ) async -> Bool {
        await redeemCustomToken(customToken, pinPlane: storedPlane, attempt: nil)
    }

    private func redeemCustomToken(
        _ customToken: String, pinPlane storedPlane: String?, attempt: Int?
    ) async -> Bool {
        #if !SKIP && canImport(Security)
        let secure = credentials as? SecureSessionCredentialStoring
        let snapshot: SecureSessionSnapshot?
        do { snapshot = try secure?.secureSnapshot() } catch { return false }
        if let attempt {
            guard lock.withLock({
                attempt == signInAttempt && !settled
                    && (snapshot == nil || snapshot?.revision == attemptRevision)
            }) else { return false }
        }
        #endif
        var request = URLRequest(
            url: URL(
                string:
                    "https://identitytoolkit.googleapis.com/v1/accounts:signInWithCustomToken?key=\(config.firebaseApiKey)"
            )!)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "content-type")
        request.httpBody = Data(
            JSON.serialize(
                JSONValue.object([
                    ("token", JSONValue.string(customToken)),
                    ("returnSecureToken", JSONValue.bool(true)),
                ])
            ).utf8
        )
        let redeemed = try? await urlSession.data(for: request)
        let http = redeemed?.1 as? HTTPURLResponse
        guard let data = redeemed?.0, http?.statusCode == 200,
            let body = JSON.parseOrNull(String(data: data, encoding: String.Encoding.utf8)),
            body.isRecord,
            let idToken = body["idToken"]?.stringValue,
            let refreshToken = body["refreshToken"]?.stringValue
        else {
            NSLog("Omi auth firebase redeem status=\(http?.statusCode ?? -1)")
            return false
        }
        let expiresIn = body["expiresIn"]?.numberValue ?? 3600.0
        let stored = StoredSession(
                idToken: idToken, refreshToken: refreshToken,
                expiresAtMs: Int64(Date().timeIntervalSince1970 * 1000)
                    + Int64(expiresIn * 1000),
                uid: body["localId"]?.stringValue,
                firebaseApiKey: config.firebaseApiKey,
                loginGeneration: UUID().uuidString.lowercased())
        #if !SKIP && canImport(Security)
        if let secure, let snapshot {
            do {
                try lock.withLock {
                    if let attempt {
                        guard attempt == signInAttempt && !settled else {
                            throw SecureSessionError.changed
                        }
                    }
                    if let storedPlane, let plane = SoftwarePlane(rawValue: storedPlane) {
                        try planeStore.commitSoftwarePlane(plane) {
                            try secure.replaceSession(stored, expecting: snapshot.revision)
                        }
                    } else {
                        try secure.replaceSession(stored, expecting: snapshot.revision)
                    }
                }
            } catch { return false }
            return true
        }
        #endif
        await credentials.store(stored)
        if let storedPlane, let plane = SoftwarePlane(rawValue: storedPlane) {
            planeStore.storeSoftwarePlane(plane)
        }
        return true
    }

    // MARK: Sign-in flows

    public func signIn() async throws -> Bool {
        let attempt = try lock.withLock { () throws -> Int in
            #if !SKIP && canImport(Security)
            attemptRevision = try (credentials as? SecureSessionCredentialStoring)?
                .secureSnapshot().revision
            #endif
            signInAttempt += 1
            settled = false
            return signInAttempt
        }

        if let origin = config.v5BackendOrigin {
            return try await signInWithDesktopHandoff(origin: origin, attempt: attempt)
        }
        return try await signInWithLegacyPKCE(attempt: attempt)
    }

    public func cancelSignIn() async {
        lock.withLock {
            signInAttempt += 1
            settled = true
        }
    }

    public func signOut() async throws -> Bool {
        await cancelSignIn()
        #if !SKIP && canImport(Security)
        if let secure = credentials as? SecureSessionCredentialStoring {
            defer { invalidationContinuation.yield() }
            try secure.clearSecureSession()
            return true
        }
        #endif
        await credentials.clear()
        invalidationContinuation.yield()
        return true
    }

    func isAttemptCurrent(_ attempt: Int) -> Bool {
        lock.lock()
        defer { lock.unlock() }
        return attempt == signInAttempt && !settled
    }

    /// Desktop handoff: start → poll exchange (1s backoff until expiry) →
    /// redeem the custom token, pinning the plane to "new".
    func signInWithDesktopHandoff(origin: String, attempt: Int) async throws -> Bool {
        guard
            let verifier = AuthCrypto.randomValue(),
            let confirmationCode = AuthCrypto.confirmationCode(),
            let challenge = AuthCrypto.sha256Base64URL(verifier),
            let confirmationChallenge = AuthCrypto.sha256Base64URL(confirmationCode),
            let sessionId = AuthCrypto.deriveDesktopSessionId(
                challenge: challenge, confirmationChallenge: confirmationChallenge)
        else {
            throw AuthError.unconfigured
        }
        var base = origin
        while base.hasSuffix("/") { base = String(base.dropLast()) }
        var start = URLRequest(url: URL(string: "\(base)/v1/auth/desktop/start")!)
        start.httpMethod = "POST"
        start.setValue("application/json", forHTTPHeaderField: "content-type")
        start.httpBody = Data(
            JSON.serialize(
                JSONValue.object([
                    ("sessionId", JSONValue.string(sessionId)),
                    ("challenge", JSONValue.string(challenge)),
                    ("confirmationChallenge", JSONValue.string(confirmationChallenge)),
                ])
            ).utf8
        )
        guard let (data, response) = try? await urlSession.data(for: start),
            let http = response as? HTTPURLResponse, http.statusCode == 201,
            let body = JSON.parseOrNull(String(data: data, encoding: String.Encoding.utf8)),
            body.isRecord,
            let browserUrl = body["browserUrl"]?.stringValue,
            let expiresAt = body["expiresAt"]?.numberValue
        else {
            throw AuthError.transport
        }
        let handoffUrl = browserUrl + "#c=\(confirmationCode)"
        emitHandoff(
            DesktopHandoff(
                code: confirmationCode, expiresAt: Int64(expiresAt),
                browserUrl: handoffUrl))
        while isAttemptCurrent(attempt) {
            let nowMs = Date().timeIntervalSince1970 * 1000
            if nowMs >= expiresAt - 500 {
                throw AuthError.expired
            }
            var exchange = URLRequest(url: URL(string: "\(base)/v1/auth/desktop/exchange")!)
            exchange.httpMethod = "POST"
            exchange.setValue("application/json", forHTTPHeaderField: "content-type")
            exchange.httpBody = Data(
                JSON.serialize(
                    JSONValue.object([
                        ("sessionId", JSONValue.string(sessionId)),
                        ("verifier", JSONValue.string(verifier)),
                    ])
                ).utf8
            )
            let customToken: String?
            if let (data, response) = try? await urlSession.data(for: exchange),
                let http = response as? HTTPURLResponse
            {
                if http.statusCode == 200,
                    let body = JSON.parseOrNull(String(data: data, encoding: String.Encoding.utf8)),
                    body.isRecord
                {
                    customToken = body["customToken"]?.stringValue
                } else if http.statusCode == 409 || http.statusCode == 429
                    || http.statusCode >= 500
                {
                    customToken = nil
                } else {
                    throw AuthError.expired
                }
            } else {
                customToken = nil
            }
            if let customToken, !customToken.isEmpty {
                guard isAttemptCurrent(attempt) else { return false }
                return await redeemCustomToken(customToken, pinPlane: "new", attempt: attempt)
            }
            try await Task.sleep(nanoseconds: 1_000_000_000)
        }
        throw AuthError.cancelled
    }

    /// Legacy loopback OAuth PKCE: the host owns the browser leg; this
    /// exchanges the callback code for a custom token, pinning "old".
    func signInWithLegacyPKCE(attempt: Int) async throws -> Bool {
        guard let browserAuth else { throw AuthError.unconfigured }
        guard
            let verifier = AuthCrypto.randomValue(),
            let state = AuthCrypto.randomValue(),
            let challenge = AuthCrypto.sha256Base64URL(verifier)
        else {
            throw AuthError.unconfigured
        }
        let authorizeURL = legacyAuthorizeURL(
            base: config.legacyAuthorizeURL,
            redirectURI: config.legacyRedirectURI,
            state: state,
            codeChallenge: challenge
        )
        guard let authorizeURL else {
            throw AuthError.unconfigured
        }
        guard
            let callback = await browserAuth.presentAuthorizeURL(
                authorizeURL, state: state)
        else {
            throw AuthError.unauthorized("Omi cloud sign in was cancelled or failed")
        }
        guard isAttemptCurrent(attempt) else { return false }
        // Validate the callback shape (loopback on macOS, app scheme on iOS).
        guard
            let code = authCallbackCode(
                callback, redirectURI: config.legacyRedirectURI, expectedState: state)
        else {
            throw AuthError.unauthorized("Omi cloud sign in was cancelled or failed")
        }
        guard isAttemptCurrent(attempt) else { return false }
        var body = "grant_type=authorization_code&code=\(encodeQueryComponent(code))"
        body += "&redirect_uri=\(encodeQueryComponent(config.legacyRedirectURI))"
        body += "&use_custom_token=true&code_verifier=\(encodeQueryComponent(verifier))"
        var exchange = URLRequest(url: URL(string: "https://api.omi.me/v1/auth/token")!)
        exchange.httpMethod = "POST"
        exchange.setValue(
            "application/x-www-form-urlencoded", forHTTPHeaderField: "content-type")
        exchange.httpBody = Data(body.utf8)
        let exchanged: (Data, URLResponse)
        do {
            exchanged = try await urlSession.data(for: exchange)
        } catch {
            throw AuthError.transport
        }
        guard let http = exchanged.1 as? HTTPURLResponse else {
            throw AuthError.transport
        }
        guard http.statusCode == 200,
            let payload = JSON.parseOrNull(
                String(data: exchanged.0, encoding: String.Encoding.utf8)),
            payload.isRecord
        else {
            NSLog("Omi auth token exchange status=\(http.statusCode)")
            throw AuthError.unauthorized("Omi cloud token exchange failed")
        }
        // Only a custom_token mints a refreshable Omi session.
        let customToken =
            payload["custom_token"]?.stringValue ?? payload["customToken"]?.stringValue
        guard let customToken, !customToken.isEmpty else {
            throw AuthError.unauthorized("Omi cloud did not return a usable session")
        }
        guard isAttemptCurrent(attempt) else { return false }
        return await redeemCustomToken(customToken, pinPlane: "old", attempt: attempt)
    }
}
