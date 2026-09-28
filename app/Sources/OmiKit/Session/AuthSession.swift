import Foundation
#if !SKIP
#if canImport(Crypto)
import Crypto
#else
import CommonCrypto
#endif
#endif

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

/// Host-supplied browser leg for the legacy loopback OAuth flow.
public protocol BrowserAuthControlling: Sendable {
    /// Presents the authorize URL and resolves with the loopback callback
    /// URL, or nil when the user cancelled.
    func presentAuthorizeURL(_ url: String, state: String) async -> String?
}

public struct AuthSessionConfig: Sendable {
    public var firebaseApiKey: String
    /// The stamped, validated v5 origin, when the New plane is stamped.
    public var v5BackendOrigin: String?
    public var legacyAuthorizeURL: String
    public var legacyRedirectURI: String

    public init(
        firebaseApiKey: String, v5BackendOrigin: String? = nil,
        legacyAuthorizeURL: String = "https://api.omi.me/v1/auth/google",
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
        #if !SKIP
        let digest = sha256(Array(value.utf8))
        return Base64Codec.encodeURL(digest)
        #else
        return nil
        #endif
    }

    #if !SKIP
    static func sha256(_ bytes: [UInt8]) -> [UInt8] {
        #if canImport(Crypto)
        let digest = SHA256.hash(data: Data(bytes))
        return digest.map { $0 }
        #else
        var digest = [UInt8](repeating: 0, count: Int(CC_SHA256_DIGEST_LENGTH))
        bytes.withUnsafeBufferPointer { buffer in
            _ = CC_SHA256(buffer.baseAddress, CC_LONG(bytes.count), &digest)
        }
        return digest
        #endif
    }
    #endif

    /// `sha256url(challenge + "\0" + confirmationChallenge)` — mirrors the
    /// Worker's `deriveSessionId`.
    public static func deriveDesktopSessionId(
        challenge: String, confirmationChallenge: String
    ) -> String? {
        sha256Base64URL("\(challenge)\u{0}\(confirmationChallenge)")
    }

    /// Six decimal digits, rejection-sampled over 000000-999999.
    public static func confirmationCode() -> String? {
        for _ in 0..<16 {
            let raw = UInt32.random(in: 0...UInt32.max)
            if raw < 4_294_000_000 {
                return String(format: "%06d", raw % 1_000_000)
            }
        }
        return nil
    }

    public static func randomValue() -> String? {
        var bytes = [UInt8](repeating: 0, count: 32)
        for index in bytes.indices {
            bytes[index] = UInt8.random(in: 0...255)
        }
        return Base64Codec.encodeURL(bytes)
    }
}

public final class OmiAuthSession: Authenticating, SessionProbeCapable, @unchecked Sendable {
    private let config: AuthSessionConfig
    private let credentials: CredentialStoring
    private let browserAuth: BrowserAuthControlling?
    private let handoffs: InvalidationStream<DesktopHandoff>
    private let invalidations: InvalidationStream<Void>
    private let lock = NSLock()
    private var signInAttempt: Int = 0
    private var settled = true

    public init(
        config: AuthSessionConfig, credentials: CredentialStoring,
        browserAuth: BrowserAuthControlling? = nil
    ) {
        self.config = config
        self.credentials = credentials
        self.browserAuth = browserAuth
        self.handoffs = InvalidationStream()
        self.invalidations = InvalidationStream()
    }

    public var desktopHandoffs: AsyncStream<DesktopHandoff> { handoffs.stream }
    public var sessionInvalidated: AsyncStream<Void> { invalidations.stream }

    // MARK: Session refresh (Firebase REST)

    /// Returns a fresh Bearer id token, or nil when no session is stored.
    /// A definitive refresh failure clears the stored session.
    public func resolveBearerToken() async -> String? {
        guard var session = await credentials.load() else { return nil }
        let nowMs = Int64(Date().timeIntervalSince1970 * 1000)
        if session.expiresAtMs > nowMs + 60_000, !session.idToken.isEmpty {
            return session.idToken
        }
        guard !session.refreshToken.isEmpty else {
            await credentials.clear()
            invalidations.yield(())
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
        guard let (data, response) = try? await URLSession.shared.data(for: request),
            let http = response as? HTTPURLResponse, http.statusCode == 200,
            let body = JSON.parseOrNull(String(data: data, encoding: String.Encoding.utf8)),
            body.isRecord,
            let idToken = body["id_token"]?.stringValue,
            let refreshToken = body["refresh_token"]?.stringValue
        else {
            // Transient failures keep the session; only the caller can decide
            // to clear it through definitive handling at the transport layer.
            return session.idToken.isEmpty ? nil : session.idToken
        }
        let expiresIn = body["expires_in"]?.numberValue ?? 3600
        let userId = body["user_id"]?.stringValue ?? session.uid
        session.idToken = idToken
        session.refreshToken = refreshToken
        session.expiresAtMs = nowMs + Int64(expiresIn * 1000)
        session.uid = userId
        session.firebaseApiKey = apiKey
        await credentials.store(session)
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
        guard let (data, response) = try? await URLSession.shared.data(for: request),
            let http = response as? HTTPURLResponse, http.statusCode == 200,
            let body = JSON.parseOrNull(String(data: data, encoding: String.Encoding.utf8)),
            body.isRecord,
            let idToken = body["idToken"]?.stringValue,
            let refreshToken = body["refreshToken"]?.stringValue
        else {
            return false
        }
        let expiresIn = body["expiresIn"]?.numberValue ?? 3600
        await credentials.store(
            StoredSession(
                idToken: idToken, refreshToken: refreshToken,
                expiresAtMs: Int64(Date().timeIntervalSince1970 * 1000)
                    + Int64(expiresIn * 1000),
                uid: body["localId"]?.stringValue,
                firebaseApiKey: config.firebaseApiKey))
        if let storedPlane {
            UserDefaults.standard.set(storedPlane, forKey: SOFTWARE_PLANE_DEFAULTS_KEY)
        }
        return true
    }

    // MARK: Sign-in flows

    public func signIn() async throws -> Bool {
        let attempt = lock.withLock { () -> Int in
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
        await credentials.clear()
        invalidations.yield(())
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
        while base.hasSuffix("/") { base.removeLast() }
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
        guard let (data, response) = try? await URLSession.shared.data(for: start),
            let http = response as? HTTPURLResponse, http.statusCode == 201,
            let body = JSON.parseOrNull(String(data: data, encoding: String.Encoding.utf8)),
            body.isRecord,
            let browserUrl = body["browserUrl"]?.stringValue,
            let expiresAt = body["expiresAt"]?.numberValue
        else {
            throw AuthError.transport
        }
        let handoffUrl = browserUrl + "#c=\(confirmationCode)"
        handoffs.yield(
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
            if let (data, response) = try? await URLSession.shared.data(for: exchange),
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
                return await redeemCustomToken(customToken, pinPlane: "new")
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
        let authorizeURL =
            "\(config.legacyAuthorizeURL)?client_id=omi&redirect_uri=\(encodeQueryComponent(config.legacyRedirectURI))&response_type=code&state=\(encodeQueryComponent(state))&code_challenge=\(encodeQueryComponent(challenge))&code_challenge_method=S256"
        guard let callback = await browserAuth.presentAuthorizeURL(
            authorizeURL, state: state)
        else {
            throw AuthError.unauthorized("Omi cloud sign in was cancelled or failed")
        }
        guard isAttemptCurrent(attempt) else { return false }
        // Validate the loopback callback shape.
        guard let components = URLComponents(string: callback),
            components.scheme?.lowercased() == "http",
            components.host?.lowercased() == "127.0.0.1",
            components.path == "/callback", components.fragment == nil
        else {
            throw AuthError.unauthorized("Omi cloud sign in was cancelled or failed")
        }
        let values = Dictionary(
            uniqueKeysWithValues: (components.queryItems ?? []).compactMap { item in
                item.value.map { (item.name, $0) }
            })
        guard values["state"] == state, let code = values["code"], !code.isEmpty else {
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
        guard let (data, response) = try? await URLSession.shared.data(for: exchange),
            let http = response as? HTTPURLResponse, http.statusCode == 200,
            let payload = JSON.parseOrNull(String(data: data, encoding: String.Encoding.utf8)),
            payload.isRecord
        else {
            throw AuthError.unauthorized("Omi cloud token exchange failed")
        }
        // Only a custom_token mints a refreshable Omi session.
        let customToken =
            payload["custom_token"]?.stringValue ?? payload["customToken"]?.stringValue
        guard let customToken, !customToken.isEmpty else {
            throw AuthError.unauthorized("Omi cloud did not return a usable session")
        }
        guard isAttemptCurrent(attempt) else { return false }
        return await redeemCustomToken(customToken, pinPlane: "old")
    }
}

/// Small continuation holder shared by the auth session streams.
final class InvalidationStream<Value: Sendable>: @unchecked Sendable {
    let continuation: AsyncStream<Value>.Continuation
    let stream: AsyncStream<Value>

    init() {
        var captured: AsyncStream<Value>.Continuation!
        self.stream = AsyncStream { continuation in
            captured = continuation
        }
        self.continuation = captured
    }

    func yield(_ value: Value) {
        continuation.yield(value)
    }
}
