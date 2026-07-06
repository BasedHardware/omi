import Foundation
@preconcurrency import FirebaseAuth
import OmiSupport
import CryptoKit
import AppKit
import AuthenticationServices
import Sentry
import Darwin

extension Notification.Name {
    /// Posted by AuthService.signOut() so views can reset @AppStorage-backed properties directly.
    static let userDidSignOut = Notification.Name("com.omi.desktop.userDidSignOut")
}

final class OAuthLoopbackCallbackServer: @unchecked Sendable {
    enum ServerError: Error {
        case socketCreationFailed
        case bindFailed
        case listenFailed
        case portLookupFailed
        case invalidRequest
    }

    private var socketFD: Int32?
    private var activeClientFD: Int32?
    private let queue = DispatchQueue(label: "com.omi.desktop.oauth-loopback-callback")
    private let lock = NSLock()
    private var continuation: CheckedContinuation<(code: String, state: String), Error>?
    private var pendingResult: Result<(code: String, state: String), Error>?
    private var completed = false
    private let expectedState: String

    let port: UInt16
    let redirectURI: String

    private init(socketFD: Int32, port: UInt16, expectedState: String) {
        self.socketFD = socketFD
        self.port = port
        self.expectedState = expectedState
        self.redirectURI = "http://127.0.0.1:\(port)/callback"
    }

    static func start(expectedState: String) throws -> OAuthLoopbackCallbackServer {
        let fd = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP)
        guard fd >= 0 else { throw ServerError.socketCreationFailed }

        var addr = sockaddr_in()
        addr.sin_len = UInt8(MemoryLayout<sockaddr_in>.size)
        addr.sin_family = sa_family_t(AF_INET)
        addr.sin_port = 0
        inet_pton(AF_INET, "127.0.0.1", &addr.sin_addr)

        let bindResult = withUnsafePointer(to: &addr) {
            $0.withMemoryRebound(to: sockaddr.self, capacity: 1) {
                bind(fd, $0, socklen_t(MemoryLayout<sockaddr_in>.size))
            }
        }
        guard bindResult == 0 else {
            close(fd)
            throw ServerError.bindFailed
        }

        guard listen(fd, 1) == 0 else {
            close(fd)
            throw ServerError.listenFailed
        }

        var boundAddr = sockaddr_in()
        var boundAddrLen = socklen_t(MemoryLayout<sockaddr_in>.size)
        let portResult = withUnsafeMutablePointer(to: &boundAddr) {
            $0.withMemoryRebound(to: sockaddr.self, capacity: 1) {
                getsockname(fd, $0, &boundAddrLen)
            }
        }
        guard portResult == 0 else {
            close(fd)
            throw ServerError.portLookupFailed
        }

        let server = OAuthLoopbackCallbackServer(
            socketFD: fd,
            port: UInt16(bigEndian: boundAddr.sin_port),
            expectedState: expectedState
        )
        server.acceptRequests()
        return server
    }

    func waitForCallback() async throws -> (code: String, state: String) {
        try await withCheckedThrowingContinuation { continuation in
            lock.lock()
            if let pendingResult {
                lock.unlock()
                continuation.resume(with: pendingResult)
                return
            }
            self.continuation = continuation
            lock.unlock()
        }
    }

    func cancel() {
        finish(.failure(AuthError.cancelled))
    }

    func fail(with error: Error) {
        finish(.failure(error))
    }

    func stop() {
        lock.lock()
        let alreadyCompleted = completed
        completed = true
        closeSocketsLocked()
        lock.unlock()
        if !alreadyCompleted {
            resumeIfNeeded(.failure(AuthError.cancelled))
        }
    }

    deinit {
        stop()
    }

    private func acceptRequests() {
        queue.async { [weak self] in
            guard let self else { return }

            while !self.isCompleted {
                guard let listenFD = self.currentListenSocket() else { return }

                var remoteAddr = sockaddr()
                var remoteLen = socklen_t(MemoryLayout<sockaddr>.size)
                let clientFD = accept(listenFD, &remoteAddr, &remoteLen)
                guard clientFD >= 0 else { continue }

                self.setActiveClient(clientFD)
                defer {
                    self.closeActiveClientIfMatching(clientFD)
                }

                var noSigPipe: Int32 = 1
                setsockopt(clientFD, SOL_SOCKET, SO_NOSIGPIPE, &noSigPipe, socklen_t(MemoryLayout<Int32>.size))

                var timeout = timeval(tv_sec: 5, tv_usec: 0)
                setsockopt(clientFD, SOL_SOCKET, SO_RCVTIMEO, &timeout, socklen_t(MemoryLayout<timeval>.size))

                var buffer = [UInt8](repeating: 0, count: 8192)
                let bytesRead = recv(clientFD, &buffer, buffer.count - 1, 0)
                guard bytesRead > 0,
                      let request = String(bytes: buffer.prefix(bytesRead), encoding: .utf8) else {
                    self.sendResponse(clientFD, status: "400 Bad Request", message: "Invalid authentication callback.")
                    continue
                }

                switch self.parseCallbackRequest(request) {
                case .success(let code, let state):
                    self.sendResponse(clientFD, status: "200 OK", message: "Authentication complete. You can close this tab.")
                    self.finish(.success((code: code, state: state)))
                    return
                case .providerError(let error):
                    self.sendResponse(clientFD, status: "400 Bad Request", message: "Authentication failed. You can close this tab.")
                    self.finish(.failure(AuthError.oauthError(error)))
                    return
                case .ignore:
                    self.sendResponse(clientFD, status: "400 Bad Request", message: "Invalid authentication callback.")
                    continue
                }
            }
        }
    }

    private enum ParsedCallbackRequest {
        case success(code: String, state: String)
        case providerError(String)
        case ignore
    }

    private func parseCallbackRequest(_ request: String) -> ParsedCallbackRequest {
        guard let requestLine = request.split(separator: "\r\n", maxSplits: 1).first else {
            return .ignore
        }
        let parts = requestLine.split(separator: " ")
        guard parts.count >= 2, parts[0] == "GET" else {
            return .ignore
        }

        let target = String(parts[1])
        guard let components = URLComponents(string: "http://127.0.0.1\(target)"),
              components.path == "/callback" else {
            return .ignore
        }

        let queryItems = components.queryItems ?? []
        guard let state = queryItems.first(where: { $0.name == "state" })?.value,
              state == expectedState else {
            return .ignore
        }

        if let providerError = queryItems.first(where: { $0.name == "error" })?.value {
            return .providerError(providerError)
        }

        guard let code = queryItems.first(where: { $0.name == "code" })?.value else {
            return .ignore
        }
        return .success(code: code, state: state)
    }

    private func sendResponse(_ clientFD: Int32, status: String, message: String) {
        let body = """
        <!doctype html><html><head><meta charset="utf-8"><title>Omi Authentication</title></head><body><p>\(message)</p></body></html>
        """
        let response = """
        HTTP/1.1 \(status)\r
        Content-Type: text/html; charset=utf-8\r
        Content-Length: \(body.utf8.count)\r
        Connection: close\r
        \r
        \(body)
        """
        response.withCString { pointer in
            _ = send(clientFD, pointer, strlen(pointer), 0)
        }
    }

    private func finish(_ result: Result<(code: String, state: String), Error>) {
        lock.lock()
        guard !completed else {
            lock.unlock()
            return
        }
        completed = true
        closeSocketsLocked()
        lock.unlock()
        resumeIfNeeded(result)
    }

    private func resumeIfNeeded(_ result: Result<(code: String, state: String), Error>) {
        lock.lock()
        if let continuation {
            self.continuation = nil
            lock.unlock()
            continuation.resume(with: result)
        } else {
            pendingResult = result
            lock.unlock()
        }
    }

    private var isCompleted: Bool {
        lock.lock()
        defer { lock.unlock() }
        return completed
    }

    private func currentListenSocket() -> Int32? {
        lock.lock()
        defer { lock.unlock() }
        return socketFD
    }

    private func setActiveClient(_ fd: Int32) {
        lock.lock()
        activeClientFD = fd
        lock.unlock()
    }

    private func closeActiveClientIfMatching(_ fd: Int32) {
        lock.lock()
        if activeClientFD == fd {
            activeClientFD = nil
            close(fd)
        }
        lock.unlock()
    }

    private func closeSocketsLocked() {
        if let activeClientFD {
            close(activeClientFD)
            self.activeClientFD = nil
        }
        if let socketFD {
            close(socketFD)
            self.socketFD = nil
        }
    }
}

@MainActor
class AuthService {
    static let shared = AuthService()

    // Use AuthState for UI updates - it's a pure Swift ObservableObject
    // that doesn't reference Firebase types at the class level
    private var authState: AuthState { AuthState.shared }

    var isSignedIn: Bool {
        get { authState.isSignedIn }
        set { authState.isSignedIn = newValue }
    }
    var isLoading: Bool {
        get { authState.isLoading }
        set { authState.isLoading = newValue }
    }
    var error: String? {
        get { authState.error }
        set { authState.error = newValue }
    }

    private var authStateHandle: AuthStateDidChangeListenerHandle?
    private var isConfigured: Bool = false

    // OAuth state for CSRF protection
    private var pendingOAuthState: String?
    private var pendingOAuthFlow: OAuthFlowContext?
    private var loopbackCallbackServer: OAuthLoopbackCallbackServer?
    private var oauthContinuation: CheckedContinuation<(code: String, state: String), Error>?
    private var oauthTimeoutTask: Task<Void, Never>?

    // Native Apple Sign In
    private var currentNonce: String?
    private var appleSignInDelegate: AppleSignInDelegate?

    // API Configuration
    // Auth uses the production Python backend by default because web OAuth
    // provider callbacks are host allowlisted. Override with OMI_AUTH_API_URL
    // for local auth backend testing.
    private var apiBaseURL: String {
        DesktopBackendEnvironment.authBaseURL()
    }
    private var redirectURI: String {
        return "\(urlScheme)://auth/callback"
    }

    private var currentBundleIdentifier: String {
        Bundle.main.bundleIdentifier ?? "unknown.bundle"
    }

    private var urlScheme: String {
        if let urlTypes = Bundle.main.infoDictionary?["CFBundleURLTypes"] as? [[String: Any]],
           let firstType = urlTypes.first,
           let schemes = firstType["CFBundleURLSchemes"] as? [String],
           let scheme = schemes.first {
            return scheme
        }
        return "omi-computer"
    }

    private struct OAuthFlowContext {
        let id: String
        let provider: String
        let state: String
        let startedAt: Date
        let callbackTransport: String
    }

    // UserDefaults keys for auth persistence (dev builds with ad-hoc signing).
    // Keys are defined once in `DefaultsKey` and read/written through the typed
    // `UserDefaults` accessors so a typo is a compile error, not a silent nil.
    private let authTokenKeychainService = "com.omi.desktop.firebase-rest-session"
    private let authTokenKeychainAccount = "firebase-rest-tokens"

    private struct StoredAuthTokens: Codable {
        let idToken: String
        let refreshToken: String
        let expiryTime: TimeInterval
        let tokenUserId: String
    }

    private var cachedStoredTokens: StoredAuthTokens?
    private var cachedStoredTokensLoaded = false

    private func invalidateStoredTokensCache() {
        cachedStoredTokens = nil
        cachedStoredTokensLoaded = false
    }

    // Firebase Web API key — fetched from backend via APIKeyService, set as env var.
    // No hardcoded fallback — if the key isn't available, auth operations will fail
    // with a clear error instead of silently using a potentially wrong key.
    private var firebaseApiKey: String {
        if let envKey = getenv("FIREBASE_API_KEY"), let key = String(validatingUTF8: envKey), !key.isEmpty {
            return key
        }
        log("AuthService: FIREBASE_API_KEY not set — auth operations will fail")
        return ""
    }

    /// Resolve the Firebase Web API key or fail loudly (BL-019).
    ///
    /// The key is provisioned asynchronously (APIKeyService fetches it from the
    /// backend and `setenv`s it), so it can legitimately be absent right after a
    /// cold launch — failing at launch would false-positive. Instead, fail at the
    /// point of use: every identitytoolkit/securetoken request must resolve the key
    /// through this helper so a missing/empty key surfaces as a clear, user-visible
    /// `AuthError` instead of being interpolated into `?key=` and returning an
    /// opaque HTTP 400 ("API key not valid") that looks like a generic auth failure.
    private func requireFirebaseApiKey() throws -> String {
        let key = firebaseApiKey
        guard !key.isEmpty else {
            log("AuthService: refusing to build an auth request without FIREBASE_API_KEY")
            throw AuthError.missingFirebaseApiKey
        }
        return key
    }

    // MARK: - User Name Properties

    /// Get the user's given name (first name)
    var givenName: String {
        get { UserDefaults.standard.string(forKey: .authGivenName) ?? "" }
        set { UserDefaults.standard.set(newValue, forKey: .authGivenName) }
    }

    /// Get the user's family name (last name)
    var familyName: String {
        get { UserDefaults.standard.string(forKey: .authFamilyName) ?? "" }
        set { UserDefaults.standard.set(newValue, forKey: .authFamilyName) }
    }

    /// Get the user's full display name
    var displayName: String {
        let given = givenName
        let family = familyName
        if !given.isEmpty && !family.isEmpty {
            return "\(given) \(family)"
        } else if !given.isEmpty {
            return given
        } else if !family.isEmpty {
            return family
        }
        return ""
    }

    init() {
        // Initialize without super
    }

    // MARK: - Configuration (call after FirebaseApp.configure())

    func configure() {
        guard !isConfigured else { return }
        isConfigured = true
        restoreAuthState()
        setupAuthStateListener()

        // Timeout: if auth isn't restored within 5 seconds, stop showing loading
        DispatchQueue.main.asyncAfter(deadline: .now() + 5.0) {
            if AuthState.shared.isRestoringAuth {
                NSLog("OMI AUTH: Auth restore timed out after 5s, clearing loading state")
                AuthState.shared.isRestoringAuth = false
            }
        }
    }

    func bootstrapLocalHarnessAuthIfNeeded() async {
        defer { AuthState.shared.isRestoringAuth = false }
        guard let email = DesktopLocalProfile.selectedEmail,
              let password = DesktopLocalProfile.selectedPassword,
              let selectedUser = DesktopLocalProfile.selectedUser else {
            log("OMI AUTH LOCAL: missing selected local auth user env; staying signed out")
            return
        }

        if let savedEmail = UserDefaults.standard.string(forKey: .authUserEmail),
           !savedEmail.isEmpty, savedEmail != email {
            clearPersistedAuthState()
            clearTokens()
            log("OMI AUTH LOCAL: cleared stale persisted auth for email=\(savedEmail)")
        }

        do {
            let tokens = try await signInWithPasswordViaAuthEmulator(email: email, password: password)
            try saveTokens(
                idToken: tokens.idToken,
                refreshToken: tokens.refreshToken,
                expiresIn: tokens.expiresIn,
                userId: tokens.localId
            )
            AuthState.shared.userEmail = email
            isSignedIn = true
            saveAuthState(isSignedIn: true, email: email, userId: tokens.localId)
            if let display = DesktopLocalProfile.selectedDisplayName, !display.isEmpty {
                let pieces = display.split(separator: " ", maxSplits: 1).map(String.init)
                givenName = pieces.first ?? ""
                familyName = pieces.count > 1 ? pieces[1] : ""
            }
            await RewindDatabase.shared.configure(userId: tokens.localId)
            log("OMI AUTH LOCAL: signed in via emulator REST as \(email) uid=\(tokens.localId) user=\(selectedUser)")
        } catch {
            logError("OMI AUTH LOCAL: sign-in failed for \(email)", error: error)
            self.error = "Local Auth emulator sign-in failed for \(email): \(error.localizedDescription)"
            isSignedIn = false
        }
    }

    private func signInWithPasswordViaAuthEmulator(email: String, password: String) async throws -> FirebaseTokenResult {
        guard let hostPort = DesktopLocalProfile.authEmulatorHost else {
            throw AuthError.invalidURL
        }
        let apiKey = try requireFirebaseApiKey()
        guard let url = URL(
            string: "http://\(hostPort)/identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key=\(apiKey)"
        ) else {
            throw AuthError.invalidURL
        }

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.timeoutInterval = 10
        request.httpBody = try JSONSerialization.data(withJSONObject: [
            "email": email,
            "password": password,
            "returnSecureToken": true,
        ])

        let (data, response) = try await URLSession.shared.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse else {
            throw AuthError.invalidResponse
        }
        guard httpResponse.statusCode == 200 else {
            let errorBody = String(data: data, encoding: .utf8) ?? "unknown"
            log("OMI AUTH LOCAL: emulator REST error \(httpResponse.statusCode): \(errorBody)")
            throw AuthError.tokenExchangeFailed(httpResponse.statusCode)
        }

        guard let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let idToken = json["idToken"] as? String,
              let refreshToken = json["refreshToken"] as? String else {
            throw AuthError.invalidResponse
        }
        let expiresIn = Int(json["expiresIn"] as? String ?? "3600") ?? 3600
        let localId = json["localId"] as? String ?? selectedLocalUserId(from: idToken) ?? ""
        guard !localId.isEmpty else {
            throw AuthError.invalidResponse
        }
        return FirebaseTokenResult(
            idToken: idToken,
            refreshToken: refreshToken,
            expiresIn: expiresIn,
            localId: localId
        )
    }

    private func selectedLocalUserId(from idToken: String) -> String? {
        guard let payload = decodeJWT(idToken) else { return nil }
        return payload["user_id"] as? String ?? payload["sub"] as? String
    }

    // MARK: - Auth Persistence (UserDefaults for dev builds)

    private func saveAuthState(isSignedIn: Bool, email: String?, userId: String?) {
        UserDefaults.standard.set(isSignedIn, forKey: .authIsSignedIn)
        UserDefaults.standard.set(email, forKey: .authUserEmail)
        UserDefaults.standard.set(userId, forKey: .authUserId)
        UserDefaults.standard.synchronize()  // Force flush before process can be killed
        NSLog("OMI AUTH: Saved auth state - signedIn: %@, email: %@", isSignedIn ? "true" : "false", email ?? "nil")
    }

    private func clearPersistedAuthState() {
        UserDefaults.standard.removeObject(forKey: .authIsSignedIn)
        UserDefaults.standard.removeObject(forKey: .authUserEmail)
        UserDefaults.standard.removeObject(forKey: .authUserId)
        UserDefaults.standard.removeObject(forKey: .authIdToken)
        UserDefaults.standard.removeObject(forKey: .authRefreshToken)
        UserDefaults.standard.removeObject(forKey: .authTokenExpiry)
        UserDefaults.standard.removeObject(forKey: .authTokenUserId)
    }

    private func restoreAuthState() {
        // Check if we have a saved auth state
        let savedSignedIn = UserDefaults.standard.bool(forKey: .authIsSignedIn)
        let savedEmail = UserDefaults.standard.string(forKey: .authUserEmail)

        NSLog("OMI AUTH: Checking saved auth state - savedSignedIn: %@, savedEmail: %@",
              savedSignedIn ? "true" : "false", savedEmail ?? "nil")

        // Set auth state synchronously (we're already on main thread from configure()).
        // Using DispatchQueue.main.async here would defer to the next run-loop tick,
        // creating a race window where the Firebase auth state listener can fire first
        // with user=nil and flip isSignedIn to false before we restore it.
        if savedSignedIn {
            // Check if Firebase also has a current user (session might still be valid)
            if let currentUser = Auth.auth().currentUser {
                NSLog("OMI AUTH: Restored auth state from Firebase - uid: %@", currentUser.uid)
                self.isSignedIn = true
                AuthState.shared.userEmail = currentUser.email ?? savedEmail
                AuthState.shared.isRestoringAuth = false
                self.loadNameFromBackendIfNeeded()
            } else {
                // Firebase doesn't have user, but we have saved state
                // This can happen with ad-hoc signing where Keychain doesn't persist
                NSLog("OMI AUTH: Restored auth state from UserDefaults (Firebase session expired)")

                // Migration: Fix empty userId by extracting from stored idToken
                let savedUserId = UserDefaults.standard.string(forKey: .authUserId) ?? ""
                if savedUserId.isEmpty, let storedToken = storedIdToken {
                    if let payload = decodeJWT(storedToken),
                       let userId = payload["user_id"] as? String ?? payload["sub"] as? String {
                        NSLog("OMI AUTH: Migrating empty userId - extracted from JWT: %@", userId)
                        UserDefaults.standard.set(userId, forKey: .authUserId)
                    }
                }

                self.isSignedIn = true
                AuthState.shared.userEmail = savedEmail
                AuthState.shared.isRestoringAuth = false
                validateRestoredUserDefaultsSession()
            }
        } else {
            NSLog("OMI AUTH: No saved auth state found")
            AuthState.shared.isRestoringAuth = false
        }
    }

    private func validateRestoredUserDefaultsSession() {
        Task { [weak self] in
            guard let self else { return }
            guard self.storedIdToken != nil else {
                NSLog("OMI AUTH: Restored UserDefaults session validation deferred - no cached ID token")
                return
            }
            guard !self.isTokenExpired else {
                NSLog("OMI AUTH: Restored UserDefaults session validation deferred - cached ID token expired")
                return
            }
            do {
                _ = try await self.getIdToken(forceRefresh: false)
                NSLog("OMI AUTH: Restored UserDefaults session validated from cached ID token")
                APIKeyService.shared.startFetchingKeys()
                Task { await FloatingBarUsageLimiter.shared.fetchPlan() }
            } catch AuthError.notSignedIn {
                if self.storedIdToken == nil || self.storedRefreshToken == nil {
                    // getIdToken() can clear tokens internally before surfacing notSignedIn —
                    // e.g. a stored token/user mismatch after an account switch (it clears the
                    // stale token, then the refresh path has no token). The entry guard proved
                    // a cached ID token existed, so if it's gone now the session is genuinely
                    // dead; preserving isSignedIn would leave a ghost signed-in UI with no
                    // credentials. Sign out cleanly so the UI shows sign-in.
                    NSLog("OMI AUTH: Restored UserDefaults session validation cleared tokens - signing out")
                    self.isSignedIn = false
                    AuthState.shared.userEmail = nil
                    AuthState.shared.isRestoringAuth = false
                    self.saveAuthState(isSignedIn: false, email: nil, userId: nil)
                } else if self.isSignedIn {
                    // Tokens survived — a transient/race failure (e.g. Firebase SDK user not
                    // yet restored). Keep the restored session; on-demand refresh recovers it.
                    NSLog("OMI AUTH: Restored UserDefaults session validation deferred - preserving restored session")
                } else {
                    NSLog("OMI AUTH: Restored UserDefaults session validation found signed-out state")
                    AuthState.shared.userEmail = nil
                    AuthState.shared.isRestoringAuth = false
                }
            } catch {
                NSLog("OMI AUTH: Restored UserDefaults session validation deferred: %@", error.localizedDescription)
            }
        }
    }

    // MARK: - Auth State Listener

    private func setupAuthStateListener() {
        authStateHandle = Auth.auth().addStateDidChangeListener { [weak self] _, user in
            Task { @MainActor in
                if user != nil {
                    // Firebase has a user - trust it
                    log("AUTH_LISTENER: Firebase user present (uid=\(user?.uid ?? "nil")), setting isSignedIn=true")
                    self?.isSignedIn = true
                    AuthState.shared.userEmail = user?.email
                    AuthState.shared.isRestoringAuth = false
                    self?.saveAuthState(isSignedIn: true, email: user?.email, userId: user?.uid)
                    // Configure database for the signed-in user immediately so any code
                    // that touches the DB during onboarding (e.g. save_knowledge_graph)
                    // writes to the correct per-user path instead of "anonymous".
                    if let uid = user?.uid {
                        Task { await RewindDatabase.shared.configure(userId: uid) }
                    }
                    // Load name from backend profile (Firestore), then Firebase Auth as fallback
                    self?.loadNameFromBackendIfNeeded()
                    // Sync assistant settings from backend (fire-and-forget)
                    Task { await SettingsSyncManager.shared.syncFromServer() }
                } else {
                    // Firebase has no user - check if we have a saved session (for dev builds where Keychain doesn't persist)
                    let savedSignedIn = UserDefaults.standard.bool(forKey: .authIsSignedIn)
                    log("AUTH_LISTENER: Firebase user nil, savedSignedIn=\(savedSignedIn), currentIsSignedIn=\(self?.isSignedIn ?? false)")
                    if !savedSignedIn {
                        // No saved session either - user is truly signed out
                        log("AUTH_LISTENER: No saved session - setting isSignedIn=false")
                        self?.isSignedIn = false
                        AuthState.shared.userEmail = nil
                        AuthState.shared.isRestoringAuth = false
                    } else {
                        log("AUTH_LISTENER: Keeping saved session (not overriding isSignedIn)")
                    }
                }
            }
        }
    }

    // MARK: - Sign in with Apple (Native with Web OAuth Fallback)

    @MainActor
    func signInWithApple() async throws {
        // Use web OAuth directly — native Apple Sign In requires entitlements that
        // don't work reliably across dev/release builds. Web OAuth works everywhere.
        try await signIn(provider: "apple")
    }

    // MARK: - Native Apple Sign In (requires com.apple.developer.applesignin entitlement)

    @MainActor
    private func signInWithAppleNative() async throws {
        NSLog("OMI AUTH: Starting native Apple Sign In")
        isLoading = true
        error = nil
        AnalyticsManager.shared.signInStarted(provider: "apple")
        defer { isLoading = false }

        // Step 1: Generate nonce for security
        let nonce = generateNonce()
        currentNonce = nonce
        let hashedNonce = sha256(nonce)

        // Step 2: Perform native Apple Sign In
        let appleCredential = try await performAppleSignIn(hashedNonce: hashedNonce)
        appleSignInDelegate = nil  // Clean up

        // Step 3: Extract identity token
        guard let identityTokenData = appleCredential.identityToken,
              let identityToken = String(data: identityTokenData, encoding: .utf8) else {
            throw AuthError.missingToken
        }
        NSLog("OMI AUTH: Got Apple identity token")

        // Save user name if provided (Apple only sends name on first sign-in)
        if let fullName = appleCredential.fullName {
            let given = fullName.givenName ?? ""
            let family = fullName.familyName ?? ""
            if !given.isEmpty {
                givenName = given
                familyName = family
                NSLog("OMI AUTH: Saved name from Apple: %@ %@", given, family)
            }
        }
        if let email = appleCredential.email {
            AuthState.shared.userEmail = email
        }

        // Step 4: Sign in with Firebase using Apple credential
        // Use Firebase SDK first (handles native bundle ID audience correctly),
        // fall back to REST API (for web OAuth audience 'me.omi.web')
        NSLog("OMI AUTH: Signing in with Firebase using Apple identity token...")

        let credential = OAuthProvider.credential(providerID: .apple, idToken: identityToken, rawNonce: nonce)
        var userId = ""

        do {
            // Firebase SDK sign-in (works with native bundle ID as token audience)
            let authResult = try await Auth.auth().signIn(with: credential)
            NSLog("OMI AUTH: Firebase SDK sign-in SUCCESS - uid: %@", authResult.user.uid)
            userId = authResult.user.uid

            // Get ID token from Firebase SDK for API calls
            let tokenResult = try await authResult.user.getIDTokenResult()
            let idToken = tokenResult.token
            let refreshToken = authResult.user.refreshToken ?? ""
            let expiresIn = Int(tokenResult.expirationDate.timeIntervalSinceNow)

            try saveTokens(idToken: idToken, refreshToken: refreshToken, expiresIn: expiresIn, userId: userId)
        } catch {
            // Fall back to REST API (works when Firebase SDK has keychain issues)
            let nsError = error as NSError
            NSLog("OMI AUTH: Firebase SDK Apple sign-in failed (domain=%@ code=%d): %@", nsError.domain, nsError.code, error.localizedDescription)
            logError("AUTH: Firebase SDK Apple sign-in failed (domain=\(nsError.domain) code=\(nsError.code))", error: error)
            NSLog("OMI AUTH: Falling back to REST API for Apple sign-in...")
            let firebaseTokens = try await signInWithAppleIdentityToken(identityToken: identityToken, nonce: nonce)
            userId = firebaseTokens.localId
            try saveTokens(idToken: firebaseTokens.idToken, refreshToken: firebaseTokens.refreshToken, expiresIn: firebaseTokens.expiresIn, userId: userId)
        }

        isSignedIn = true

        // Extract email from identity token if not provided by Apple
        if AuthState.shared.userEmail == nil {
            if let payload = decodeJWT(identityToken),
               let email = payload["email"] as? String {
                AuthState.shared.userEmail = email
            }
        }

        saveAuthState(isSignedIn: true, email: AuthState.shared.userEmail, userId: userId)
        Task { await RewindDatabase.shared.configure(userId: userId) }

        if givenName.isEmpty {
            loadNameFromBackendIfNeeded()
        }

        AnalyticsManager.shared.identify()
        AnalyticsManager.shared.signInCompleted(provider: "apple")
        APIKeyService.shared.startFetchingKeys()
        Task { await FloatingBarUsageLimiter.shared.fetchPlan() }

        // Start trial polling for the newly signed-in user
        if let state = AppState.current {
            state.startTrialMetadataRefresh()
            TrialBannerService.shared.start(appState: state)
        }
        // Refresh the chat usage limiter for the new account (PTT gate + floating
        // bar read it); without this it stays nil/old until the next app launch.
        Task { await FloatingBarUsageLimiter.shared.fetchPlan() }

        if !AnalyticsManager.isDevBuild {
            let sentryUser = User(userId: userId)
            sentryUser.email = AuthState.shared.userEmail
            sentryUser.username = displayName.isEmpty ? nil : displayName
            SentrySDK.setUser(sentryUser)
        }

        NSLog("OMI AUTH: Apple Sign in complete!")
        fetchConversations()
    }

    // MARK: - Sign in with Google (Web OAuth Flow)

    @MainActor
    func signInWithGoogle() async throws {
        try await signIn(provider: "google")
    }

    // MARK: - Generic OAuth Sign In

    @MainActor
    private func signIn(provider: String) async throws {
        // Guard against double sign-in (e.g., rapid button clicks before UI updates)
        guard !isLoading else {
            NSLog("OMI AUTH: Sign in already in progress, ignoring duplicate request")
            return
        }

        NSLog("OMI AUTH: Starting Sign in with %@ (Web OAuth)", provider)
        isLoading = true
        error = nil

        // Track sign-in started
        AnalyticsManager.shared.signInStarted(provider: provider)

        var activeFlowId: String?
        var activeFlowStartedAt: Date?
        var activeCallbackServer: OAuthLoopbackCallbackServer?
        var activeCallbackTransport = "custom_scheme"

        defer {
            if activeFlowId == nil || pendingOAuthFlow == nil || pendingOAuthFlow?.id == activeFlowId {
                isLoading = false
            }
        }

        do {
            // Step 1: Generate state for CSRF protection
            let flowId = generateOAuthFlowID()
            let state = generateState(flowId: flowId)
            let codeVerifier = generateCodeVerifier()
            let codeChallenge = makeCodeChallenge(for: codeVerifier)
            let startedAt = Date()
            activeFlowId = flowId
            activeFlowStartedAt = startedAt
            pendingOAuthState = state

            let callbackServer: OAuthLoopbackCallbackServer?
            do {
                callbackServer = try OAuthLoopbackCallbackServer.start(expectedState: state)
                activeCallbackServer = callbackServer
                loopbackCallbackServer = callbackServer
            } catch {
                callbackServer = nil
                let nsError = error as NSError
                trackAuthFlowEvent(
                    "Auth Callback Server Failed",
                    stage: "callback_server_started",
                    provider: provider,
                    authFlowId: flowId,
                    failureClass: "\(nsError.domain)_\(nsError.code)",
                    error: error.localizedDescription,
                    extraProperties: ["callback_transport": "custom_scheme_fallback"]
                )
            }
            let selectedRedirectURI = callbackServer?.redirectURI ?? redirectURI
            let selectedCallbackTransport = callbackServer == nil ? "custom_scheme_fallback" : "loopback"
            activeCallbackTransport = selectedCallbackTransport
            pendingOAuthFlow = OAuthFlowContext(
                id: flowId,
                provider: provider,
                state: state,
                startedAt: startedAt,
                callbackTransport: selectedCallbackTransport
            )

            trackAuthFlowEvent(
                "Auth Flow Started",
                stage: "started",
                provider: provider,
                authFlowId: flowId,
                extraProperties: ["callback_transport": selectedCallbackTransport]
            )
            if let callbackServer {
                trackAuthFlowEvent(
                    "Auth Callback Server Started",
                    stage: "callback_server_started",
                    provider: provider,
                    authFlowId: flowId,
                    extraProperties: [
                        "callback_transport": selectedCallbackTransport,
                        "redirect_scheme": "http",
                        "loopback_port": callbackServer.port
                    ]
                )
            }
            NSLog("OMI AUTH: Generated OAuth state")

            // Step 2: Build authorization URL
            let authURL = buildAuthorizationURL(
                provider: provider,
                state: state,
                codeChallenge: codeChallenge,
                redirectURI: selectedRedirectURI
            )
            NSLog("OMI AUTH: Opening browser for authentication")

            // Step 3: Open browser for authentication
            guard let url = URL(string: authURL) else {
                trackAuthFlowEvent("Auth Callback Invalid", stage: "authorize_url", provider: provider, authFlowId: flowId, failureClass: "invalid_url")
                throw AuthError.invalidURL
            }
            NSWorkspace.shared.open(url)
            trackAuthFlowEvent("Auth Browser Opened", stage: "browser_opened", provider: provider, authFlowId: flowId)

            // Step 4: Wait for callback with authorization code
            NSLog("OMI AUTH: Waiting for OAuth callback...")
            let (code, returnedState) = try await waitForOAuthCallback(callbackServer: callbackServer)
            clearLoopbackCallbackServerIfCurrent(callbackServer, flowId: flowId)
            if callbackServer != nil {
                trackAuthFlowEvent(
                    "Auth Callback Received",
                    stage: "callback_received",
                    provider: provider,
                    authFlowId: flowId
                )
            }

            // Step 5: Verify state matches
            guard returnedState == state else {
                NSLog("OMI AUTH: State mismatch - potential CSRF attack")
                trackAuthFlowEvent(
                    "Auth Callback Invalid",
                    stage: "state_verified",
                    provider: provider,
                    authFlowId: flowId,
                    failureClass: "state_mismatch"
                )
                throw AuthError.stateMismatch
            }
            if callbackServer != nil {
                trackAuthFlowEvent(
                    "Auth Callback Valid",
                    stage: "callback_validated",
                    provider: provider,
                    authFlowId: flowId
                )
            }
            NSLog("OMI AUTH: Received valid authorization code")

            // Step 6: Exchange code for custom token and user info
            NSLog("OMI AUTH: Exchanging code for Firebase token...")
            trackAuthFlowEvent("Auth Token Exchange Started", stage: "token_exchange", provider: provider, authFlowId: flowId)
            let tokenResult: TokenExchangeResult
            do {
                tokenResult = try await exchangeCodeForToken(
                    code: code,
                    codeVerifier: codeVerifier,
                    redirectURI: selectedRedirectURI
                )
            } catch {
                trackAuthFlowEvent(
                    "Auth Token Exchange Failed",
                    stage: "token_exchange",
                    provider: provider,
                    authFlowId: flowId,
                    failureClass: authFailureClass(for: error),
                    error: error.localizedDescription
                )
                throw error
            }
            trackAuthFlowEvent("Auth Token Exchange Completed", stage: "token_exchange", provider: provider, authFlowId: flowId)
            NSLog("OMI AUTH: Got Firebase custom token")

            // Save user info from OAuth response immediately (before Firebase sign-in)
            // This ensures we have the name even if Firebase session doesn't persist
            if let extractedGivenName = tokenResult.givenName, !extractedGivenName.isEmpty {
                givenName = extractedGivenName
                familyName = tokenResult.familyName ?? ""
                NSLog("OMI AUTH: Saved name from OAuth: %@ %@", givenName, familyName)
            }
            if let extractedEmail = tokenResult.email {
                AuthState.shared.userEmail = extractedEmail
            }

            // Step 7: Exchange custom token for ID token via REST API
            // This bypasses keychain issues with Firebase SDK on dev builds
            NSLog("OMI AUTH: Exchanging custom token for ID token via REST API...")
            trackAuthFlowEvent(
                "Firebase Custom Token Exchange Started",
                stage: "firebase_custom_token_exchange",
                provider: provider,
                authFlowId: flowId
            )
            let firebaseTokens: FirebaseTokenResult
            do {
                firebaseTokens = try await exchangeCustomTokenForIdToken(customToken: tokenResult.customToken)
            } catch {
                trackAuthFlowEvent(
                    "Firebase Custom Token Exchange Failed",
                    stage: "firebase_custom_token_exchange",
                    provider: provider,
                    authFlowId: flowId,
                    failureClass: authFailureClass(for: error),
                    error: error.localizedDescription
                )
                throw error
            }
            trackAuthFlowEvent(
                "Firebase Custom Token Exchange Completed",
                stage: "firebase_custom_token_exchange",
                provider: provider,
                authFlowId: flowId
            )
            NSLog("OMI AUTH: Got Firebase ID token via REST API")

            // Store tokens for API calls (include userId to validate token ownership on retrieval)
            try saveTokens(idToken: firebaseTokens.idToken, refreshToken: firebaseTokens.refreshToken, expiresIn: firebaseTokens.expiresIn, userId: firebaseTokens.localId)

            // Also try Firebase SDK sign-in (best effort for other Firebase features)
            do {
                let authResult = try await Auth.auth().signIn(withCustomToken: tokenResult.customToken)
                NSLog("OMI AUTH: Firebase SDK sign-in SUCCESS - uid: %@", authResult.user.uid)
            } catch let firebaseError as NSError {
                // Keychain errors are expected on dev builds - we have REST API tokens as fallback
                NSLog("OMI AUTH: Firebase SDK sign-in failed (using REST API tokens): %@", firebaseError.localizedDescription)
            }

            isSignedIn = true

            // Save auth state immediately
            let userId = firebaseTokens.localId
            saveAuthState(isSignedIn: true, email: tokenResult.email, userId: userId)
            await RewindDatabase.shared.configure(userId: userId)

            // Try to load name from backend profile (Firestore), then Firebase Auth as fallback
            if givenName.isEmpty {
                loadNameFromBackendIfNeeded()
            }

            // Identify user first, then track sign-in completed
            // (identify must happen before events for PostHog person profiles to work)
            AnalyticsManager.shared.identify()
            trackAuthFlowEvent(
                "Auth Flow Completed",
                stage: "completed",
                provider: provider,
                authFlowId: flowId,
                terminalState: "completed",
                durationMs: authFlowDurationMs(startedAt: startedAt),
                extraProperties: ["callback_transport": selectedCallbackTransport]
            )
            AnalyticsManager.shared.signInCompleted(provider: provider)
            clearOAuthFlowIfCurrent(flowId: flowId, callbackServer: callbackServer)
            APIKeyService.shared.startFetchingKeys()
            Task { await FloatingBarUsageLimiter.shared.fetchPlan() }

            // Start trial polling for the newly signed-in user
            if let state = AppState.current {
                state.startTrialMetadataRefresh()
                TrialBannerService.shared.start(appState: state)
            }
            // Refresh the chat usage limiter for the new account (PTT gate +
            // floating bar read it); without this it stays nil/old until launch.
            Task { await FloatingBarUsageLimiter.shared.fetchPlan() }

            // Set Sentry user context for error tracking (skip in dev builds)
            if !AnalyticsManager.isDevBuild {
                let sentryUser = User(userId: userId)
                sentryUser.email = tokenResult.email
                sentryUser.username = displayName.isEmpty ? nil : displayName
                SentrySDK.setUser(sentryUser)
            }

            NSLog("OMI AUTH: Sign in complete!")

            // Fetch conversations after successful sign-in
            fetchConversations()

        } catch AuthError.cancelled {
            // User-initiated cancel: clear any stale error and stay silent.
            NSLog("OMI AUTH: %@ web OAuth sign-in cancelled by user", provider)
            trackAuthFlowEvent(
                "Auth Flow Cancelled",
                stage: "cancelled",
                provider: provider,
                authFlowId: activeFlowId,
                terminalState: "cancelled",
                durationMs: authFlowDurationMs(startedAt: activeFlowStartedAt),
                extraProperties: ["callback_transport": activeCallbackTransport]
            )
            if let activeFlowId {
                clearOAuthFlowIfCurrent(flowId: activeFlowId, callbackServer: activeCallbackServer)
            }
            self.error = nil
            throw AuthError.cancelled
        } catch AuthError.timeout {
            NSLog("OMI AUTH: %@ web OAuth sign-in timed out", provider)
            trackAuthFlowEvent(
                "Auth Flow Timed Out",
                stage: "timed_out",
                provider: provider,
                authFlowId: activeFlowId,
                terminalState: "timed_out",
                failureClass: "timeout",
                durationMs: authFlowDurationMs(startedAt: activeFlowStartedAt),
                extraProperties: ["callback_transport": activeCallbackTransport]
            )
            AnalyticsManager.shared.signInFailed(provider: provider, error: AuthError.timeout.localizedDescription)
            if let activeFlowId {
                clearOAuthFlowIfCurrent(flowId: activeFlowId, callbackServer: activeCallbackServer)
            }
            self.error = AuthError.timeout.localizedDescription
            throw AuthError.timeout
        } catch {
            let nsError = error as NSError
            NSLog("OMI AUTH: Error during sign in: %@", error.localizedDescription)
            logError("AUTH: \(provider) web OAuth sign-in failed (domain=\(nsError.domain) code=\(nsError.code))", error: error)
            trackAuthFlowEvent(
                "Auth Flow Failed",
                stage: "failed",
                provider: provider,
                authFlowId: activeFlowId,
                terminalState: "failed",
                failureClass: authFailureClass(for: error),
                error: error.localizedDescription,
                durationMs: authFlowDurationMs(startedAt: activeFlowStartedAt),
                extraProperties: ["callback_transport": activeCallbackTransport]
            )
            AnalyticsManager.shared.signInFailed(provider: provider, error: error.localizedDescription)
            if let activeFlowId {
                clearOAuthFlowIfCurrent(flowId: activeFlowId, callbackServer: activeCallbackServer)
            }
            self.error = error.localizedDescription
            throw error
        }
    }

    // MARK: - OAuth URL Building

    private func buildAuthorizationURL(provider: String, state: String, codeChallenge: String, redirectURI: String) -> String {
        var components = URLComponents(string: "\(apiBaseURL)v1/auth/authorize")
        components?.queryItems = [
            URLQueryItem(name: "provider", value: provider),
            URLQueryItem(name: "redirect_uri", value: redirectURI),
            URLQueryItem(name: "state", value: state),
            URLQueryItem(name: "code_challenge", value: codeChallenge),
            URLQueryItem(name: "code_challenge_method", value: "S256")
        ]
        return components?.url?.absoluteString ?? ""
    }

    private func trackCurrentAuthFlowEvent(
        _ eventName: String,
        stage: String,
        terminalState: String? = nil,
        failureClass: String? = nil,
        error: String? = nil
    ) {
        trackAuthFlowEvent(
            eventName,
            stage: stage,
            provider: pendingOAuthFlow?.provider ?? "unknown",
            authFlowId: pendingOAuthFlow?.id,
            terminalState: terminalState,
            failureClass: failureClass,
            error: error,
            durationMs: terminalState == nil ? nil : authFlowDurationMs()
        )
    }

    private func trackAuthFlowEvent(
        _ eventName: String,
        stage: String,
        provider: String,
        authFlowId: String?,
        terminalState: String? = nil,
        failureClass: String? = nil,
        error: String? = nil,
        durationMs: Int? = nil,
        extraProperties: [String: Any] = [:]
    ) {
        var properties = extraProperties
        properties["provider"] = provider
        properties["platform"] = "macos"
        properties["stage"] = stage
        properties["bundle_id"] = currentBundleIdentifier
        properties["url_scheme"] = urlScheme
        if properties["callback_transport"] == nil {
            properties["callback_transport"] = pendingOAuthFlow?.callbackTransport ?? "custom_scheme"
        }
        properties["auth_flow_id"] = authFlowId ?? "missing"
        properties["app_version"] = Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "unknown"
        properties["app_build"] = Bundle.main.infoDictionary?["CFBundleVersion"] as? String ?? "unknown"
        if let terminalState {
            properties["terminal_state"] = terminalState
        }
        if let failureClass {
            properties["failure_class"] = failureClass
        }
        if let error {
            properties["error"] = String(error.prefix(200))
        }
        if let durationMs {
            properties["duration_ms"] = durationMs
        }
        AnalyticsManager.shared.authFlowEvent(eventName, properties: properties)
    }

    private func authFlowDurationMs() -> Int? {
        guard let startedAt = pendingOAuthFlow?.startedAt else { return nil }
        return max(0, Int(Date().timeIntervalSince(startedAt) * 1000))
    }

    private func authFlowDurationMs(startedAt: Date?) -> Int? {
        guard let startedAt else { return nil }
        return max(0, Int(Date().timeIntervalSince(startedAt) * 1000))
    }

    private func clearLoopbackCallbackServerIfCurrent(_ callbackServer: OAuthLoopbackCallbackServer?, flowId: String) {
        guard let callbackServer else { return }
        callbackServer.stop()
        guard pendingOAuthFlow?.id == flowId, loopbackCallbackServer === callbackServer else { return }
        loopbackCallbackServer = nil
    }

    private func clearOAuthFlowIfCurrent(flowId: String, callbackServer: OAuthLoopbackCallbackServer?) {
        callbackServer?.stop()
        guard pendingOAuthFlow?.id == flowId else { return }
        if callbackServer == nil || loopbackCallbackServer === callbackServer {
            loopbackCallbackServer = nil
        }
        pendingOAuthFlow = nil
        pendingOAuthState = nil
    }

    private func authFailureClass(for error: Error) -> String {
        guard let authError = error as? AuthError else {
            let nsError = error as NSError
            return "\(nsError.domain)_\(nsError.code)"
        }

        switch authError {
        case .invalidCredential: return "invalid_credential"
        case .invalidNonce: return "invalid_nonce"
        case .missingToken: return "missing_token"
        case .missingFirebaseApiKey: return "missing_firebase_api_key"
        case .notSignedIn: return "not_signed_in"
        case .invalidURL: return "invalid_url"
        case .stateMismatch: return "state_mismatch"
        case .timeout: return "timeout"
        case .invalidCallback: return "invalid_callback"
        case .oauthError: return "oauth_error"
        case .missingCodeOrState: return "missing_code_or_state"
        case .invalidResponse: return "invalid_response"
        case .tokenExchangeFailed(let code): return "token_exchange_http_\(code)"
        case .missingCustomToken: return "missing_custom_token"
        case .keychainTokenStorageUnavailable: return "keychain_token_storage_unavailable"
        case .cancelled: return "cancelled"
        }
    }

    // MARK: - OAuth Callback Handling

    private func waitForOAuthCallback() async throws -> (code: String, state: String) {
        try await withCheckedThrowingContinuation { continuation in
            self.oauthContinuation = continuation
            let expectedState = self.pendingOAuthState

            // Set a timeout
            oauthTimeoutTask?.cancel()
            oauthTimeoutTask = Task {
                try? await Task.sleep(nanoseconds: 5 * 60 * 1_000_000_000) // 5 minutes
                guard !Task.isCancelled else { return }
                await MainActor.run {
                    guard self.pendingOAuthState == expectedState else { return }
                    self.resumeOAuthContinuation(throwing: AuthError.timeout)
                }
            }
        }
    }

    private func waitForOAuthCallback(callbackServer: OAuthLoopbackCallbackServer?) async throws -> (code: String, state: String) {
        guard let callbackServer else {
            return try await waitForOAuthCallback()
        }

        let timeoutTask = Task {
            try? await Task.sleep(nanoseconds: 5 * 60 * 1_000_000_000) // 5 minutes
            guard !Task.isCancelled else { return }
            callbackServer.fail(with: AuthError.timeout)
        }
        defer { timeoutTask.cancel() }

        return try await withTaskCancellationHandler {
            try await callbackServer.waitForCallback()
        } onCancel: {
            callbackServer.cancel()
        }
    }

    private func resumeOAuthContinuation(returning value: (code: String, state: String)) {
        oauthTimeoutTask?.cancel()
        oauthTimeoutTask = nil
        oauthContinuation?.resume(returning: value)
        oauthContinuation = nil
    }

    private func resumeOAuthContinuation(throwing error: Error) {
        oauthTimeoutTask?.cancel()
        oauthTimeoutTask = nil
        oauthContinuation?.resume(throwing: error)
        oauthContinuation = nil
    }
    /// Called by AppDelegate when the app receives an OAuth callback URL
    @MainActor
    func handleOAuthCallback(url: URL) {
        NSLog("OMI AUTH: Received OAuth callback: %@", url.absoluteString)

        guard let components = URLComponents(url: url, resolvingAgainstBaseURL: false) else {
            NSLog("OMI AUTH: Failed to parse callback URL")
            trackCurrentAuthFlowEvent(
                "Auth Callback Invalid",
                stage: "callback_parse",
                failureClass: "invalid_callback"
            )
            resumeOAuthContinuation(throwing: AuthError.invalidCallback)
            return
        }

        // Check if this is our auth callback
        guard url.scheme == urlScheme && url.host == "auth" && url.path == "/callback" else {
            NSLog("OMI AUTH: Not an auth callback URL")
            return
        }

        let queryItems = components.queryItems ?? []
        let code = queryItems.first(where: { $0.name == "code" })?.value
        let state = queryItems.first(where: { $0.name == "state" })?.value
        let error = queryItems.first(where: { $0.name == "error" })?.value
        let callbackFlowId = state.flatMap(authFlowId(from:))
        trackAuthFlowEvent(
            "Auth Callback Received",
            stage: "callback_received",
            provider: pendingOAuthFlow?.provider ?? "unknown",
            authFlowId: callbackFlowId ?? pendingOAuthFlow?.id
        )

        if let state, let targetBundleId = targetBundleIdentifier(from: state), targetBundleId != currentBundleIdentifier {
            NSLog(
                "OMI AUTH: Callback is for bundle %@, current bundle is %@. Forwarding...",
                targetBundleId,
                currentBundleIdentifier
            )
            trackAuthFlowEvent(
                "Auth Callback IgnoredWrongBundle",
                stage: "callback_bundle_check",
                provider: pendingOAuthFlow?.provider ?? "unknown",
                authFlowId: callbackFlowId,
                extraProperties: ["target_bundle_id": targetBundleId]
            )
            forwardOAuthCallback(url: url, toBundleId: targetBundleId, authFlowId: callbackFlowId)
            return
        }

        if let error = error {
            guard let state, state == pendingOAuthState else {
                NSLog("OMI AUTH: Ignoring OAuth error callback with missing or mismatched state")
                trackAuthFlowEvent(
                    "Auth Callback Invalid",
                    stage: "callback_provider_error_state",
                    provider: pendingOAuthFlow?.provider ?? "unknown",
                    authFlowId: callbackFlowId ?? pendingOAuthFlow?.id,
                    failureClass: "state_mismatch"
                )
                return
            }
            NSLog("OMI AUTH: OAuth error: %@", error)
            trackAuthFlowEvent(
                "Auth Callback Invalid",
                stage: "callback_provider_error",
                provider: pendingOAuthFlow?.provider ?? "unknown",
                authFlowId: callbackFlowId ?? pendingOAuthFlow?.id,
                failureClass: "provider_error",
                error: error
            )
            resumeOAuthContinuation(throwing: AuthError.oauthError(error))
            return
        }

        guard let code = code, let state = state else {
            NSLog("OMI AUTH: Missing code or state in callback")
            trackAuthFlowEvent(
                "Auth Callback Invalid",
                stage: "callback_params",
                provider: pendingOAuthFlow?.provider ?? "unknown",
                authFlowId: callbackFlowId ?? pendingOAuthFlow?.id,
                failureClass: "missing_code_or_state"
            )
            resumeOAuthContinuation(throwing: AuthError.missingCodeOrState)
            return
        }

        NSLog("OMI AUTH: Successfully extracted code and state from callback")
        trackAuthFlowEvent(
            "Auth Callback Valid",
            stage: "callback_validated",
            provider: pendingOAuthFlow?.provider ?? "unknown",
            authFlowId: callbackFlowId
        )
        resumeOAuthContinuation(returning: (code: code, state: state))
    }

    /// Cancel an in-flight web OAuth sign-in so the user can retry from a clean
    /// state. The recovery path we care about: the user fails on the web side
    /// (closed the tab, denied, or just walked away) and comes back to a
    /// desktop app whose sign-in buttons are still disabled waiting on a
    /// callback that will never arrive.
    @MainActor
    func cancelSignIn() {
        if let loopbackCallbackServer {
            NSLog("OMI AUTH: User cancelled in-flight loopback web OAuth sign-in")
            pendingOAuthState = nil
            loopbackCallbackServer.cancel()
            self.loopbackCallbackServer = nil
            isLoading = false
            return
        }

        guard oauthContinuation != nil else {
            // Callback wait already finished; later auth stages own loading and
            // cleanup so a stale cancel action cannot race a token exchange.
            return
        }
        NSLog("OMI AUTH: User cancelled in-flight web OAuth sign-in")
        pendingOAuthState = nil
        resumeOAuthContinuation(throwing: AuthError.cancelled)
    }

    // MARK: - Token Exchange

    /// Response from token exchange containing custom token and user info
    struct TokenExchangeResult {
        let customToken: String
        let givenName: String?
        let familyName: String?
        let email: String?
    }

    private func exchangeCodeForToken(code: String, codeVerifier: String, redirectURI: String) async throws -> TokenExchangeResult {
        guard let url = URL(string: "\(apiBaseURL)v1/auth/token") else {
            throw AuthError.invalidURL
        }

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/x-www-form-urlencoded", forHTTPHeaderField: "Content-Type")

        let bodyParams = [
            ("grant_type", "authorization_code"),
            ("code", code),
            ("redirect_uri", redirectURI),
            ("use_custom_token", "true"),
            ("code_verifier", codeVerifier)
        ]

        let bodyString = bodyParams
            .map { "\(formEncode($0.0))=\(formEncode($0.1))" }
            .joined(separator: "&")

        request.httpBody = bodyString.data(using: .utf8)

        NSLog("OMI AUTH: Sending token exchange request...")
        let (data, response) = try await URLSession.shared.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse else {
            throw AuthError.invalidResponse
        }

        NSLog("OMI AUTH: Token exchange response status: %d", httpResponse.statusCode)

        guard httpResponse.statusCode == 200 else {
            let responseBody = String(data: data, encoding: .utf8) ?? "unknown"
            NSLog("OMI AUTH: Token exchange failed: %@", responseBody)
            throw AuthError.tokenExchangeFailed(httpResponse.statusCode)
        }

        // Parse response
        guard let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            throw AuthError.invalidResponse
        }

        // Get custom token
        guard let customToken = json["custom_token"] as? String else {
            NSLog("OMI AUTH: No custom_token in response")
            throw AuthError.missingCustomToken
        }

        // Extract user info from id_token (JWT)
        var extractedGivenName: String?
        var extractedFamilyName: String?
        var extractedEmail: String?

        if let idToken = json["id_token"] as? String {
            if let userInfo = decodeJWT(idToken) {
                extractedGivenName = userInfo["given_name"] as? String
                extractedFamilyName = userInfo["family_name"] as? String
                extractedEmail = userInfo["email"] as? String

                // Fall back to "name" field if given_name not available
                if extractedGivenName == nil, let fullName = userInfo["name"] as? String {
                    let parts = fullName.split(separator: " ", maxSplits: 1)
                    extractedGivenName = parts.first.map(String.init)
                    extractedFamilyName = parts.count > 1 ? String(parts[1]) : nil
                }

                NSLog("OMI AUTH: Extracted from id_token - name: %@ %@, email: %@",
                      extractedGivenName ?? "(none)",
                      extractedFamilyName ?? "",
                      extractedEmail ?? "(none)")
            }
        }

        return TokenExchangeResult(
            customToken: customToken,
            givenName: extractedGivenName,
            familyName: extractedFamilyName,
            email: extractedEmail
        )
    }

    private func formEncode(_ value: String) -> String {
        var allowed = CharacterSet.alphanumerics
        allowed.insert(charactersIn: "-._~")
        return value.addingPercentEncoding(withAllowedCharacters: allowed) ?? ""
    }

    /// Decode a JWT and return the payload as a dictionary
    private func decodeJWT(_ jwt: String) -> [String: Any]? {
        let parts = jwt.split(separator: ".")
        guard parts.count >= 2 else { return nil }

        // JWT payload is the second part, base64url encoded
        var base64 = String(parts[1])
            .replacingOccurrences(of: "-", with: "+")
            .replacingOccurrences(of: "_", with: "/")

        // Pad to multiple of 4
        while base64.count % 4 != 0 {
            base64 += "="
        }

        guard let data = Data(base64Encoded: base64),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            return nil
        }

        return json
    }

    // MARK: - User Name Management

    /// Update the user's given name (stores locally, updates Firebase Auth, and syncs to backend profile)
    @MainActor
    func updateGivenName(_ fullName: String) async {
        let trimmedName = fullName.trimmingCharacters(in: .whitespaces)
        let nameParts = trimmedName.split(separator: " ", maxSplits: 1)
        let newGivenName = nameParts.first.map(String.init) ?? trimmedName
        let newFamilyName = nameParts.count > 1 ? String(nameParts[1]) : ""

        // Save locally
        givenName = newGivenName
        familyName = newFamilyName
        NSLog("OMI AUTH: Updated name locally - given: %@, family: %@", newGivenName, newFamilyName)

        // Try to update Firebase profile (best effort)
        // Skip during impersonation to avoid overwriting the target user's display name
        let isImpersonating = UserDefaults.standard.bool(forKey: .authIsImpersonating)
        if isImpersonating {
            NSLog("OMI AUTH: Skipping Firebase displayName update (impersonation mode)")
        } else if let user = Auth.auth().currentUser {
            do {
                let changeRequest = user.createProfileChangeRequest()
                changeRequest.displayName = trimmedName
                try await changeRequest.commitChanges()
                NSLog("OMI AUTH: Updated Firebase displayName to: %@", trimmedName)
            } catch {
                NSLog("OMI AUTH: Failed to update Firebase displayName (non-fatal): %@", error.localizedDescription)
            }
        }

        // Also save to backend profile (Firestore) so it persists across sign-in methods
        if !isImpersonating {
            do {
                try await APIClient.shared.updateUserProfile(name: trimmedName)
                NSLog("OMI AUTH: Updated backend profile name to: %@", trimmedName)
            } catch {
                NSLog("OMI AUTH: Failed to update backend profile name (non-fatal): %@", error.localizedDescription)
            }
        }
    }

    /// Try to get name from Firebase user (after OAuth sign-in)
    func getNameFromFirebase() -> String? {
        if let displayName = Auth.auth().currentUser?.displayName, !displayName.isEmpty {
            return displayName
        }
        return nil
    }

    /// Load name from Firebase if local name is empty
    func loadNameFromFirebaseIfNeeded() {
        if givenName.isEmpty, let firebaseName = getNameFromFirebase() {
            let nameParts = firebaseName.split(separator: " ", maxSplits: 1)
            givenName = nameParts.first.map(String.init) ?? firebaseName
            familyName = nameParts.count > 1 ? String(nameParts[1]) : ""
            NSLog("OMI AUTH: Loaded name from Firebase - given: %@, family: %@", givenName, familyName)
        }
    }

    /// Load name from backend profile (Firestore) first, then fall back to Firebase Auth.
    /// This handles cases like Apple Sign-In where Firebase Auth displayName may be empty
    /// but the user already has a name stored in Firestore from a previous sign-up.
    func loadNameFromBackendIfNeeded() {
        guard givenName.isEmpty else { return }
        Task {
            do {
                let profile = try await APIClient.shared.getUserProfile()
                if let name = profile.name, !name.trimmingCharacters(in: .whitespaces).isEmpty {
                    let nameParts = name.trimmingCharacters(in: .whitespaces).split(separator: " ", maxSplits: 1)
                    await MainActor.run {
                        givenName = nameParts.first.map(String.init) ?? name.trimmingCharacters(in: .whitespaces)
                        familyName = nameParts.count > 1 ? String(nameParts[1]) : ""
                        NSLog("OMI AUTH: Loaded name from backend profile - given: %@, family: %@", givenName, familyName)
                    }
                    return
                }
            } catch {
                NSLog("OMI AUTH: Failed to fetch backend profile for name (non-fatal): %@", error.localizedDescription)
            }
            // Fall back to Firebase Auth displayName
            await MainActor.run {
                loadNameFromFirebaseIfNeeded()
            }
        }
    }

    // MARK: - Token Storage

    private func saveTokens(idToken: String, refreshToken: String, expiresIn: Int, userId: String) throws {
        // Store expiry time (current time + expiresIn seconds, minus 5 min buffer)
        let expiryTime = Date().addingTimeInterval(TimeInterval(expiresIn - 300))
        let tokens = StoredAuthTokens(
            idToken: idToken,
            refreshToken: refreshToken,
            expiryTime: expiryTime.timeIntervalSince1970,
            tokenUserId: userId
        )
        if usesKeychainTokenStorage {
            if saveKeychainTokens(tokens) {
                clearUserDefaultsTokens()
            } else {
                clearUserDefaultsTokens()
                throw AuthError.keychainTokenStorageUnavailable
            }
        } else {
            UserDefaults.standard.set(idToken, forKey: .authIdToken)
            UserDefaults.standard.set(refreshToken, forKey: .authRefreshToken)
            UserDefaults.standard.set(expiryTime.timeIntervalSince1970, forKey: .authTokenExpiry)
            // Store the user ID that owns these tokens (for validation on retrieval)
            UserDefaults.standard.set(userId, forKey: .authTokenUserId)
        }
        invalidateStoredTokensCache()
        NSLog("OMI AUTH: Saved tokens for user %@, expires at %@", userId, expiryTime.description)
    }

    private func clearTokens() {
        DesktopKeychainStore.delete(service: authTokenKeychainService, account: authTokenKeychainAccount)
        clearUserDefaultsTokens()
        invalidateStoredTokensCache()
        NSLog("OMI AUTH: Cleared all tokens")
    }

    private func clearUserDefaultsTokens() {
        UserDefaults.standard.removeObject(forKey: .authIdToken)
        UserDefaults.standard.removeObject(forKey: .authRefreshToken)
        UserDefaults.standard.removeObject(forKey: .authTokenExpiry)
        UserDefaults.standard.removeObject(forKey: .authTokenUserId)
    }

    private var usesKeychainTokenStorage: Bool {
        !AppBuild.isNonProduction
    }

    private func saveKeychainTokens(_ tokens: StoredAuthTokens) -> Bool {
        do {
            let data = try JSONEncoder().encode(tokens)
            guard let payload = String(data: data, encoding: .utf8) else {
                log("AuthService: failed to encode Keychain token payload")
                return false
            }
            return DesktopKeychainStore.setString(
                payload,
                service: authTokenKeychainService,
                account: authTokenKeychainAccount
            )
        } catch {
            logError("AuthService: failed to encode Keychain token payload", error: error)
            return false
        }
    }

    private func loadKeychainTokens() -> StoredAuthTokens? {
        guard let payload = DesktopKeychainStore.string(
            service: authTokenKeychainService,
            account: authTokenKeychainAccount
        ) else {
            return nil
        }
        guard let data = payload.data(using: .utf8) else {
            return nil
        }
        do {
            return try JSONDecoder().decode(StoredAuthTokens.self, from: data)
        } catch {
            logError("AuthService: failed to decode Keychain token payload", error: error)
            DesktopKeychainStore.delete(service: authTokenKeychainService, account: authTokenKeychainAccount)
            return nil
        }
    }

    private func loadUserDefaultsTokens() -> StoredAuthTokens? {
        guard
            let idToken = UserDefaults.standard.string(forKey: .authIdToken),
            let refreshToken = UserDefaults.standard.string(forKey: .authRefreshToken),
            !idToken.isEmpty,
            !refreshToken.isEmpty
        else {
            return nil
        }
        let expiryTime = UserDefaults.standard.double(forKey: .authTokenExpiry)
        let tokenUserId = UserDefaults.standard.string(forKey: .authTokenUserId) ?? ""
        return StoredAuthTokens(
            idToken: idToken,
            refreshToken: refreshToken,
            expiryTime: expiryTime,
            tokenUserId: tokenUserId
        )
    }

    private func storedTokens() -> StoredAuthTokens? {
        if cachedStoredTokensLoaded {
            return cachedStoredTokens
        }

        let tokens: StoredAuthTokens?
        if usesKeychainTokenStorage {
            if let keychainTokens = loadKeychainTokens() {
                tokens = keychainTokens
            } else if let defaultsTokens = loadUserDefaultsTokens() {
                if saveKeychainTokens(defaultsTokens) {
                    clearUserDefaultsTokens()
                    log("AuthService: migrated production auth tokens from UserDefaults to Keychain")
                    tokens = defaultsTokens
                } else {
                    clearUserDefaultsTokens()
                    log("AuthService: failed to migrate production auth tokens from UserDefaults to Keychain")
                    tokens = nil
                }
            } else {
                tokens = nil
            }
        } else {
            tokens = loadUserDefaultsTokens()
        }

        cachedStoredTokens = tokens
        cachedStoredTokensLoaded = true
        return tokens
    }

    private var storedIdToken: String? {
        storedTokens()?.idToken
    }

    private var storedRefreshToken: String? {
        storedTokens()?.refreshToken
    }

    private var storedTokenUserId: String? {
        let userId = storedTokens()?.tokenUserId ?? ""
        return userId.isEmpty ? nil : userId
    }

    private var isTokenExpired: Bool {
        let expiryTime = storedTokens()?.expiryTime ?? 0
        guard expiryTime > 0 else { return true }
        return Date().timeIntervalSince1970 > expiryTime
    }

    // MARK: - Firebase REST API Token Exchange

    struct FirebaseTokenResult {
        let idToken: String
        let refreshToken: String
        let expiresIn: Int
        let localId: String
    }

    /// Exchange custom token for ID token using Firebase REST API
    private func exchangeCustomTokenForIdToken(customToken: String) async throws -> FirebaseTokenResult {
        let apiKey = try requireFirebaseApiKey()
        guard let url = URL(string: "https://identitytoolkit.googleapis.com/v1/accounts:signInWithCustomToken?key=\(apiKey)") else {
            throw AuthError.invalidURL
        }

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONSerialization.data(withJSONObject: [
            "token": customToken,
            "returnSecureToken": true
        ])

        let (data, response) = try await URLSession.shared.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse else {
            throw AuthError.invalidResponse
        }

        guard httpResponse.statusCode == 200 else {
            let errorBody = String(data: data, encoding: .utf8) ?? "unknown"
            NSLog("OMI AUTH: Firebase REST API error: %@", errorBody)
            throw AuthError.tokenExchangeFailed(httpResponse.statusCode)
        }

        guard let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let idToken = json["idToken"] as? String,
              let refreshToken = json["refreshToken"] as? String else {
            NSLog("OMI AUTH: Failed to parse Firebase response: %@", String(data: data, encoding: .utf8) ?? "nil")
            throw AuthError.invalidResponse
        }

        // expiresIn can be String or Int
        let expiresIn: Int
        if let expiresInStr = json["expiresIn"] as? String {
            expiresIn = Int(expiresInStr) ?? 3600
        } else if let expiresInInt = json["expiresIn"] as? Int {
            expiresIn = expiresInInt
        } else {
            expiresIn = 3600
        }

        // localId might be missing from REST API response - extract from JWT if needed
        var localId = json["localId"] as? String ?? ""
        if localId.isEmpty {
            // Extract user_id from the JWT token payload
            if let payload = decodeJWT(idToken),
               let userId = payload["user_id"] as? String ?? payload["sub"] as? String {
                localId = userId
                NSLog("OMI AUTH: Extracted user_id from JWT: %@", localId)
            }
        }

        return FirebaseTokenResult(
            idToken: idToken,
            refreshToken: refreshToken,
            expiresIn: expiresIn,
            localId: localId
        )
    }

    /// Refresh the ID token using the refresh token
    private func refreshIdToken() async throws -> String {
        guard let refreshToken = storedRefreshToken else {
            throw AuthError.notSignedIn
        }

        let apiKey = try requireFirebaseApiKey()
        guard let url = URL(string: "https://securetoken.googleapis.com/v1/token?key=\(apiKey)") else {
            throw AuthError.invalidURL
        }

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/x-www-form-urlencoded", forHTTPHeaderField: "Content-Type")
        request.httpBody = "grant_type=refresh_token&refresh_token=\(refreshToken)".data(using: .utf8)

        let (data, response) = try await URLSession.shared.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse else {
            throw AuthError.invalidResponse
        }

        guard httpResponse.statusCode == 200 else {
            let errorBody = String(data: data, encoding: .utf8) ?? "unknown"
            NSLog("OMI AUTH: Token refresh error (HTTP %d): %@", httpResponse.statusCode, errorBody)
            // Only clear tokens for definitive auth failures (invalid/revoked refresh token).
            // Transient errors (network issues, 500s) should not destroy the session.
            let isDefinitiveAuthFailure = errorBody.contains("TOKEN_EXPIRED")
                || errorBody.contains("INVALID_REFRESH_TOKEN")
                || errorBody.contains("USER_NOT_FOUND")
                || errorBody.contains("USER_DISABLED")
                || httpResponse.statusCode == 400
            if isDefinitiveAuthFailure {
                NSLog("OMI AUTH: Definitive auth failure - clearing tokens and session")
                clearTokens()
                // Also clear auth state so the UI shows sign-in instead of a ghost session
                // where auth_isSignedIn=true but no valid tokens exist.
                isSignedIn = false
                saveAuthState(isSignedIn: false, email: nil, userId: nil)
                throw AuthError.notSignedIn
            }
            throw AuthError.tokenExchangeFailed(httpResponse.statusCode)
        }

        guard let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let newIdToken = json["id_token"] as? String,
              let newRefreshToken = json["refresh_token"] as? String,
              let expiresIn = json["expires_in"] as? String else {
            throw AuthError.invalidResponse
        }

        // Get user ID from response (Firebase returns it as "user_id")
        // Fall back to existing stored token user ID if not in response
        let userId = (json["user_id"] as? String) ?? storedTokenUserId ?? ""

        // Save new tokens with user ID
        try saveTokens(idToken: newIdToken, refreshToken: newRefreshToken, expiresIn: Int(expiresIn) ?? 3600, userId: userId)
        NSLog("OMI AUTH: Refreshed ID token successfully for user %@", userId)

        return newIdToken
    }

    // MARK: - Get ID Token (for API calls)

    func getIdToken(forceRefresh: Bool = false) async throws -> String {
        // Get the expected user ID (the currently signed-in user)
        let expectedUserId = UserDefaults.standard.string(forKey: .authUserId)

        // First try: Use stored token if valid AND belongs to the current user
        if !forceRefresh, let token = storedIdToken, !isTokenExpired {
            // Validate token belongs to current user to prevent using stale tokens after account switch
            // Allow tokens without userId (backward compatibility with pre-c052b0b tokens)
            if let tokenUserId = storedTokenUserId {
                if expectedUserId == nil {
                    // expectedUserId missing (migration gap, crash recovery) - trust the token
                    // and backfill the userId so future calls don't hit this path
                    NSLog("OMI AUTH: expectedUserId is nil but token has userId %@ - backfilling", tokenUserId)
                    UserDefaults.standard.set(tokenUserId, forKey: .authUserId)
                    return token
                } else if tokenUserId == expectedUserId {
                    return token
                } else {
                    NSLog("OMI AUTH: Stored token user mismatch (token: %@, expected: %@) - clearing stale token",
                          tokenUserId, expectedUserId ?? "nil")
                    clearTokens()
                }
            } else {
                // Old token without userId - allow it (backward compatibility)
                NSLog("OMI AUTH: Using legacy token without userId")
                return token
            }
        }

        // Second try: Refresh using stored refresh token
        // Allow refresh when expectedUserId is nil (token was saved by valid sign-in)
        var refreshFailure: Error?
        if let _ = storedRefreshToken {
            let tokenUserId = storedTokenUserId
            let canRefresh = tokenUserId == nil || expectedUserId == nil || tokenUserId == expectedUserId
            if canRefresh {
                do {
                    return try await refreshIdToken()
                } catch {
                    refreshFailure = error
                    NSLog("OMI AUTH: Token refresh failed: %@", error.localizedDescription)
                }
            }
        }

        // Third try: Use Firebase SDK (only if user matches expected user)
        // This prevents returning a stale user's token during sign-out race conditions
        if let user = Auth.auth().currentUser {
            if expectedUserId == nil || user.uid == expectedUserId {
                if expectedUserId == nil {
                    // Backfill the missing userId
                    NSLog("OMI AUTH: expectedUserId is nil, backfilling from Firebase SDK user %@", user.uid)
                    UserDefaults.standard.set(user.uid, forKey: .authUserId)
                }
                let tokenResult = try await user.getIDTokenResult(forcingRefresh: forceRefresh)
                return tokenResult.token
            } else {
                NSLog("OMI AUTH: Firebase SDK user mismatch (firebase: %@, expected: %@) - not using",
                      user.uid, expectedUserId ?? "nil")
            }
        }

        if let refreshFailure {
            throw refreshFailure
        }

        throw AuthError.notSignedIn
    }

    func getAuthHeader(forceRefresh: Bool = false) async throws -> String {
        let token = try await getIdToken(forceRefresh: forceRefresh)
        return "Bearer \(token)"
    }

    // MARK: - Fetch User Conversations

    /// Fetches and logs user conversations (called after sign-in or on startup)
    func fetchConversations() {
        Task {
            do {
                log("Fetching user conversations...")
                let conversations = try await APIClient.shared.getConversations(limit: 10)
                log("Fetched \(conversations.count) conversations")

                for (index, conversation) in conversations.prefix(5).enumerated() {
                    log("[\(index + 1)] \(conversation.structured.emoji) \(conversation.title) (\(conversation.formattedDuration))")
                    if !conversation.overview.isEmpty {
                        let preview = String(conversation.overview.prefix(100))
                        log("    Summary: \(preview)\(conversation.overview.count > 100 ? "..." : "")")
                    }
                }

                if conversations.count > 5 {
                    log("... and \(conversations.count - 5) more conversations")
                }
            } catch {
                logError("Failed to fetch conversations", error: error)
            }
        }
    }

    // MARK: - Sign Out

    func signOut() throws {
        // Track sign out and reset analytics
        AnalyticsManager.shared.signedOut()
        AnalyticsManager.shared.reset()

        // Clear Sentry user context (skip in dev builds)
        if !AnalyticsManager.isDevBuild {
            SentrySDK.setUser(nil)
        }

        try Auth.auth().signOut()
        isSignedIn = false
        CredentialHealthManager.shared.reset()
        APIKeyService.shared.clear()
        // Clear saved auth state and tokens
        saveAuthState(isSignedIn: false, email: nil, userId: nil)
        clearTokens()

        // Stop background services that make API calls before clearing caches
        Task {
            await AgentSyncService.shared.stop()
            await FloatingBarUsageLimiter.shared.reset()
        }

        // Stop trial polling and reset banner state for this user session
        if let state = AppState.current {
            state.stopTrialMetadataRefresh()
            state.trialMetadata = nil
            state.isPaywalled = false
        }
        TrialBannerService.shared.stop()

        // Close database and invalidate all storage caches so the next sign-in
        // opens a fresh per-user database.
        // Capture the current configureGeneration so closeIfStale() can detect if
        // a new sign-in session has already called configure() by the time this runs.
        let closeGeneration = RewindDatabase.configureGeneration
        Task {
            await RewindDatabase.shared.closeIfStale(generation: closeGeneration)
            await RewindIndexer.shared.reset()
            await RewindStorage.shared.reset()
            await TranscriptionStorage.shared.invalidateCache()
            await MemoryStorage.shared.invalidateCache()
            await ActionItemStorage.shared.invalidateCache()
            await ProactiveStorage.shared.invalidateCache()
            await NoteStorage.shared.invalidateCache()
            await AIUserProfileService.shared.invalidateCache()
        }

        // Notify observers (DesktopHomeView) to reset @AppStorage-backed properties directly.
        // Using removeObject() on @AppStorage properties doesn't work because the cached value
        // in AppState (an ObservableObject, not a View) gets written back immediately.
        NotificationCenter.default.post(name: .userDidSignOut, object: nil)

        // Clear non-@AppStorage onboarding keys via UserDefaults (these work fine).
        UserDefaults.standard.removeObject(forKey: "onboardingStep")
        UserDefaults.standard.removeObject(forKey: "hasTriggeredNotification")
        UserDefaults.standard.removeObject(forKey: "hasTriggeredAutomation")
        UserDefaults.standard.removeObject(forKey: "hasTriggeredScreenRecording")
        UserDefaults.standard.removeObject(forKey: "hasTriggeredMicrophone")
        UserDefaults.standard.removeObject(forKey: "hasTriggeredSystemAudio")
        UserDefaults.standard.removeObject(forKey: "onboardingChatMessages")
        UserDefaults.standard.removeObject(forKey: "onboardingACPSessionId")
        UserDefaults.standard.removeObject(forKey: "onboardingJustCompleted")

        // screenAnalysisEnabled: Don't removeObject here — SettingsSyncManager overwrites
        // it from the server within ~200ms of sign-in. Instead, onboarding force-starts
        // monitoring regardless of this setting.
        // transcriptionEnabled: removeObject works since nothing writes it back.
        UserDefaults.standard.removeObject(forKey: "transcriptionEnabled")

        NSLog("OMI AUTH: Signed out and cleared saved state + onboarding")
    }

    // MARK: - Helper Methods

    private func generateOAuthFlowID() -> String {
        var bytes = [UInt8](repeating: 0, count: 32)
        _ = SecRandomCopyBytes(kSecRandomDefault, bytes.count, &bytes)
        return Data(bytes).base64EncodedString()
            .replacingOccurrences(of: "+", with: "-")
            .replacingOccurrences(of: "/", with: "_")
            .replacingOccurrences(of: "=", with: "")
    }

    private func generateState(flowId: String) -> String {
        // Encode source bundle in state so callbacks can be routed back to the
        // originating app, even when multiple dev builds share URL schemes.
        return "\(flowId)|\(currentBundleIdentifier)"
    }

    private func generateCodeVerifier(length: Int = 64) -> String {
        var bytes = [UInt8](repeating: 0, count: length)
        _ = SecRandomCopyBytes(kSecRandomDefault, bytes.count, &bytes)
        let charset: [Character] = Array("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~")
        return String(bytes.map { charset[Int($0) % charset.count] })
    }

    private func makeCodeChallenge(for verifier: String) -> String {
        let digest = SHA256.hash(data: Data(verifier.utf8))
        return Data(digest).base64EncodedString()
            .replacingOccurrences(of: "+", with: "-")
            .replacingOccurrences(of: "/", with: "_")
            .replacingOccurrences(of: "=", with: "")
    }

    private func targetBundleIdentifier(from state: String) -> String? {
        let parts = state.split(separator: "|", maxSplits: 1).map(String.init)
        guard parts.count == 2 else { return nil }
        let bundleId = parts[1].trimmingCharacters(in: .whitespacesAndNewlines)
        return bundleId.isEmpty ? nil : bundleId
    }

    private func authFlowId(from state: String) -> String? {
        let flowId = state.split(separator: "|", maxSplits: 1).first.map(String.init)?
            .trimmingCharacters(in: .whitespacesAndNewlines)
        return flowId?.isEmpty == false ? flowId : nil
    }

    private func forwardOAuthCallback(url: URL, toBundleId bundleId: String, authFlowId: String?) {
        guard let appURL = NSWorkspace.shared.urlForApplication(withBundleIdentifier: bundleId) else {
            NSLog("OMI AUTH: Unable to forward callback. Bundle %@ not found.", bundleId)
            trackAuthFlowEvent(
                "Auth Callback Forward Failed",
                stage: "callback_forwarded",
                provider: pendingOAuthFlow?.provider ?? "unknown",
                authFlowId: authFlowId,
                failureClass: "target_bundle_not_found",
                extraProperties: ["target_bundle_id": bundleId]
            )
            return
        }

        let config = NSWorkspace.OpenConfiguration()
        config.activates = true

        NSWorkspace.shared.open([url], withApplicationAt: appURL, configuration: config) { _, error in
            if let error {
                NSLog("OMI AUTH: Failed to forward callback to %@: %@", bundleId, error.localizedDescription)
                Task { @MainActor in
                    self.trackAuthFlowEvent(
                        "Auth Callback Forward Failed",
                        stage: "callback_forwarded",
                        provider: self.pendingOAuthFlow?.provider ?? "unknown",
                        authFlowId: authFlowId,
                        failureClass: "workspace_open_failed",
                        error: error.localizedDescription,
                        extraProperties: ["target_bundle_id": bundleId]
                    )
                }
            } else {
                NSLog("OMI AUTH: Forwarded callback to %@", bundleId)
                Task { @MainActor in
                    self.trackAuthFlowEvent(
                        "Auth Callback Forwarded",
                        stage: "callback_forwarded",
                        provider: self.pendingOAuthFlow?.provider ?? "unknown",
                        authFlowId: authFlowId,
                        extraProperties: ["target_bundle_id": bundleId]
                    )
                }
            }
        }
    }

    // MARK: - Native Apple Sign In Helpers

    /// Show the native Apple Sign In dialog and return the credential
    private func performAppleSignIn(hashedNonce: String) async throws -> ASAuthorizationAppleIDCredential {
        try await withCheckedThrowingContinuation { continuation in
            let provider = ASAuthorizationAppleIDProvider()
            let request = provider.createRequest()
            request.requestedScopes = [.fullName, .email]
            request.nonce = hashedNonce

            let controller = ASAuthorizationController(authorizationRequests: [request])
            let delegate = AppleSignInDelegate(continuation: continuation)
            self.appleSignInDelegate = delegate  // Keep delegate alive
            controller.delegate = delegate
            controller.presentationContextProvider = delegate
            controller.performRequests()
        }
    }

    /// Sign in with Firebase using an Apple identity token via REST API
    /// This bypasses the backend entirely - Firebase verifies the Apple JWT directly
    private func signInWithAppleIdentityToken(identityToken: String, nonce: String) async throws -> FirebaseTokenResult {
        let apiKey = try requireFirebaseApiKey()
        guard let url = URL(string: "https://identitytoolkit.googleapis.com/v1/accounts:signInWithIdp?key=\(apiKey)") else {
            throw AuthError.invalidURL
        }

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")

        let postBody = "id_token=\(identityToken)&providerId=apple.com&nonce=\(nonce)"
        let body: [String: Any] = [
            "postBody": postBody,
            "requestUri": "http://localhost",
            "returnIdpCredential": true,
            "returnSecureToken": true
        ]

        request.httpBody = try JSONSerialization.data(withJSONObject: body)

        let (data, response) = try await URLSession.shared.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse else {
            throw AuthError.invalidResponse
        }

        guard httpResponse.statusCode == 200 else {
            let errorBody = String(data: data, encoding: .utf8) ?? "unknown"
            NSLog("OMI AUTH: Firebase signInWithIdp error: %@", errorBody)
            throw AuthError.tokenExchangeFailed(httpResponse.statusCode)
        }

        guard let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let idToken = json["idToken"] as? String,
              let refreshToken = json["refreshToken"] as? String else {
            NSLog("OMI AUTH: Failed to parse Firebase signInWithIdp response")
            throw AuthError.invalidResponse
        }

        let expiresIn: Int
        if let expiresInStr = json["expiresIn"] as? String {
            expiresIn = Int(expiresInStr) ?? 3600
        } else if let expiresInInt = json["expiresIn"] as? Int {
            expiresIn = expiresInInt
        } else {
            expiresIn = 3600
        }

        var localId = json["localId"] as? String ?? ""
        if localId.isEmpty {
            if let payload = decodeJWT(idToken),
               let userId = payload["user_id"] as? String ?? payload["sub"] as? String {
                localId = userId
            }
        }

        // Get email from response if not already set
        if AuthState.shared.userEmail == nil {
            if let email = json["email"] as? String {
                AuthState.shared.userEmail = email
            }
        }

        return FirebaseTokenResult(
            idToken: idToken,
            refreshToken: refreshToken,
            expiresIn: expiresIn,
            localId: localId
        )
    }

    /// Generate a random nonce string for Apple Sign In
    private func generateNonce(length: Int = 32) -> String {
        var bytes = [UInt8](repeating: 0, count: length)
        _ = SecRandomCopyBytes(kSecRandomDefault, bytes.count, &bytes)
        let charset: [Character] = Array("0123456789ABCDEFGHIJKLMNOPQRSTUVXYZabcdefghijklmnopqrstuvwxyz-._")
        return String(bytes.map { charset[Int($0) % charset.count] })
    }

    /// SHA-256 hash of a string (for Apple Sign In nonce)
    private func sha256(_ input: String) -> String {
        let data = Data(input.utf8)
        let hash = SHA256.hash(data: data)
        return hash.compactMap { String(format: "%02x", $0) }.joined()
    }
}

// MARK: - Apple Sign In Delegate

private class AppleSignInDelegate: NSObject, ASAuthorizationControllerDelegate, ASAuthorizationControllerPresentationContextProviding {
    private var continuation: CheckedContinuation<ASAuthorizationAppleIDCredential, Error>?

    init(continuation: CheckedContinuation<ASAuthorizationAppleIDCredential, Error>) {
        self.continuation = continuation
        super.init()
    }

    func authorizationController(controller: ASAuthorizationController, didCompleteWithAuthorization authorization: ASAuthorization) {
        guard let credential = authorization.credential as? ASAuthorizationAppleIDCredential else {
            continuation?.resume(throwing: AuthError.invalidCredential)
            continuation = nil
            return
        }
        continuation?.resume(returning: credential)
        continuation = nil
    }

    func authorizationController(controller: ASAuthorizationController, didCompleteWithError error: Error) {
        continuation?.resume(throwing: error)
        continuation = nil
    }

    func presentationAnchor(for controller: ASAuthorizationController) -> ASPresentationAnchor {
        return NSApp.keyWindow ?? NSApp.windows.first ?? NSWindow()
    }
}

// MARK: - Auth Errors

enum AuthError: LocalizedError {
    case invalidCredential
    case invalidNonce
    case missingToken
    case missingFirebaseApiKey
    case notSignedIn
    case invalidURL
    case stateMismatch
    case timeout
    case invalidCallback
    case oauthError(String)
    case missingCodeOrState
    case invalidResponse
    case tokenExchangeFailed(Int)
    case missingCustomToken
    case keychainTokenStorageUnavailable
    case cancelled

    var errorDescription: String? {
        switch self {
        case .invalidCredential:
            return "Invalid Apple credential"
        case .invalidNonce:
            return "Invalid nonce - please try again"
        case .missingToken:
            return "Missing identity token from Apple"
        case .missingFirebaseApiKey:
            return "Sign-in is not ready yet (Firebase API key unavailable). Please check your connection and try again in a moment."
        case .notSignedIn:
            return "User is not signed in"
        case .invalidURL:
            return "Invalid authentication URL"
        case .stateMismatch:
            return "Security state mismatch - please try again"
        case .timeout:
            return "Authentication timed out - please try again"
        case .invalidCallback:
            return "Invalid authentication callback"
        case .oauthError(let error):
            return "Authentication error: \(error)"
        case .missingCodeOrState:
            return "Missing authentication code"
        case .invalidResponse:
            return "Invalid server response"
        case .tokenExchangeFailed(let code):
            return "Token exchange failed with status \(code)"
        case .missingCustomToken:
            return "Server did not return authentication token"
        case .keychainTokenStorageUnavailable:
            return "Could not securely store sign-in tokens. Please try again."
        case .cancelled:
            return "Sign in cancelled"
        }
    }
}
