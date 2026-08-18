import AppKit
import CryptoKit
import Foundation
import Security

enum OmiAuthProvider: String, Sendable {
    case google
    case apple
}

enum OmiAuthError: LocalizedError {
    case missingAPIKey
    case cancelled
    case stateMismatch
    /// Airgap Mode is on, so no sign-in or token refresh was attempted.
    ///
    /// Surfaced rather than swallowed on purpose. Both sign-in surfaces already render whatever this
    /// throws — the menu bar through `OmiAuth.lastSignInError`, onboarding through its own `catch` —
    /// so a person who presses "Continue with Google" under Airgap Mode is told which switch stopped
    /// it and where to turn it off, instead of watching a button do nothing.
    case airgapMode
    case badResponse(String)
    case http(Int, String)

    var errorDescription: String? {
        switch self {
        case .missingAPIKey:
            return "This build of Context for Claude has no Firebase API key, so it cannot finish signing in."
        case .cancelled:
            return "Sign-in didn't finish."
        case .airgapMode:
            return NetworkEgress.explanation(.signIn)
        case .stateMismatch:
            return "That sign-in response didn't match this request, so Context for Claude ignored it. Try again."
        case .badResponse(let detail):
            return detail
        case .http(let status, let detail):
            return "\(detail) (HTTP \(status))"
        }
    }
}

/// Signs Context for Claude in to the user's real Omi account and keeps a Firebase ID token available.
///
/// No Firebase SDK. Context for Claude is a small menu-bar app and the SDK would drag in a method-swizzling
/// app-delegate, its own keychain item, and a background token-refresh thread we cannot see into.
/// Everything below is the same three HTTP calls the SDK would make:
///
/// 1. `api.omi.me/v1/auth/authorize` in the user's browser (loopback redirect + PKCE)
/// 2. `api.omi.me/v1/auth/token` — the authorization code for a Firebase **custom** token
/// 3. `identitytoolkit.googleapis.com/…:signInWithCustomToken` — the custom token for a real
///    `{idToken, refreshToken}` pair, refreshed thereafter via `securetoken.googleapis.com`
///
/// Nothing here logs a token, a code, or a verifier. The only identifier that reaches the log is the
/// Firebase uid, which is opaque and is what makes a support report actionable.
@MainActor
final class OmiAuth: ObservableObject {
    static let shared = OmiAuth()

    @Published private(set) var userId: String?
    @Published private(set) var email: String?
    @Published private(set) var isSignedIn = false
    @Published private(set) var isSigningIn = false

    /// Why the last sign-in did not finish, or `nil` if none has failed since one was last started.
    ///
    /// Published rather than returned, because the surface that starts a sign-in is usually gone
    /// before it ends: the menu bar popover is `.transient` and macOS tears it down the moment the
    /// browser takes focus, so an error held in a view's `@State` is an error nobody is ever shown.
    /// Living here, it is still on screen the next time the popover opens.
    @Published private(set) var lastSignInError: String?

    private var session: OmiSession?
    private var refreshFlight: RefreshFlight?

    private struct RefreshFlight {
        let id: UUID
        let task: Task<String, Error>
    }

    /// Treat a token as dead five minutes early: a request that starts inside the window must not
    /// arrive at the backend after the token turns invalid.
    private static let expiryBuffer: TimeInterval = 300
    private static let apiBaseURL = "https://api.omi.me/"

    private let urlSession: URLSession = {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.timeoutIntervalForRequest = 30
        configuration.timeoutIntervalForResource = 60
        return URLSession(configuration: configuration)
    }()

    private init() {}

    // MARK: - Session lifecycle

    /// Loads whatever the last launch stored. An expired ID token is still a signed-in state — the
    /// refresh token is the credential that matters, and it is spent lazily on the first call.
    /// Loads any stored session, reading the Keychain **off the main actor**.
    ///
    /// `SecItemCopyMatching` is not a fast local read. When the app's code signature changes — every
    /// rebuild during development, every update in the field — the Keychain ACL no longer matches
    /// and macOS puts an authorization prompt in front of it. An `LSUIElement` app has no window to
    /// show that prompt in, so the call simply does not return: once measured at 22 minutes. Doing
    /// it on the main actor took the whole app down with it, and everything sequenced behind this
    /// call inherited the wait.
    func restore() {
        Task { [weak self] in
            let stored = await Task.detached(priority: .userInitiated) { SessionStore.load() }.value
            await MainActor.run { self?.adoptRestored(stored) }
        }
    }

    private func adoptRestored(_ stored: OmiSession?) {
        guard let stored else {
            ContextLog.info("No stored Omi session", "auth")
            return
        }
        adopt(stored, email: Self.claim("email", in: stored.idToken))
        ContextLog.info(
            "Restored Omi session (id token \(stored.isExpired ? "expired, refreshing on first use" : "valid"))",
            "auth"
        )
    }

    /// Starts a sign-in **that outlives the view which asked for it**, and records the outcome here.
    ///
    /// The same round trip as `signIn(provider:)` — this is not a second sign-in path, it owns the
    /// task rather than the credentials — and it exists for one reason: a caller that cannot await.
    /// The menu bar popover is an `NSPopover` with `.transient` behaviour, so opening the browser
    /// closes it and destroys its view; a `Task` a *view* owns would be a sign-in cancelled halfway
    /// through by the user looking at their browser. This type is a singleton for the life of the
    /// app, so a task started here simply finishes.
    ///
    /// Onboarding keeps the `async` form: it has a card on screen for the whole round trip and a
    /// step to advance to afterwards, which is a decision only that caller can make.
    func beginSignIn(provider: OmiAuthProvider) {
        guard !isSigningIn else {
            ContextLog.info("Sign-in already in progress; ignoring duplicate request", "auth")
            return
        }
        Task { [weak self] in
            guard let self else { return }
            do {
                try await self.signIn(provider: provider)
            } catch {
                // `signIn` already logged the cause; this is the sentence the user is shown.
                self.lastSignInError = error.localizedDescription
            }
        }
    }

    /// Signs in, unless Airgap Mode says otherwise.
    ///
    /// **Airgap Mode blocks sign-in outright, and that is the deliberate choice.** Signing in is
    /// three requests to two hosts — `api.omi.me` twice and Google's identity toolkit once — and it
    /// ships an authorization code for the user's account to both. Permitting "just sign-in" would
    /// hand the network the one credential that matters while claiming the app is airgapped, and it
    /// would buy the user nothing: every account feature behind that session (screen sync,
    /// conversation upload, cloud transcription, MCP key provisioning) is suppressed too, so the
    /// result would be a live session that can do nothing. Meanwhile everything this app is actually
    /// for — capture, OCR, local transcription, local search, the local MCP tools — works signed out.
    ///
    /// The user is told, not stonewalled: this throws before the browser opens, and both sign-in
    /// surfaces already render the thrown sentence.
    func signIn(provider: OmiAuthProvider) async throws {
        guard !isSigningIn else {
            ContextLog.info("Sign-in already in progress; ignoring duplicate request", "auth")
            throw OmiAuthError.cancelled
        }

        // Before `isSigningIn` is set and before a browser opens. Opening a tab and then refusing the
        // code it comes back with would be a worse lie than refusing the press.
        //
        // This is the *first* of the guards on this flow and never the last one. Nothing between
        // here and `NSWorkspace.shared.open` below suspends, so the browser cannot be opened against
        // a stale answer — but `waitForCode()` below suspends for as long as a person takes, and the
        // two requests after it re-ask for themselves in `post(url:contentType:body:client:)`.
        guard !NetworkEgress.isSuppressed(.signIn) else {
            ContextLog.info("Sign-in refused: Airgap Mode is on", "auth")
            NetworkEgress.recordSuppression(.signIn, outcome: .bypassed)
            lastSignInError = NetworkEgress.explanation(.signIn)
            throw OmiAuthError.airgapMode
        }

        isSigningIn = true
        // A new attempt clears the last one's verdict: a stale error under a live "waiting for your
        // browser…" line is the app contradicting itself.
        lastSignInError = nil
        defer { isSigningIn = false }

        // Resolve the key before a browser opens. Discovering a misconfigured build *after* the user
        // has typed their Google password is the worst possible moment for it.
        let apiKey = try Self.firebaseAPIKey()

        let state = Self.randomURLSafeToken(byteCount: 32)
        let verifier = Self.makeCodeVerifier()
        let challenge = Self.makeCodeChallenge(for: verifier)

        let server: LoopbackCallbackServer
        do {
            server = try LoopbackCallbackServer.start(expectedState: state)
        } catch {
            throw OmiAuthError.badResponse("Context for Claude couldn't open a local port to receive the sign-in response.")
        }
        // Belt and braces: the success path stops the listener early, this catches every throw above it.
        defer { server.stop() }

        guard
            let authorizeURL = Self.authorizeURL(
                provider: provider,
                redirectURI: server.redirectURI,
                state: state,
                codeChallenge: challenge
            )
        else {
            throw OmiAuthError.badResponse("Context for Claude couldn't build the sign-in URL.")
        }

        ContextLog.info("Opening \(provider.rawValue) sign-in; awaiting callback on 127.0.0.1:\(server.port)", "auth")
        NSWorkspace.shared.open(authorizeURL)

        let code: String
        do {
            code = try await server.waitForCode()
        } catch {
            throw Self.authError(from: error)
        }
        server.stop()

        let exchange = try await exchangeAuthorizationCode(
            code, verifier: verifier, redirectURI: server.redirectURI)
        let tokens = try await signInWithCustomToken(exchange.customToken, apiKey: apiKey)

        let stored = OmiSession(
            idToken: tokens.idToken,
            refreshToken: tokens.refreshToken,
            expiryTime: Date().timeIntervalSince1970 + Double(tokens.expiresIn) - Self.expiryBuffer,
            tokenUserId: tokens.localId
        )
        guard SessionStore.save(stored) else {
            throw OmiAuthError.badResponse(
                "Signed in, but Context for Claude couldn't store the session in your Keychain. Try again.")
        }
        adopt(stored, email: exchange.email ?? Self.claim("email", in: tokens.idToken))
        ContextLog.info("Signed in via \(provider.rawValue)", "auth")
        Task { await MCPKeyProvisioner.shared.ensureKey() }
    }

    func signOut() {
        refreshFlight?.task.cancel()
        refreshFlight = nil
        session = nil
        userId = nil
        email = nil
        isSignedIn = false
        ContextAnalytics.record(.accountStateChanged(signedIn: false))
        // Signing out is a clean slate, and the popover offers a Sign in link the instant this
        // lands — under which a previous attempt's failure would read as this one's.
        lastSignInError = nil
        SessionStore.clear()
        MCPKeyProvisioner.shared.removeKey()
        ContextLog.info("Signed out", "auth")
    }

    // MARK: - Tokens

    func idToken(forceRefresh: Bool = false) async throws -> String {
        guard let session else {
            throw OmiAuthError.badResponse("Not signed in to Omi.")
        }
        if !forceRefresh, !session.isExpired {
            return session.idToken
        }
        return try await refreshedIDToken()
    }

    func authHeader(forceRefresh: Bool = false) async throws -> String {
        "Bearer \(try await idToken(forceRefresh: forceRefresh))"
    }

    /// One refresh at a time, shared by everyone who asks while it runs.
    ///
    /// Firebase **rotates** the refresh token on every successful exchange, so two concurrent
    /// refreshes are not merely wasteful: the slower one persists a credential the faster one has
    /// already superseded, and the next launch signs in with a dead token. Because this type is
    /// `@MainActor`, a caller that arrives while a refresh is in flight cannot miss it — it runs to
    /// its first `await` without interleaving, sees the stored flight, and joins it.
    private func refreshedIDToken() async throws -> String {
        if let inFlight = refreshFlight {
            return try await inFlight.task.value
        }
        guard let refreshToken = session?.refreshToken else {
            throw OmiAuthError.badResponse("Not signed in to Omi.")
        }

        let id = UUID()
        let task = Task { [weak self] () throws -> String in
            guard let self else { throw OmiAuthError.cancelled }
            return try await self.performRefresh(refreshToken: refreshToken)
        }
        refreshFlight = RefreshFlight(id: id, task: task)
        defer {
            // Only clear our own flight: `signOut()` may have replaced or dropped it meanwhile.
            if refreshFlight?.id == id { refreshFlight = nil }
        }
        return try await task.value
    }

    private func performRefresh(refreshToken: String) async throws -> String {
        // Throwing here leaves the stored session **completely untouched**, which is the whole point:
        // an airgapped Mac must not be signed out for the crime of not being allowed to refresh. The
        // refresh token is long-lived, so turning Airgap Mode off resumes the same account with no
        // browser round trip. Nothing below this line runs, so the token never leaves the Keychain.
        guard !NetworkEgress.isSuppressed(.tokenRefresh) else {
            ContextLog.info("Token refresh skipped: Airgap Mode is on", "auth")
            NetworkEgress.recordSuppression(.tokenRefresh, outcome: .degraded)
            throw OmiAuthError.airgapMode
        }

        let apiKey = try Self.firebaseAPIKey()
        guard let url = URL(string: "https://securetoken.googleapis.com/v1/token?key=\(apiKey)") else {
            throw OmiAuthError.badResponse("Context for Claude couldn't build the token refresh URL.")
        }

        // A thrown `URLError` (offline, DNS, timeout, captive portal) leaves the stored session
        // untouched by construction: nothing below this line runs.
        let (data, response) = try await post(
            url: url,
            contentType: "application/x-www-form-urlencoded",
            body: Data(
                Self.formEncoded([
                    ("grant_type", "refresh_token"),
                    ("refresh_token", refreshToken),
                ]).utf8),
            client: .tokenRefresh
        )

        guard response.statusCode == 200 else {
            let summary = Self.errorSummary(data)
            if Self.isDefinitiveRefreshFailure(status: response.statusCode, body: data) {
                ContextLog.error(
                    "Refresh credential is dead (HTTP \(response.statusCode) \(summary)); signing out", "auth")
                signOut()
                throw OmiAuthError.http(response.statusCode, "Your Omi session expired. Sign in again.")
            }
            // Everything else — 5xx, 429, a proxy's HTML, an unfamiliar 400 — is treated as
            // survivable and the session is kept. Signing someone out because their wifi dropped
            // costs them a browser round-trip and their trust; retrying a refresh costs nothing.
            ContextLog.error(
                "Token refresh failed transiently (HTTP \(response.statusCode) \(summary)); keeping session", "auth")
            throw OmiAuthError.http(response.statusCode, "Context for Claude couldn't refresh your Omi session.")
        }

        guard let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
            let idToken = json["id_token"] as? String,
            let newRefreshToken = json["refresh_token"] as? String
        else {
            throw OmiAuthError.badResponse("Context for Claude couldn't read the refreshed Omi session.")
        }

        let expiresIn = Self.seconds(json["expires_in"])
        let ownerId = (json["user_id"] as? String)
            ?? session?.tokenUserId
            ?? Self.claim("user_id", in: idToken)
            ?? Self.claim("sub", in: idToken)
            ?? ""

        let refreshed = OmiSession(
            idToken: idToken,
            refreshToken: newRefreshToken,
            expiryTime: Date().timeIntervalSince1970 + Double(expiresIn) - Self.expiryBuffer,
            tokenUserId: ownerId
        )
        guard !Task.isCancelled, let session = self.session, session.refreshToken == refreshToken, self.isSignedIn else {
            throw OmiAuthError.cancelled
        }
        if !SessionStore.save(refreshed) {
            // The Keychain being briefly unavailable is not a reason to drop a valid session; keep
            // it for this launch and let the next successful refresh persist it.
            ContextLog.error("Refreshed session couldn't be stored; keeping it in memory for this launch", "auth")
        }
        adopt(refreshed, email: email)
        ContextLog.info("Refreshed Omi session", "auth")
        return idToken
    }

    /// Only these mean the refresh credential itself is gone. Anything else, including a 400 whose
    /// body we cannot parse, stays recoverable.
    private static let definitiveRefreshCodes = [
        "TOKEN_EXPIRED",
        "USER_DISABLED",
        "USER_NOT_FOUND",
        "INVALID_REFRESH_TOKEN",
    ]

    static func isDefinitiveRefreshFailure(status: Int, body: Data) -> Bool {
        guard status == 400 else { return false }
        let codes = firebaseErrorCodes(in: body)
        if !codes.isEmpty {
            return codes.contains { code in definitiveRefreshCodes.contains { code.contains($0) } }
        }
        // No JSON envelope (a proxy rewrote it): fall back to scanning the text for the same codes.
        guard let text = String(data: body, encoding: .utf8) else { return false }
        return definitiveRefreshCodes.contains { text.contains($0) }
    }

    private static func firebaseErrorCodes(in body: Data) -> [String] {
        guard let json = try? JSONSerialization.jsonObject(with: body) as? [String: Any],
            let error = json["error"] as? [String: Any]
        else {
            return []
        }
        var codes: [String] = []
        if let message = error["message"] as? String, !message.isEmpty { codes.append(message) }
        if let status = error["status"] as? String, !status.isEmpty { codes.append(status) }
        for detail in error["details"] as? [[String: Any]] ?? [] {
            if let reason = detail["reason"] as? String, !reason.isEmpty { codes.append(reason) }
        }
        return codes
    }

    // MARK: - The three calls

    private struct CodeExchange {
        let customToken: String
        let email: String?
    }

    private func exchangeAuthorizationCode(
        _ code: String, verifier: String, redirectURI: String
    ) async throws -> CodeExchange {
        guard let url = URL(string: Self.apiBaseURL + "v1/auth/token") else {
            throw OmiAuthError.badResponse("Context for Claude couldn't build the token exchange URL.")
        }
        let body = Self.formEncoded([
            ("grant_type", "authorization_code"),
            ("code", code),
            ("redirect_uri", redirectURI),
            // Ask Omi for a Firebase custom token rather than its own session: that is what lets
            // Context for Claude mint a real Firebase ID token without linking the SDK.
            ("use_custom_token", "true"),
            ("code_verifier", verifier),
        ])

        let (data, response) = try await post(
            url: url, contentType: "application/x-www-form-urlencoded", body: Data(body.utf8),
            client: .signIn)
        guard response.statusCode == 200 else {
            throw OmiAuthError.http(
                response.statusCode, "Omi rejected the sign-in \(Self.errorSummary(data)).")
        }
        guard let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
            let customToken = json["custom_token"] as? String
        else {
            throw OmiAuthError.badResponse("Omi's sign-in response didn't contain a token.")
        }
        // The provider's own id_token rides along and is the only place the email appears.
        let email = (json["id_token"] as? String).flatMap { Self.claim("email", in: $0) }
        return CodeExchange(customToken: customToken, email: email)
    }

    private struct FirebaseTokens {
        let idToken: String
        let refreshToken: String
        let expiresIn: Int
        let localId: String
    }

    private func signInWithCustomToken(_ customToken: String, apiKey: String) async throws -> FirebaseTokens {
        guard
            let url = URL(
                string: "https://identitytoolkit.googleapis.com/v1/accounts:signInWithCustomToken?key=\(apiKey)")
        else {
            throw OmiAuthError.badResponse("Context for Claude couldn't build the Firebase sign-in URL.")
        }
        let body = try JSONSerialization.data(withJSONObject: [
            "token": customToken,
            "returnSecureToken": true,
        ])

        let (data, response) = try await post(
            url: url, contentType: "application/json", body: body, client: .signIn)
        guard response.statusCode == 200 else {
            throw OmiAuthError.http(
                response.statusCode, "Firebase rejected Omi's sign-in \(Self.errorSummary(data)).")
        }
        guard let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
            let idToken = json["idToken"] as? String,
            let refreshToken = json["refreshToken"] as? String
        else {
            throw OmiAuthError.badResponse("Firebase's sign-in response was missing a token.")
        }

        let localId = (json["localId"] as? String).flatMap { $0.isEmpty ? nil : $0 }
            ?? Self.claim("user_id", in: idToken)
            ?? Self.claim("sub", in: idToken)
        guard let localId, !localId.isEmpty else {
            throw OmiAuthError.badResponse("Firebase's sign-in response had no user id.")
        }

        return FirebaseTokens(
            idToken: idToken,
            refreshToken: refreshToken,
            expiresIn: Self.seconds(json["expiresIn"]),
            localId: localId
        )
    }

    private func post(
        url: URL, contentType: String, body: Data, client: NetworkEgress.Client
    ) async throws -> (Data, HTTPURLResponse) {
        try await Self.post(
            url: url, contentType: contentType, body: body, client: client,
            transport: { [urlSession] request in try await urlSession.data(for: request) })
    }

    /// The one function in this type that touches the network, and therefore the one place Airgap
    /// Mode can honestly be read.
    ///
    /// **The re-read here is the fix, not decoration.** Sign-in used to be guarded once, at the
    /// press, and then waited on `LoopbackCallbackServer.waitForCode()` — an unbounded wait, because
    /// what it is waiting for is a person in a browser. Everything after that wait ran on an answer
    /// taken minutes earlier: someone who reached for Airgap Mode *while* their browser was open —
    /// the exact moment a person reaches for it — still shipped an authorization code to
    /// `api.omi.me` and a custom token to Google. A flow-level guard cannot see a switch that moves
    /// mid-flow; a request-level one cannot miss it.
    ///
    /// Static, and with both the gate and the transport injected, so the refusal is drivable in a
    /// test without a browser, a loopback socket, or a request to anybody's real account.
    static func post(
        url: URL,
        contentType: String,
        body: Data,
        client: NetworkEgress.Client,
        isSuppressed: (NetworkEgress.Client) -> Bool = { NetworkEgress.isSuppressed($0) },
        transport: (URLRequest) async throws -> (Data, URLResponse)
    ) async throws -> (Data, HTTPURLResponse) {
        // Before the `URLRequest` exists, so no body carrying a code, a verifier or a refresh token
        // is ever assembled — let alone sent.
        guard !isSuppressed(client) else {
            ContextLog.info("\(client.rawValue) request suppressed: Airgap Mode is on", "auth")
            // `.bypassed` for a sign-in: the whole attempt is abandoned and the user is told.
            // `.degraded` for a refresh: the stored session is untouched and resumes, with no
            // browser round trip, the moment the switch goes off.
            NetworkEgress.recordSuppression(client, outcome: client == .signIn ? .bypassed : .degraded)
            throw OmiAuthError.airgapMode
        }

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue(contentType, forHTTPHeaderField: "Content-Type")
        request.httpBody = body

        let (data, response) = try await transport(request)
        guard let http = response as? HTTPURLResponse else {
            throw OmiAuthError.badResponse("The server sent a response Context for Claude couldn't read.")
        }
        return (data, http)
    }

    // MARK: - Configuration

    /// The Firebase **Web API key** — a public client identifier for the `based-hardware` project,
    /// not a secret; it identifies which project a REST call addresses and every Firebase web app
    /// ships it in plain JavaScript. It is still resolved at runtime rather than typed into source:
    ///
    /// 1. `FIREBASE_API_KEY` in the environment is honored only in DEBUG builds, so a developer can
    ///    run against a different project (or the emulator) without editing or rebuilding anything.
    /// 2. `OmiFirebaseAPIKey` in `Info.plist`, which `scripts/build.sh` injects for shipped builds.
    ///
    /// Hardcoding it would make the fallback invisible and would put a project identifier into git
    /// where rotating it means a source change.
    private static func firebaseAPIKey() throws -> String {
        #if DEBUG
        if let fromEnvironment = ProcessInfo.processInfo.environment["FIREBASE_API_KEY"],
            !fromEnvironment.isEmpty
        {
            return fromEnvironment
        }
        #endif
        if let fromBundle = Bundle.main.object(forInfoDictionaryKey: "OmiFirebaseAPIKey") as? String,
            !fromBundle.isEmpty
        {
            return fromBundle
        }
        ContextLog.error("No Firebase API key in Info.plist", "auth")
        throw OmiAuthError.missingAPIKey
    }

    private static func authorizeURL(
        provider: OmiAuthProvider, redirectURI: String, state: String, codeChallenge: String
    ) -> URL? {
        var components = URLComponents(string: apiBaseURL + "v1/auth/authorize")
        components?.queryItems = [
            URLQueryItem(name: "provider", value: provider.rawValue),
            URLQueryItem(name: "redirect_uri", value: redirectURI),
            URLQueryItem(name: "state", value: state),
            URLQueryItem(name: "code_challenge", value: codeChallenge),
            URLQueryItem(name: "code_challenge_method", value: "S256"),
        ]
        return components?.url
    }

    // MARK: - PKCE

    /// 64 characters of the unreserved set. The modulo is very slightly biased across a 66-symbol
    /// alphabet, which is irrelevant next to the ~380 bits of entropy that remain.
    private static func makeCodeVerifier(length: Int = 64) -> String {
        let charset = Array("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~")
        return String(randomBytes(length).map { charset[Int($0) % charset.count] })
    }

    private static func makeCodeChallenge(for verifier: String) -> String {
        base64URL(Data(SHA256.hash(data: Data(verifier.utf8))))
    }

    private static func randomURLSafeToken(byteCount: Int) -> String {
        base64URL(Data(randomBytes(byteCount)))
    }

    private static func randomBytes(_ count: Int) -> [UInt8] {
        var bytes = [UInt8](repeating: 0, count: count)
        guard SecRandomCopyBytes(kSecRandomDefault, count, &bytes) == errSecSuccess else {
            // Never degrade to something guessable: `SystemRandomNumberGenerator` is also a CSPRNG.
            ContextLog.error("SecRandomCopyBytes failed; falling back to the system generator", "auth")
            return (0..<count).map { _ in UInt8.random(in: UInt8.min...UInt8.max) }
        }
        return bytes
    }

    private static func base64URL(_ data: Data) -> String {
        data.base64EncodedString()
            .replacingOccurrences(of: "+", with: "-")
            .replacingOccurrences(of: "/", with: "_")
            .replacingOccurrences(of: "=", with: "")
    }

    // MARK: - Small helpers

    /// `email` is authoritative, not a merge: signing in as a second account must not leave the
    /// first account's address on screen. A refresh, which carries no email, passes the current one.
    private func adopt(_ session: OmiSession, email: String?) {
        self.session = session
        userId = session.tokenUserId.isEmpty ? nil : session.tokenUserId
        self.email = email
        isSignedIn = true
        // Whether, never who. `AnalyticsIdentity` stays a salted hash of the install id after
        // sign-in — see `ContextAnalytics` — so this reports that an account exists without making
        // the anonymous series joinable to it.
        ContextAnalytics.record(.accountStateChanged(signedIn: true))
    }

    private static func authError(from error: Error) -> OmiAuthError {
        guard let serverError = error as? LoopbackCallbackServer.ServerError else {
            return .badResponse(error.localizedDescription)
        }
        switch serverError {
        case .stateMismatch:
            ContextLog.error("Callback state did not match; refusing to exchange the code", "auth")
            return .stateMismatch
        case .provider(let reason):
            return .badResponse("The sign-in provider returned an error: \(reason)")
        case .timedOut:
            ContextLog.info("Sign-in callback timed out; closed the listener", "auth")
            return .cancelled
        case .stopped:
            return .cancelled
        case .socketCreationFailed, .bindFailed, .listenFailed, .portLookupFailed:
            return .badResponse("Context for Claude couldn't listen for the sign-in response.")
        }
    }

    /// Firebase reports `expiresIn` as a string, `expires_in` sometimes as a number.
    private static func seconds(_ value: Any?) -> Int {
        if let text = value as? String, let parsed = Int(text) { return parsed }
        if let number = value as? Int { return number }
        if let number = value as? Double { return Int(number) }
        return 3600
    }

    /// A short, safe description of a failure body. Deliberately never the raw body: a misbehaving
    /// proxy could echo the request, and the request carries a token.
    private static func errorSummary(_ data: Data) -> String {
        guard let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
            let error = json["error"] as? [String: Any]
        else {
            return "response"
        }
        if let message = error["message"] as? String, !message.isEmpty {
            return String(message.prefix(120))
        }
        return "response"
    }

    private static func claim(_ name: String, in jwt: String) -> String? {
        let parts = jwt.split(separator: ".")
        guard parts.count >= 2 else { return nil }
        var base64 = String(parts[1])
            .replacingOccurrences(of: "-", with: "+")
            .replacingOccurrences(of: "_", with: "/")
        while base64.count % 4 != 0 { base64 += "=" }
        guard let data = Data(base64Encoded: base64),
            let payload = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        else {
            return nil
        }
        return payload[name] as? String
    }

    private static func formEncoded(_ pairs: [(String, String)]) -> String {
        pairs
            .map { "\(percentEncoded($0.0))=\(percentEncoded($0.1))" }
            .joined(separator: "&")
    }

    private static func percentEncoded(_ value: String) -> String {
        var allowed = CharacterSet.alphanumerics
        allowed.insert(charactersIn: "-._~")
        return value.addingPercentEncoding(withAllowedCharacters: allowed) ?? ""
    }
}
