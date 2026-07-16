import AppKit
import AuthenticationServices
import CryptoKit
import Darwin
@preconcurrency import FirebaseAuth
import FirebaseCore
import Foundation
import OmiSupport
import Sentry

extension Notification.Name {
  /// Posted by AuthService.signOut() so views can reset @AppStorage-backed properties directly.
  static let userDidSignOut = Notification.Name("com.omi.desktop.userDidSignOut")
  /// Posted whenever the signed-in user's name becomes known (Apple first-auth
  /// capture, or a later backend/Firebase fetch). `givenName`/`familyName` are
  /// plain UserDefaults, so onboarding can't observe them directly — it listens
  /// for this and re-reads `AuthService.shared.givenName`.
  static let authNameDidUpdate = Notification.Name("com.omi.desktop.authNameDidUpdate")
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
          let request = String(bytes: buffer.prefix(bytesRead), encoding: .utf8)
        else {
          self.sendResponse(clientFD, page: .invalid)
          continue
        }

        switch self.parseCallbackRequest(request) {
        case .success(let code, let state):
          self.sendResponse(clientFD, page: .success)
          self.finish(.success((code: code, state: state)))
          return
        case .providerError(let error):
          self.sendResponse(clientFD, page: .failure)
          self.finish(.failure(AuthError.oauthError(error)))
          return
        case .ignore:
          self.sendResponse(clientFD, page: .invalid)
          continue
        }
      }
    }
  }

  enum CallbackPage {
    case success
    case failure
    case invalid

    var httpStatus: String {
      switch self {
      case .success: return "200 OK"
      case .failure, .invalid: return "400 Bad Request"
      }
    }

    var documentTitle: String {
      switch self {
      case .success: return "Signed in - Omi"
      case .failure, .invalid: return "Authentication failed - Omi"
      }
    }

    var heading: String {
      switch self {
      case .success: return "You're signed in"
      case .failure: return "Authentication failed"
      case .invalid: return "Invalid callback"
      }
    }

    var message: String {
      switch self {
      case .success: return "You can close this tab and return to Omi."
      case .failure: return "You can close this tab and try again in the app."
      case .invalid: return "This authentication callback was invalid. You can close this tab."
      }
    }

    var icon: String {
      switch self {
      case .success: return "✓"
      case .failure, .invalid: return "!"
      }
    }

    var iconBackground: String {
      switch self {
      case .success: return "#111111"
      case .failure, .invalid: return "#d32f2f"
      }
    }
  }

  /// Branded HTML body served on the local OAuth loopback callback.
  /// Kept pure/static so unit tests can assert markup without opening a socket.
  static func responseHTML(for page: CallbackPage) -> String {
    """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>\(page.documentTitle)</title>
        <style>
            body {
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                min-height: 100vh;
                margin: 0;
                background-color: #f7f7f7;
                color: #333;
            }
            .card {
                background-color: white;
                border-radius: 8px;
                box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
                padding: 48px 32px;
                text-align: center;
                max-width: 400px;
            }
            .icon {
                width: 56px;
                height: 56px;
                margin: 0 auto 16px;
                border-radius: 50%;
                background-color: \(page.iconBackground);
                color: white;
                font-size: 28px;
                font-weight: 600;
                line-height: 56px;
            }
            h1 {
                font-size: 24px;
                font-weight: 600;
                margin: 0 0 12px 0;
            }
            p {
                font-size: 16px;
                color: #555;
                margin: 0;
                line-height: 1.5;
            }
        </style>
    </head>
    <body>
        <div class="card">
            <div class="icon">\(page.icon)</div>
            <h1>\(page.heading)</h1>
            <p>\(page.message)</p>
        </div>
        <script>
            setTimeout(function () {
                try { window.close(); } catch (e) {}
            }, 1200);
        </script>
    </body>
    </html>
    """
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
      components.path == "/callback"
    else {
      return .ignore
    }

    let queryItems = components.queryItems ?? []
    guard let state = queryItems.first(where: { $0.name == "state" })?.value,
      state == expectedState
    else {
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

  private func sendResponse(_ clientFD: Int32, page: CallbackPage) {
    let body = Self.responseHTML(for: page)
    let response = """
      HTTP/1.1 \(page.httpStatus)\r
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
    set { authState.transition(to: newValue ? .authenticated : .signedOut) }
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
      let scheme = schemes.first
    {
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
  //
  // Keychain service is team+bundle scoped so local Dev / named-bundle builds
  // cannot poison each other or notarized Beta/Prod (login-keychain password
  // dialog). See DesktopKeychainStore.scopedService.
  private let authTokenKeychainAccount = "firebase-rest-tokens"
  private var authTokenKeychainService: String {
    DesktopKeychainStore.scopedService(DesktopKeychainStore.legacyAuthTokenService)
  }

  private struct StoredAuthTokens: Codable, Equatable {
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

  struct TokenStorageHooks {
    var usesKeychainTokenStorage: () -> Bool
    var allowsUserDefaultsFallback: () -> Bool
    var readKeychainString: (_ service: String, _ account: String) -> String?
    var writeKeychainString: (_ value: String, _ service: String, _ account: String) -> Bool
    var deleteKeychainString: (_ service: String, _ account: String) -> Void
    var recordsFallbackTelemetry: Bool

    // Security invariant: new auth tokens live in the Keychain on EVERY build,
    // including Sparkle beta. Plaintext UserDefaults fallback is disabled for new
    // sign-ins. The read path remains only for transactional migration of older
    // installs: keep that already-existing copy until Keychain read-back plus a
    // forced refresh commit the new store.
    nonisolated(unsafe) static let live = TokenStorageHooks(
      usesKeychainTokenStorage: { true },
      allowsUserDefaultsFallback: { false },
      readKeychainString: { service, account in
        // Only the team+bundle scoped service. Never query the unscoped
        // legacy `com.omi.desktop.firebase-rest-session` item — a foreign
        // ACL on that name is what triggers the login-keychain password
        // dialog. Pre-scoping installs recover via UserDefaults migration.
        DesktopKeychainStore.string(service: service, account: account)
      },
      writeKeychainString: { value, service, account in
        DesktopKeychainStore.setString(value, service: service, account: account)
      },
      deleteKeychainString: { service, account in
        // Only delete the scoped item. Touching the legacy unscoped name can
        // itself prompt when the ACL belongs to another signing team.
        DesktopKeychainStore.delete(service: service, account: account)
      },
      recordsFallbackTelemetry: true
    )
  }

  var tokenStorageHooks = TokenStorageHooks.live

  struct TokenRefreshHooks {
    var dataForRequest: ((URLRequest) async throws -> (Data, URLResponse))?

    nonisolated(unsafe) static let live = TokenRefreshHooks(dataForRequest: nil)
  }

  var tokenRefreshHooks = TokenRefreshHooks.live

  // Firebase Web API key — fetched from backend via APIKeyService, set as env var.
  // No hardcoded fallback — if the key isn't available, auth operations will fail
  // with a clear error instead of silently using a potentially wrong key.
  private var firebaseApiKey: String {
    if let envKey = getenv("FIREBASE_API_KEY"), let key = String(validatingCString: envKey), !key.isEmpty {
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

  /// Notify observers (onboarding) that the user's name is now known. Posted on
  /// the main queue since it drives UI. Observers re-read `givenName` themselves.
  func postNameDidUpdate() {
    DispatchQueue.main.async {
      NotificationCenter.default.post(name: .authNameDidUpdate, object: nil)
    }
  }

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

  private let sessionCoordinator = AuthSessionCoordinator.shared
  private let sessionAttemptFence = AuthSessionAttemptFence()

  init() {
    // Initialize without super
  }

  /// Start a new authoritative auth operation. Async completions from every
  /// older restore/sign-in/refresh/invalidation/sign-out attempt become
  /// incapable of mutating credentials or owner state immediately.
  @discardableResult
  func beginSessionAttempt() -> AuthSessionAttempt {
    sessionAttemptFence.begin()
  }

  func currentSessionAttempt() -> AuthSessionAttempt {
    sessionAttemptFence.current()
  }

  func isSessionAttemptCurrent(_ attempt: AuthSessionAttempt) -> Bool {
    sessionAttemptFence.isCurrent(attempt)
  }

  private func discardStaleFirebaseUserIfNeeded(_ userID: String) {
    guard FirebaseApp.app() != nil,
      Auth.auth().currentUser?.uid == userID
    else {
      return
    }
    try? Auth.auth().signOut()
  }

  // MARK: - Session invalidation (light — not nuclear signOut)

  /// Clears tokens and signed-in UI state without onboarding wipe, capture stop,
  /// or storage cache teardown. Use for expired/revoked credentials.
  func invalidateSession(reason: AuthSessionCoordinator.InvalidateReason) async {
    await sessionCoordinator.invalidateSession(reason: reason, auth: self)
  }

  /// Internal hook for `AuthSessionCoordinator` — not a user-facing sign-out.
  func performLightSessionInvalidation() async -> Bool {
    let attempt = beginSessionAttempt()
    // Also clear the Firebase SDK session so that restoreAuthState() and the
    // auth-state listener do not re-create the ghost session on the next
    // launch. Unlike signOut(), this does NOT tear down storage caches or
    // stop background services — it only clears the Firebase SDK user.
    // Guard: tests/local harnesses can exercise invalidation without
    // FirebaseApp.configure(); Auth.auth() traps fatally if called before
    // Firebase is configured.
    if FirebaseApp.app() != nil {
      try? Auth.auth().signOut()
    }
    return await commitSignedOutSession(attempt: attempt, phase: .needsReauth)
  }

  // MARK: - Configuration (call after FirebaseApp.configure())

  func configure() async {
    guard !isConfigured else { return }
    isConfigured = true
    let attempt = beginSessionAttempt()
    await restoreAuthState(attempt: attempt)
    setupAuthStateListener()

    // Timeout: if auth isn't restored within 5 seconds, stop showing loading
    DispatchQueue.main.asyncAfter(deadline: .now() + 5.0) { [weak self] in
      guard let self, self.isSessionAttemptCurrent(attempt) else { return }
      if AuthState.shared.isRestoringAuth {
        NSLog("OMI AUTH: Auth restore timed out after 5s, entering recoverable state")
        AuthState.shared.transition(to: .recoveryRequired)
      }
    }
  }

  func bootstrapLocalHarnessAuthIfNeeded() async {
    let attempt = beginSessionAttempt()
    guard let email = DesktopLocalProfile.selectedEmail,
      let password = DesktopLocalProfile.selectedPassword,
      let selectedUser = DesktopLocalProfile.selectedUser
    else {
      log("OMI AUTH LOCAL: missing selected local auth user env; staying signed out")
      return
    }

    if let savedEmail = UserDefaults.standard.string(forKey: .authUserEmail),
      !savedEmail.isEmpty, savedEmail != email
    {
      guard await clearPersistedAuthState(attempt: attempt) else { return }
      _ = sessionAttemptFence.commitIfCurrent(attempt) {
        clearTokens()
      }
      log("OMI AUTH LOCAL: cleared stale persisted auth for email=\(savedEmail)")
    }

    do {
      let tokens = try await signInWithPasswordViaAuthEmulator(email: email, password: password)
      guard
        try await commitSignedInSession(
          tokens: tokens,
          email: email,
          attempt: attempt)
      else {
        return
      }
      if let display = DesktopLocalProfile.selectedDisplayName, !display.isEmpty {
        let pieces = display.split(separator: " ", maxSplits: 1).map(String.init)
        givenName = pieces.first ?? ""
        familyName = pieces.count > 1 ? pieces[1] : ""
      }
      log("OMI AUTH LOCAL: signed in via emulator REST as \(email) uid=\(tokens.localId) user=\(selectedUser)")
    } catch {
      logError("OMI AUTH LOCAL: sign-in failed for \(email)", error: error)
      self.error = "Local Auth emulator sign-in failed for \(email): \(error.localizedDescription)"
      AuthState.shared.transition(to: .recoveryRequired)
    }
  }

  private func signInWithPasswordViaAuthEmulator(email: String, password: String) async throws -> FirebaseTokenResult {
    guard let hostPort = DesktopLocalProfile.authEmulatorHost else {
      throw AuthError.invalidURL
    }
    let apiKey = try requireFirebaseApiKey()
    guard
      let url = URL(
        string: "http://\(hostPort)/identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key=\(apiKey)"
      )
    else {
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

    return try Self.decodeFirebaseTokenResult(from: data, requireLocalId: true)
  }

  private func selectedLocalUserId(from idToken: String) -> String? {
    Self.localUserId(fromIDToken: idToken)
  }

  // MARK: - Auth Persistence (UserDefaults for dev builds)

  @discardableResult
  private func saveAuthState(
    isSignedIn: Bool,
    email: String?,
    userId: String?,
    attempt: AuthSessionAttempt
  ) async -> Bool {
    let attemptFence = sessionAttemptFence
    let committed = await RuntimeOwnerIdentity.performEffectiveOwnerTransition(
      plannedNextOwner: { _, previousOwner in
        attemptFence.isCurrent(attempt) ? userId : previousOwner
      }
    ) { defaults in
      attemptFence.commitIfCurrent(attempt) {
        defaults.set(isSignedIn, forKey: .authIsSignedIn)
        defaults.set(email, forKey: .authUserEmail)
        defaults.set(userId, forKey: .authUserId)
        defaults.synchronize()  // Force flush before process can be killed
        return true
      } ?? false
    }
    guard committed, sessionAttemptFence.isCurrent(attempt) else { return false }
    NSLog("OMI AUTH: Saved auth state - signedIn: %@, email: %@", isSignedIn ? "true" : "false", email ?? "nil")
    return true
  }

  @discardableResult
  private func clearPersistedAuthState(attempt: AuthSessionAttempt) async -> Bool {
    let attemptFence = sessionAttemptFence
    let committed = await RuntimeOwnerIdentity.performEffectiveOwnerTransition(
      plannedNextOwner: { _, previousOwner in
        attemptFence.isCurrent(attempt) ? nil : previousOwner
      }
    ) { defaults in
      attemptFence.commitIfCurrent(attempt) {
        defaults.removeObject(forKey: .authIsSignedIn)
        defaults.removeObject(forKey: .authUserEmail)
        defaults.removeObject(forKey: .authUserId)
        defaults.removeObject(forKey: .authIdToken)
        defaults.removeObject(forKey: .authRefreshToken)
        defaults.removeObject(forKey: .authTokenExpiry)
        defaults.removeObject(forKey: .authTokenUserId)
        return true
      } ?? false
    }
    return committed && sessionAttemptFence.isCurrent(attempt)
  }

  /// The only production path for changing the persisted authenticated uid
  /// outside the larger save/clear auth-state transactions above.
  @discardableResult
  private func persistAuthenticatedOwner(
    _ userId: String?,
    attempt: AuthSessionAttempt
  ) async -> Bool {
    let attemptFence = sessionAttemptFence
    let committed = await RuntimeOwnerIdentity.performEffectiveOwnerTransition(
      plannedNextOwner: { _, previousOwner in
        attemptFence.isCurrent(attempt) ? userId : previousOwner
      }
    ) { defaults in
      attemptFence.commitIfCurrent(attempt) {
        if let userId {
          defaults.set(userId, forKey: .authUserId)
        } else {
          defaults.removeObject(forKey: .authUserId)
        }
        return true
      } ?? false
    }
    return committed && sessionAttemptFence.isCurrent(attempt)
  }

  /// Commit credentials and their owner as one generation-owned auth result.
  /// Token persistence is synchronous and generation-locked; the awaited owner
  /// transition re-checks the same attempt before changing defaults. A newer
  /// operation therefore wins even if this task resumes later.
  @discardableResult
  func commitSignedInSession(
    tokens: FirebaseTokenResult,
    email: String?,
    attempt: AuthSessionAttempt
  ) async throws -> Bool {
    let attemptFence = sessionAttemptFence
    // Credentials and their durable owner are one publication boundary.
    // Writing B's token before revoking A left a window where an admitted A
    // token read observed `tokenUserId == B` with `authUserId == A` and
    // correctly treated the new credential as stale by deleting it. Reserve
    // the owner fence first, quiesce A, then commit both stores synchronously
    // on MainActor while the attempt-generation lock excludes superseding
    // auth work. No AuthService token reader can interleave with a mixed
    // A/B credential generation.
    let committed = try await RuntimeOwnerIdentity.performEffectiveOwnerTransition(
      plannedNextOwner: { _, previousOwner in
        attemptFence.isCurrent(attempt) ? tokens.localId : previousOwner
      }
    ) { _ in
      try await MainActor.run {
        try attemptFence.commitIfCurrent(attempt) {
          try self.saveTokens(
            idToken: tokens.idToken,
            refreshToken: tokens.refreshToken,
            expiresIn: tokens.expiresIn,
            userId: tokens.localId)
          let defaults = UserDefaults.standard
          defaults.set(true, forKey: .authIsSignedIn)
          defaults.set(email, forKey: .authUserEmail)
          defaults.set(tokens.localId, forKey: .authUserId)
          defaults.synchronize()
          return true
        } ?? false
      }
    }
    guard committed else { return false }
    guard sessionAttemptFence.isCurrent(attempt) else { return false }
    NSLog("OMI AUTH: Atomically saved signed-in session for user %@", tokens.localId)
    AuthState.shared.userEmail = email
    sessionCoordinator.resetAfterSuccessfulSignIn()
    return true
  }

  /// Publish a restored session only if the restore attempt remains current.
  @discardableResult
  func commitRestoredSession(
    userId: String?,
    email: String?,
    attempt: AuthSessionAttempt
  ) async -> Bool {
    guard
      await saveAuthState(
        isSignedIn: true,
        email: email,
        userId: userId,
        attempt: attempt)
    else {
      return false
    }
    guard sessionAttemptFence.isCurrent(attempt) else { return false }
    AuthState.shared.userEmail = email
    sessionCoordinator.resetAfterSuccessfulSignIn()
    return true
  }

  /// Clear credentials before the awaited owner transition. This ordering is
  /// deliberate: a newer sign-in can begin while SQLite is closing, but a stale
  /// sign-out has no token-deletion step left to run after that suspension.
  @discardableResult
  func commitSignedOutSession(
    attempt: AuthSessionAttempt,
    phase: AuthSessionPhase
  ) async -> Bool {
    let cleared =
      sessionAttemptFence.commitIfCurrent(attempt) {
        clearTokens()
        AuthState.shared.userEmail = nil
        AuthState.shared.transition(to: phase)
        return true
      } ?? false
    guard cleared else { return false }
    return await saveAuthState(
      isSignedIn: false,
      email: nil,
      userId: nil,
      attempt: attempt)
  }

  private func restoreAuthState(attempt: AuthSessionAttempt) async {
    // Check if we have a saved auth state
    let savedSignedIn = UserDefaults.standard.bool(forKey: .authIsSignedIn)
    let savedEmail = UserDefaults.standard.string(forKey: .authUserEmail)

    NSLog(
      "OMI AUTH: Checking saved auth state - savedSignedIn: %@, savedEmail: %@",
      savedSignedIn ? "true" : "false", savedEmail ?? "nil")

    // Set auth state synchronously (we're already on main thread from configure()).
    // Using DispatchQueue.main.async here would defer to the next run-loop tick,
    // creating a race window where the Firebase auth state listener can fire first
    // with user=nil and flip isSignedIn to false before we restore it.
    if savedSignedIn {
      AuthState.shared.transition(to: .restoring)
      AuthState.shared.userEmail = Auth.auth().currentUser?.email ?? savedEmail

      // Migration: Fix empty userId by extracting from stored idToken.
      let savedUserId = UserDefaults.standard.string(forKey: .authUserId) ?? ""
      if savedUserId.isEmpty, let storedToken = storedIdToken {
        if let payload = decodeJWT(storedToken),
          let userId = payload["user_id"] as? String ?? payload["sub"] as? String
        {
          NSLog("OMI AUTH: Migrating empty userId - extracted from JWT: %@", userId)
          guard await persistAuthenticatedOwner(userId, attempt: attempt) else { return }
        }
      }

      // A persisted boolean and Firebase's cached currentUser are restore hints,
      // never proof of a usable session. Keep every authenticated surface gated
      // until a forced refresh succeeds.
      validateRestoredSession(attempt: attempt)
    } else {
      NSLog("OMI AUTH: No saved auth state found")
      guard
        await saveAuthState(
          isSignedIn: false,
          email: nil,
          userId: nil,
          attempt: attempt)
      else {
        return
      }
      AuthState.shared.transition(to: .signedOut)
    }
  }

  private func validateRestoredSession(attempt: AuthSessionAttempt) {
    Task { [weak self] in
      guard let self else { return }
      await self.validateRestoredSessionNow(attempt: attempt)
    }
  }

  func retryRestoredSession() async {
    let attempt = beginSessionAttempt()
    guard UserDefaults.standard.bool(forKey: .authIsSignedIn) else {
      AuthState.shared.transition(to: .signedOut)
      return
    }
    AuthState.shared.transition(to: .restoring)
    await validateRestoredSessionNow(attempt: attempt)
  }

  private func validateRestoredSessionNow(attempt: AuthSessionAttempt) async {
    guard sessionAttemptFence.isCurrent(attempt) else { return }
    let hasFirebaseUser = !DesktopLocalProfile.isEnabled && Auth.auth().currentUser != nil

    guard storedRefreshToken != nil || storedIdToken != nil || hasFirebaseUser else {
      NSLog("OMI AUTH: Restored session has no credentials — invalidating")
      await invalidateSession(reason: .restoredSessionInvalid)
      return
    }

    do {
      _ = try await sessionCoordinator.refreshSingleFlight(auth: self)
      guard sessionAttemptFence.isCurrent(attempt) else { return }
      NSLog("OMI AUTH: Restored session validated via forced refresh")
      let userId = storedTokenUserId ?? Auth.auth().currentUser?.uid
      guard
        await commitRestoredSession(
          userId: userId,
          email: AuthState.shared.userEmail,
          attempt: attempt)
      else {
        return
      }
      loadNameFromBackendIfNeeded()
      APIKeyService.shared.startFetchingKeys()
      Task { await FloatingBarUsageLimiter.shared.fetchPlan() }
    } catch AuthError.notSignedIn {
      guard sessionAttemptFence.isCurrent(attempt) else { return }
      if sessionCoordinator.phase == .needsReauth
        || (storedIdToken == nil && storedRefreshToken == nil && !hasFirebaseUser)
      {
        NSLog("OMI AUTH: Restored session validation proved credentials absent")
        await invalidateSession(reason: .restoredSessionInvalid)
      } else {
        NSLog("OMI AUTH: Restored session validation deferred - preserving credentials for retry")
        AuthState.shared.transition(to: .recoveryRequired)
      }
    } catch {
      guard sessionAttemptFence.isCurrent(attempt) else { return }
      NSLog("OMI AUTH: Restored session validation deferred (transient): %@", error.localizedDescription)
      AuthState.shared.transition(to: .recoveryRequired)
    }
  }

  // MARK: - Auth State Listener

  private func setupAuthStateListener() {
    authStateHandle = Auth.auth().addStateDidChangeListener { [weak self] _, user in
      Task { @MainActor in
        guard let self else { return }
        if let user {
          // Firebase currentUser is cached identity, not proof that the
          // credential can refresh. Only enrich an already validated session;
          // launch restoration remains owned by validateRestoredSessionNow().
          log(
            "AUTH_LISTENER: Firebase user present (uid=\(user.uid)), phase=\(String(describing: self.sessionCoordinator.phase))"
          )
          let ownerID = UserDefaults.standard.string(forKey: .authUserId)
          let tokenOwnerID = self.storedTokenUserId
          if self.sessionCoordinator.phase == .authenticated,
            ownerID == user.uid,
            tokenOwnerID == nil || tokenOwnerID == user.uid
          {
            let attempt = self.currentSessionAttempt()
            guard
              await self.saveAuthState(
                isSignedIn: true,
                email: user.email,
                userId: user.uid,
                attempt: attempt)
            else {
              return
            }
            AuthState.shared.userEmail = user.email
            self.loadNameFromBackendIfNeeded()
            Task { await SettingsSyncManager.shared.syncFromServer() }
          }
        } else {
          // Firebase has no user - check if we have a saved session (for dev builds where Keychain doesn't persist)
          let savedSignedIn = UserDefaults.standard.bool(forKey: .authIsSignedIn)
          log("AUTH_LISTENER: Firebase user nil, savedSignedIn=\(savedSignedIn), currentIsSignedIn=\(self.isSignedIn)")
          if !savedSignedIn {
            // No saved session either - user is truly signed out
            log("AUTH_LISTENER: No saved session - setting isSignedIn=false")
            AuthState.shared.transition(to: .signedOut)
            AuthState.shared.userEmail = nil
          } else {
            log("AUTH_LISTENER: Firebase user nil with saved session — validating REST tokens")
            await self.validateSavedSessionAfterFirebaseNil()
          }
        }
      }
    }
  }

  /// When Firebase SDK has no user but UserDefaults says signed-in, probe REST tokens.
  /// Invalidates only on definitive death; skips while launch restore is in flight.
  private func validateSavedSessionAfterFirebaseNil() async {
    let attempt = currentSessionAttempt()
    let expectedOwnerID = UserDefaults.standard.string(forKey: .authUserId)
    guard !AuthState.shared.isRestoringAuth else {
      log("AUTH_LISTENER: skipping REST validation while launch restore is in flight")
      return
    }
    guard storedRefreshToken != nil else {
      await invalidateSession(reason: .restoredSessionInvalid)
      return
    }
    do {
      _ = try await sessionCoordinator.refreshSingleFlight(auth: self)
      guard sessionAttemptFence.isCurrent(attempt),
        UserDefaults.standard.string(forKey: .authUserId) == expectedOwnerID
      else {
        return
      }
      sessionCoordinator.resetAfterSuccessfulSignIn()
      log("AUTH_LISTENER: saved REST session validated after Firebase nil")
    } catch AuthError.notSignedIn where storedIdToken == nil || storedRefreshToken == nil {
      guard sessionAttemptFence.isCurrent(attempt) else { return }
      log("AUTH_LISTENER: saved REST session definitively dead — invalidating")
      await invalidateSession(reason: .definitiveRefreshFailure)
    } catch {
      guard sessionAttemptFence.isCurrent(attempt) else { return }
      log("AUTH_LISTENER: saved REST session validation deferred: \(error.localizedDescription)")
      AuthState.shared.transition(to: .recoveryRequired)
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
    let sessionAttempt = beginSessionAttempt()
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
    guard sessionAttemptFence.isCurrent(sessionAttempt) else {
      throw AuthError.cancelled
    }
    appleSignInDelegate = nil  // Clean up

    // Step 3: Extract identity token
    guard let identityTokenData = appleCredential.identityToken,
      let identityToken = String(data: identityTokenData, encoding: .utf8)
    else {
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
    let firebaseTokens: FirebaseTokenResult

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
      guard sessionAttemptFence.isCurrent(sessionAttempt) else {
        discardStaleFirebaseUserIfNeeded(authResult.user.uid)
        throw AuthError.cancelled
      }
      firebaseTokens = FirebaseTokenResult(
        idToken: idToken,
        refreshToken: refreshToken,
        expiresIn: expiresIn,
        localId: userId)
    } catch {
      if !sessionAttemptFence.isCurrent(sessionAttempt) {
        throw AuthError.cancelled
      }
      // Fall back to REST API (works when Firebase SDK has keychain issues)
      let nsError = error as NSError
      NSLog(
        "OMI AUTH: Firebase SDK Apple sign-in failed (domain=%@ code=%d): %@", nsError.domain, nsError.code,
        error.localizedDescription)
      logError("AUTH: Firebase SDK Apple sign-in failed (domain=\(nsError.domain) code=\(nsError.code))", error: error)
      NSLog("OMI AUTH: Falling back to REST API for Apple sign-in...")
      let fallbackTokens = try await signInWithAppleIdentityToken(identityToken: identityToken, nonce: nonce)
      userId = fallbackTokens.localId
      firebaseTokens = fallbackTokens
    }

    // Extract email from identity token if not provided by Apple
    if AuthState.shared.userEmail == nil {
      if let payload = decodeJWT(identityToken),
        let email = payload["email"] as? String
      {
        AuthState.shared.userEmail = email
      }
    }

    guard
      try await commitSignedInSession(
        tokens: firebaseTokens,
        email: AuthState.shared.userEmail,
        attempt: sessionAttempt)
    else {
      throw AuthError.cancelled
    }

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
    let sessionAttempt = beginSessionAttempt()

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
            "loopback_port": callbackServer.port,
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
        trackAuthFlowEvent(
          "Auth Callback Invalid", stage: "authorize_url", provider: provider, authFlowId: flowId,
          failureClass: "invalid_url")
        throw AuthError.invalidURL
      }
      NSWorkspace.shared.open(url)
      trackAuthFlowEvent("Auth Browser Opened", stage: "browser_opened", provider: provider, authFlowId: flowId)

      // Step 4: Wait for callback with authorization code
      NSLog("OMI AUTH: Waiting for OAuth callback...")
      let (code, returnedState) = try await waitForOAuthCallback(callbackServer: callbackServer)
      clearLoopbackCallbackServerIfCurrent(callbackServer, flowId: flowId)
      bringAppToFrontAfterAuthCallback()
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
      trackAuthFlowEvent(
        "Auth Token Exchange Completed", stage: "token_exchange", provider: provider, authFlowId: flowId)
      NSLog("OMI AUTH: Got Firebase custom token")

      guard sessionAttemptFence.isCurrent(sessionAttempt) else {
        throw AuthError.cancelled
      }

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

      // Also try Firebase SDK sign-in (best effort for other Firebase features)
      guard sessionAttemptFence.isCurrent(sessionAttempt) else {
        throw AuthError.cancelled
      }
      do {
        let authResult = try await Auth.auth().signIn(withCustomToken: tokenResult.customToken)
        guard sessionAttemptFence.isCurrent(sessionAttempt) else {
          discardStaleFirebaseUserIfNeeded(authResult.user.uid)
          throw AuthError.cancelled
        }
        NSLog("OMI AUTH: Firebase SDK sign-in SUCCESS - uid: %@", authResult.user.uid)
      } catch AuthError.cancelled {
        throw AuthError.cancelled
      } catch let firebaseError as NSError {
        // Keychain errors are expected on dev builds - we have REST API tokens as fallback
        NSLog("OMI AUTH: Firebase SDK sign-in failed (using REST API tokens): %@", firebaseError.localizedDescription)
      }

      // Save auth state immediately
      let userId = firebaseTokens.localId
      guard
        try await commitSignedInSession(
          tokens: firebaseTokens,
          email: tokenResult.email,
          attempt: sessionAttempt)
      else {
        throw AuthError.cancelled
      }

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
      AnalyticsManager.shared.signInFailed(
        provider: provider,
        error: AuthError.timeout.localizedDescription,
        errorClass: authFailureClass(for: AuthError.timeout)
      )
      if let activeFlowId {
        clearOAuthFlowIfCurrent(flowId: activeFlowId, callbackServer: activeCallbackServer)
      }
      self.error = AuthError.timeout.localizedDescription
      throw AuthError.timeout
    } catch {
      let nsError = error as NSError
      NSLog("OMI AUTH: Error during sign in: %@", error.localizedDescription)
      logError(
        "AUTH: \(provider) web OAuth sign-in failed (domain=\(nsError.domain) code=\(nsError.code))", error: error)
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
      AnalyticsManager.shared.signInFailed(
        provider: provider,
        error: error.localizedDescription,
        errorClass: authFailureClass(for: error)
      )
      if let activeFlowId {
        clearOAuthFlowIfCurrent(flowId: activeFlowId, callbackServer: activeCallbackServer)
      }
      self.error = error.localizedDescription
      throw error
    }
  }

  // MARK: - OAuth URL Building

  private func buildAuthorizationURL(provider: String, state: String, codeChallenge: String, redirectURI: String)
    -> String
  {
    var components = URLComponents(string: "\(apiBaseURL)v1/auth/authorize")
    components?.queryItems = [
      URLQueryItem(name: "provider", value: provider),
      URLQueryItem(name: "redirect_uri", value: redirectURI),
      URLQueryItem(name: "state", value: state),
      URLQueryItem(name: "code_challenge", value: codeChallenge),
      URLQueryItem(name: "code_challenge_method", value: "S256"),
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
      let errorClass = PostHogManager.diagnosticErrorClass(error)
      properties["error"] = errorClass
      properties["error_class"] = errorClass
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
    case .invalidConfiguration: return "invalid_configuration"
    case .userChangedDuringRequest: return "user_changed_during_request"
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
        try? await Task.sleep(nanoseconds: 5 * 60 * 1_000_000_000)  // 5 minutes
        guard !Task.isCancelled else { return }
        await MainActor.run {
          guard self.pendingOAuthState == expectedState else { return }
          self.resumeOAuthContinuation(throwing: AuthError.timeout)
        }
      }
    }
  }

  private func waitForOAuthCallback(callbackServer: OAuthLoopbackCallbackServer?) async throws -> (
    code: String, state: String
  ) {
    guard let callbackServer else {
      return try await waitForOAuthCallback()
    }

    let timeoutTask = Task {
      try? await Task.sleep(nanoseconds: 5 * 60 * 1_000_000_000)  // 5 minutes
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
    // Foregrounding happens once in signIn() after waitForOAuthCallback returns,
    // so custom-scheme and loopback paths share a single activation.
    resumeOAuthContinuation(returning: (code: code, state: state))
  }

  /// Focus the main Omi window after the browser finishes the OAuth handoff.
  /// Filters to titled main windows so ordered-out panels (floating bar, overlays)
  /// are not resurrected by a blanket `orderFrontRegardless()` sweep.
  @MainActor
  private func bringAppToFrontAfterAuthCallback() {
    NSApp.activate()
    for window in NSApp.windows where window.title.lowercased().hasPrefix("omi") {
      window.makeKeyAndOrderFront(nil)
    }
  }

  /// Cancel an in-flight web OAuth sign-in so the user can retry from a clean
  /// state. The recovery path we care about: the user fails on the web side
  /// (closed the tab, denied, or just walked away) and comes back to a
  /// desktop app whose sign-in buttons are still disabled waiting on a
  /// callback that will never arrive.
  @MainActor
  func cancelSignIn() {
    if let loopbackCallbackServer {
      _ = beginSessionAttempt()
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
    _ = beginSessionAttempt()
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

  private func exchangeCodeForToken(code: String, codeVerifier: String, redirectURI: String) async throws
    -> TokenExchangeResult
  {
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
      ("code_verifier", codeVerifier),
    ]

    let bodyString =
      bodyParams
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

        NSLog(
          "OMI AUTH: Extracted from id_token - name: %@ %@, email: %@",
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

  nonisolated static func localUserId(fromIDToken idToken: String) -> String? {
    guard let payload = decodeJWTPayload(idToken) else { return nil }
    return payload["user_id"] as? String ?? payload["sub"] as? String
  }

  /// Decode a JWT and return the payload as a dictionary
  nonisolated static func decodeJWTPayload(_ jwt: String) -> [String: Any]? {
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
      let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
    else {
      return nil
    }

    return json
  }

  private func decodeJWT(_ jwt: String) -> [String: Any]? {
    Self.decodeJWTPayload(jwt)
  }

  // MARK: - User Name Management

  /// Update the user's given name (stores locally, updates Firebase Auth, and syncs to backend profile)
  @MainActor
  func updateGivenName(
    _ fullName: String,
    expectedOwnerID: String? = nil,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil
  ) async {
    let trimmedName = fullName.trimmingCharacters(in: .whitespaces)
    let nameParts = trimmedName.split(separator: " ", maxSplits: 1)
    let newGivenName = nameParts.first.map(String.init) ?? trimmedName
    let newFamilyName = nameParts.count > 1 ? String(nameParts[1]) : ""

    if let expectedOwnerID {
      await updateGivenNameOwnerBound(
        trimmedName: trimmedName,
        newGivenName: newGivenName,
        newFamilyName: newFamilyName,
        expectedOwnerID: expectedOwnerID,
        authorizationSnapshot: authorizationSnapshot
      )
      return
    }

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

  private func updateGivenNameOwnerBound(
    trimmedName: String,
    newGivenName: String,
    newFamilyName: String,
    expectedOwnerID: String,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot?
  ) async {
    guard isCurrentOwner(expectedOwnerID, authorizationSnapshot: authorizationSnapshot) else { return }
    let isImpersonating = UserDefaults.standard.bool(forKey: .authIsImpersonating)

    if !isImpersonating, let user = Auth.auth().currentUser {
      guard user.uid == expectedOwnerID else { return }
      do {
        let changeRequest = user.createProfileChangeRequest()
        changeRequest.displayName = trimmedName
        try await changeRequest.commitChanges()
      } catch {
        NSLog(
          "OMI AUTH: Failed to update Firebase displayName (non-fatal): %@",
          error.localizedDescription
        )
      }
      guard isCurrentOwner(expectedOwnerID, authorizationSnapshot: authorizationSnapshot) else { return }
    }

    if !isImpersonating {
      do {
        try await APIClient.shared.updateUserProfile(
          name: trimmedName,
          expectedOwnerId: expectedOwnerID,
          authorizationSnapshot: authorizationSnapshot
        )
      } catch {
        NSLog(
          "OMI AUTH: Failed to update backend profile name (non-fatal): %@",
          error.localizedDescription
        )
      }
      guard isCurrentOwner(expectedOwnerID, authorizationSnapshot: authorizationSnapshot) else { return }
    }

    givenName = newGivenName
    familyName = newFamilyName
    NSLog("OMI AUTH: Updated owner-bound name locally - given: %@, family: %@", newGivenName, newFamilyName)
  }

  private nonisolated func isCurrentOwner(
    _ expectedOwnerID: String,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil
  ) -> Bool {
    if let authorizationSnapshot {
      return authorizationSnapshot.ownerID == expectedOwnerID
        && RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot)
    }
    return AuthorizedToolExecution.isOwnerCurrent(expectedOwnerID)
  }

  /// Try to get name from Firebase user (after OAuth sign-in)
  func getNameFromFirebase() -> String? {
    if let displayName = Auth.auth().currentUser?.displayName, !displayName.isEmpty {
      return displayName
    }
    return nil
  }

  /// Load name from backend profile (Firestore) first, then fall back to Firebase Auth.
  /// This handles cases like Apple Sign-In where Firebase Auth displayName may be empty
  /// but the user already has a name stored in Firestore from a previous sign-up.
  func loadNameFromBackendIfNeeded() {
    guard givenName.isEmpty,
      let expectedOwnerID = RuntimeOwnerIdentity.currentOwnerId()
    else {
      return
    }
    let attempt = currentSessionAttempt()
    Task { [weak self] in
      guard let self,
        self.isSessionAttemptCurrent(attempt),
        RuntimeOwnerIdentity.currentOwnerId() == expectedOwnerID
      else {
        return
      }
      do {
        let profile = try await APIClient.shared.getUserProfile()
        guard self.isSessionAttemptCurrent(attempt),
          RuntimeOwnerIdentity.currentOwnerId() == expectedOwnerID
        else {
          return
        }
        if let name = profile.name, !name.trimmingCharacters(in: .whitespaces).isEmpty {
          let nameParts = name.trimmingCharacters(in: .whitespaces).split(separator: " ", maxSplits: 1)
          self.givenName = nameParts.first.map(String.init) ?? name.trimmingCharacters(in: .whitespaces)
          self.familyName = nameParts.count > 1 ? String(nameParts[1]) : ""
          NSLog("OMI AUTH: Loaded name from backend profile - given: %@, family: %@", self.givenName, self.familyName)
          return
        }
      } catch {
        guard self.isSessionAttemptCurrent(attempt),
          RuntimeOwnerIdentity.currentOwnerId() == expectedOwnerID
        else {
          return
        }
        NSLog("OMI AUTH: Failed to fetch backend profile for name (non-fatal): %@", error.localizedDescription)
      }
      // Fall back to Firebase Auth displayName
      guard self.givenName.isEmpty,
        self.isSessionAttemptCurrent(attempt),
        RuntimeOwnerIdentity.currentOwnerId() == expectedOwnerID,
        FirebaseApp.app() != nil,
        Auth.auth().currentUser?.uid == expectedOwnerID,
        let firebaseName = self.getNameFromFirebase()
      else {
        return
      }
      let nameParts = firebaseName.split(separator: " ", maxSplits: 1)
      self.givenName = nameParts.first.map(String.init) ?? firebaseName
      self.familyName = nameParts.count > 1 ? String(nameParts[1]) : ""
      NSLog("OMI AUTH: Loaded owner-bound name from Firebase - given: %@, family: %@", self.givenName, self.familyName)
    }
  }

  // MARK: - Token Storage

  func saveTokens(idToken: String, refreshToken: String, expiresIn: Int, userId: String) throws {
    // Store expiry time (current time + expiresIn seconds, minus 5 min buffer)
    let expiryTime = Date().addingTimeInterval(TimeInterval(expiresIn - 300))
    let tokens = StoredAuthTokens(
      idToken: idToken,
      refreshToken: refreshToken,
      expiryTime: expiryTime.timeIntervalSince1970,
      tokenUserId: userId
    )
    if usesKeychainTokenStorage {
      let legacyMigrationSource = loadUserDefaultsTokens()
      let hasLegacyMigrationSource =
        legacyMigrationSource.map {
          $0.tokenUserId.isEmpty || $0.tokenUserId == userId
        } ?? false
      if persistKeychainTokensTransactionally(tokens) {
        clearUserDefaultsTokens()
        cachedStoredTokens = tokens
        cachedStoredTokensLoaded = true
      } else if hasLegacyMigrationSource || allowsUserDefaultsTokenFallback {
        // Migration-only continuity: these secrets were already present in
        // UserDefaults before the Keychain migration started. Updating that
        // existing copy is safer than deleting the only refresh credential.
        // New sign-ins still fail closed when no legacy source exists.
        saveUserDefaultsTokens(idToken: idToken, refreshToken: refreshToken, expiryTime: expiryTime, userId: userId)
        cachedStoredTokens = tokens
        cachedStoredTokensLoaded = true
        log("AuthService: Keychain token persistence deferred; preserving legacy migration source")
        recordTokenStorageFallback(reason: "keychain_migration_deferred")
      } else {
        // Do not clear any prior credential on a failed write. The caller has
        // not committed the new signed-in state yet, so the old session remains
        // the only safe rollback point.
        throw AuthError.keychainTokenStorageUnavailable
      }
    } else {
      saveUserDefaultsTokens(idToken: idToken, refreshToken: refreshToken, expiryTime: expiryTime, userId: userId)
      cachedStoredTokens = tokens
      cachedStoredTokensLoaded = true
    }
    NSLog("OMI AUTH: Saved tokens for user %@, expires at %@", userId, expiryTime.description)
  }

  private func clearTokens() {
    tokenStorageHooks.deleteKeychainString(authTokenKeychainService, authTokenKeychainAccount)
    clearUserDefaultsTokens()
    invalidateStoredTokensCache()
    NSLog("OMI AUTH: Cleared all tokens")
  }

  private func saveUserDefaultsTokens(idToken: String, refreshToken: String, expiryTime: Date, userId: String) {
    UserDefaults.standard.set(idToken, forKey: .authIdToken)
    UserDefaults.standard.set(refreshToken, forKey: .authRefreshToken)
    UserDefaults.standard.set(expiryTime.timeIntervalSince1970, forKey: .authTokenExpiry)
    // Store the user ID that owns these tokens (for validation on retrieval)
    UserDefaults.standard.set(userId, forKey: .authTokenUserId)
  }

  private func clearUserDefaultsTokens() {
    UserDefaults.standard.removeObject(forKey: .authIdToken)
    UserDefaults.standard.removeObject(forKey: .authRefreshToken)
    UserDefaults.standard.removeObject(forKey: .authTokenExpiry)
    UserDefaults.standard.removeObject(forKey: .authTokenUserId)
  }

  /// AUTH-03 test seam (**non-prod only**): force the stored idToken's expiry into the
  /// past by re-saving the CURRENT tokens through `saveTokens` — the same storage path
  /// the app really uses — so a harness can then relaunch and prove the app refreshes an
  /// expired idToken *without signing the user out*.
  ///
  /// Why this exists: the tokens moved to the Keychain, so the old harness trick of
  /// `defaults write <bundle> auth_tokenExpiry -float 1000` now tampers a key the app
  /// no longer reads — the probe silently measured nothing and reported a false
  /// regression. Going through `saveTokens` keeps the seam correct for BOTH backends
  /// (keychain and the UserDefaults fallback) and is inert if the storage changes again.
  ///
  /// `expiresIn: 0` lands at `now - 300` (saveTokens subtracts the 5-min buffer), i.e.
  /// already expired. Token material never leaves the process — only a redacted status.
  func expireStoredTokenForAutomation() -> [String: String] {
    guard AppBuild.isNonProduction else {
      return ["error": "expire_auth_token is disabled on production bundles"]
    }
    guard let idToken = storedIdToken, let refreshToken = storedRefreshToken else {
      return ["error": "no stored tokens to expire"]
    }
    do {
      try saveTokens(
        idToken: idToken,
        refreshToken: refreshToken,
        expiresIn: 0,
        userId: storedTokenUserId ?? ""
      )
      return [
        "expired": "true",
        "storage": usesKeychainTokenStorage ? "keychain" : "user_defaults",
        "is_token_expired": isTokenExpired ? "true" : "false",
      ]
    } catch {
      return ["error": "failed to re-save tokens with a past expiry"]
    }
  }

  /// AUTH-03 test seam (**non-prod only**): read-only token status. Reports which
  /// backend actually holds the tokens and whether the stored idToken is currently
  /// expired, so a harness can assert "expired -> relaunch -> refreshed, still signed
  /// in" against the REAL storage instead of a UserDefaults key that may not be in use.
  /// Presence/expiry booleans only — never token material.
  func tokenStatusForAutomation() -> [String: String] {
    guard AppBuild.isNonProduction else {
      return ["error": "auth_token_status is disabled on production bundles"]
    }
    return [
      "signed_in": isSignedIn ? "true" : "false",
      "storage": usesKeychainTokenStorage ? "keychain" : "user_defaults",
      "has_id_token": storedIdToken != nil ? "true" : "false",
      "has_refresh_token": storedRefreshToken != nil ? "true" : "false",
      "is_token_expired": isTokenExpired ? "true" : "false",
    ]
  }

  private var usesKeychainTokenStorage: Bool {
    tokenStorageHooks.usesKeychainTokenStorage()
  }

  private var allowsUserDefaultsTokenFallback: Bool {
    tokenStorageHooks.allowsUserDefaultsFallback()
  }

  private func recordTokenStorageFallback(reason: String) {
    guard tokenStorageHooks.recordsFallbackTelemetry else { return }
    DesktopDiagnosticsManager.shared.recordFallback(
      area: "other",
      from: "keychain",
      to: "user_defaults",
      reason: "other",
      outcome: .degraded,
      extra: [
        "detail": reason,
        "update_channel": AppBuild.currentUpdateChannel,
      ]
    )
  }

  /// Keychain writes are not committed until the running signed app can read
  /// back the exact payload it wrote. Callers must retain the previous
  /// credential source until this returns true.
  private func persistKeychainTokensTransactionally(_ tokens: StoredAuthTokens) -> Bool {
    let previousPayload = tokenStorageHooks.readKeychainString(
      authTokenKeychainService,
      authTokenKeychainAccount
    )
    guard saveKeychainTokens(tokens) else { return false }
    guard let verified = loadKeychainTokens(), verified == tokens else {
      log("AuthService: Keychain token read-back verification failed; retaining previous credential source")
      if let previousPayload {
        let restored = tokenStorageHooks.writeKeychainString(
          previousPayload,
          authTokenKeychainService,
          authTokenKeychainAccount
        )
        let restoredPayload = tokenStorageHooks.readKeychainString(
          authTokenKeychainService,
          authTokenKeychainAccount
        )
        if !restored || restoredPayload != previousPayload {
          log("AuthService: failed to restore previous Keychain payload after verification failure")
        }
      } else {
        // The attempted write created the first item but did not verify.
        // Remove that partial value so a later retry is not mistaken for
        // a committed credential.
        tokenStorageHooks.deleteKeychainString(authTokenKeychainService, authTokenKeychainAccount)
      }
      return false
    }
    return true
  }

  private func saveKeychainTokens(_ tokens: StoredAuthTokens) -> Bool {
    do {
      let data = try JSONEncoder().encode(tokens)
      guard let payload = String(data: data, encoding: .utf8) else {
        log("AuthService: failed to encode Keychain token payload")
        return false
      }
      return tokenStorageHooks.writeKeychainString(
        payload,
        authTokenKeychainService,
        authTokenKeychainAccount
      )
    } catch {
      logError("AuthService: failed to encode Keychain token payload", error: error)
      return false
    }
  }

  private func loadKeychainTokens() -> StoredAuthTokens? {
    guard let payload = tokenStorageHooks.readKeychainString(authTokenKeychainService, authTokenKeychainAccount) else {
      return nil
    }
    guard let data = payload.data(using: .utf8) else {
      return nil
    }
    do {
      return try JSONDecoder().decode(StoredAuthTokens.self, from: data)
    } catch {
      logError("AuthService: failed to decode Keychain token payload", error: error)
      tokenStorageHooks.deleteKeychainString(authTokenKeychainService, authTokenKeychainAccount)
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
      let keychainTokens = loadKeychainTokens()
      let defaultsTokens = loadUserDefaultsTokens()
      let expectedUserId = UserDefaults.standard.string(forKey: .authUserId)

      let candidates = [keychainTokens, defaultsTokens].compactMap { $0 }
      let exactOwnerMatches = candidates.filter {
        guard let expectedUserId, !expectedUserId.isEmpty else { return false }
        return $0.tokenUserId == expectedUserId
      }
      let eligible = exactOwnerMatches.isEmpty ? candidates : exactOwnerMatches
      let preferred = eligible.max { $0.expiryTime < $1.expiryTime }

      if let defaultsTokens, preferred == defaultsTokens {
        // Stage the copy, but do not delete the legacy source here. The
        // forced refresh performed by restore validation will persist the
        // refreshed token and only then clear UserDefaults.
        if persistKeychainTokensTransactionally(defaultsTokens) {
          log("AuthService: staged legacy auth tokens in Keychain; awaiting refresh validation before cleanup")
        } else {
          log("AuthService: Keychain migration deferred; retaining legacy auth tokens")
          recordTokenStorageFallback(reason: "keychain_migration_deferred")
        }
      }
      tokens = preferred
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

  nonisolated static func decodeFirebaseTokenResult(
    from data: Data,
    requireLocalId: Bool = false
  ) throws -> FirebaseTokenResult {
    guard let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
      let idToken = json["idToken"] as? String,
      let refreshToken = json["refreshToken"] as? String
    else {
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

    let localId = json["localId"] as? String ?? localUserId(fromIDToken: idToken) ?? ""
    if requireLocalId && localId.isEmpty {
      throw AuthError.invalidResponse
    }

    return FirebaseTokenResult(
      idToken: idToken,
      refreshToken: refreshToken,
      expiresIn: expiresIn,
      localId: localId
    )
  }

  /// Exchange custom token for ID token using Firebase REST API
  private func exchangeCustomTokenForIdToken(customToken: String) async throws -> FirebaseTokenResult {
    let apiKey = try requireFirebaseApiKey()
    guard
      let url = URL(string: "https://identitytoolkit.googleapis.com/v1/accounts:signInWithCustomToken?key=\(apiKey)")
    else {
      throw AuthError.invalidURL
    }

    var request = URLRequest(url: url)
    request.httpMethod = "POST"
    request.setValue("application/json", forHTTPHeaderField: "Content-Type")
    request.httpBody = try JSONSerialization.data(withJSONObject: [
      "token": customToken,
      "returnSecureToken": true,
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

    do {
      let tokens = try Self.decodeFirebaseTokenResult(from: data)
      if !tokens.localId.isEmpty, jsonLocalIdMissing(in: data) {
        NSLog("OMI AUTH: Extracted user_id from JWT: %@", tokens.localId)
      }
      return tokens
    } catch {
      NSLog("OMI AUTH: Failed to parse Firebase response: %@", String(data: data, encoding: .utf8) ?? "nil")
      throw error
    }
  }

  private func jsonLocalIdMissing(in data: Data) -> Bool {
    guard let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
      return false
    }
    return (json["localId"] as? String ?? "").isEmpty
  }

  /// Refresh the ID token using the refresh token
  private func refreshIdToken(attempt: AuthSessionAttempt) async throws -> String {
    guard sessionAttemptFence.isCurrent(attempt) else { throw AuthError.notSignedIn }
    guard let refreshToken = storedRefreshToken else {
      throw AuthError.notSignedIn
    }

    let apiKey = try requireFirebaseApiKey()
    let refreshURL: URL
    if let hostPort = DesktopLocalProfile.authEmulatorHost {
      guard let url = URL(string: "http://\(hostPort)/securetoken.googleapis.com/v1/token?key=\(apiKey)") else {
        throw AuthError.invalidURL
      }
      refreshURL = url
    } else if DesktopLocalProfile.isEnabled {
      throw AuthError.invalidConfiguration
    } else {
      guard let url = URL(string: "https://securetoken.googleapis.com/v1/token?key=\(apiKey)") else {
        throw AuthError.invalidURL
      }
      refreshURL = url
    }

    var request = URLRequest(url: refreshURL)
    request.httpMethod = "POST"
    request.setValue("application/x-www-form-urlencoded", forHTTPHeaderField: "Content-Type")
    request.httpBody = "grant_type=refresh_token&refresh_token=\(refreshToken)".data(using: .utf8)

    let (data, response): (Data, URLResponse)
    if let handler = tokenRefreshHooks.dataForRequest {
      (data, response) = try await handler(request)
    } else {
      (data, response) = try await URLSession.shared.data(for: request)
    }

    guard sessionAttemptFence.isCurrent(attempt) else { throw AuthError.notSignedIn }

    guard let httpResponse = response as? HTTPURLResponse else {
      throw AuthError.invalidResponse
    }

    guard httpResponse.statusCode == 200 else {
      let errorBody = String(data: data, encoding: .utf8) ?? "unknown"
      NSLog("OMI AUTH: Token refresh error (HTTP %d): %@", httpResponse.statusCode, errorBody)
      // Only clear tokens for definitive auth failures (invalid/revoked refresh token).
      // Transient errors (network issues, 500s) should not destroy the session.
      let isDefinitiveAuthFailure = AuthDefinitiveDeathClassifier.isDefinitiveRefreshFailure(
        httpStatus: httpResponse.statusCode,
        errorBody: errorBody
      )
      if isDefinitiveAuthFailure {
        if DesktopLocalProfile.isEnabled {
          NSLog("OMI AUTH LOCAL: refresh failed — re-bootstrapping emulator session")
          await bootstrapLocalHarnessAuthIfNeeded()
          if let token = storedIdToken, !isTokenExpired {
            return token
          }
        }
        DesktopDiagnosticsManager.shared.recordAuthSessionCleared(
          reason: "refresh_token_rejected",
          httpStatusCode: httpResponse.statusCode
        )
        NSLog("OMI AUTH: Definitive auth failure — invalidating session")
        await invalidateSession(reason: .definitiveRefreshFailure)
        throw AuthError.notSignedIn
      }
      throw AuthError.tokenExchangeFailed(httpResponse.statusCode)
    }

    guard let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
      let newIdToken = json["id_token"] as? String,
      let newRefreshToken = json["refresh_token"] as? String,
      let expiresIn = json["expires_in"] as? String
    else {
      throw AuthError.invalidResponse
    }

    // Get user ID from response (Firebase returns it as "user_id")
    // Fall back to existing stored token user ID if not in response
    let userId = (json["user_id"] as? String) ?? storedTokenUserId ?? ""

    // Save new tokens only while the refresh's session attempt still owns
    // the credential store.
    let saved =
      try sessionAttemptFence.commitIfCurrent(attempt) {
        try saveTokens(
          idToken: newIdToken,
          refreshToken: newRefreshToken,
          expiresIn: Int(expiresIn) ?? 3600,
          userId: userId)
        return true
      } ?? false
    guard saved else { throw AuthError.notSignedIn }
    NSLog("OMI AUTH: Refreshed ID token successfully for user %@", userId)

    return newIdToken
  }

  // MARK: - Get ID Token (for API calls)

  func getIdToken(forceRefresh: Bool = false) async throws -> String {
    let attempt = currentSessionAttempt()
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
          guard await persistAuthenticatedOwner(tokenUserId, attempt: attempt) else {
            throw AuthError.notSignedIn
          }
          return token
        } else if tokenUserId == expectedUserId {
          return token
        } else {
          NSLog(
            "OMI AUTH: Stored token user mismatch (token: %@, expected: %@) - clearing stale token",
            tokenUserId, expectedUserId ?? "nil")
          _ = sessionAttemptFence.commitIfCurrent(attempt) {
            clearTokens()
          }
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
    if storedRefreshToken != nil {
      let tokenUserId = storedTokenUserId
      let canRefresh = tokenUserId == nil || expectedUserId == nil || tokenUserId == expectedUserId
      if canRefresh {
        do {
          return try await refreshIdToken(attempt: attempt)
        } catch {
          refreshFailure = error
          NSLog("OMI AUTH: Token refresh failed: %@", error.localizedDescription)
          // Definitive refresh failures already cleared local tokens — do not
          // fall through to Firebase SDK (which traps when FirebaseApp is absent).
          if case AuthError.notSignedIn = error {
            throw error
          }
        }
      }
    }

    // Third try: Use Firebase SDK (only if user matches expected user)
    // This prevents returning a stale user's token during sign-out race conditions
    // Local harness skips FirebaseApp.configure(); Auth.auth() traps if called.
    if !DesktopLocalProfile.isEnabled, FirebaseApp.app() != nil, let user = Auth.auth().currentUser {
      if expectedUserId == nil || user.uid == expectedUserId {
        if expectedUserId == nil {
          // Backfill the missing userId
          NSLog("OMI AUTH: expectedUserId is nil, backfilling from Firebase SDK user %@", user.uid)
          guard await persistAuthenticatedOwner(user.uid, attempt: attempt) else {
            throw AuthError.notSignedIn
          }
        }
        let tokenResult = try await user.getIDTokenResult(forcingRefresh: forceRefresh)
        guard sessionAttemptFence.isCurrent(attempt) else {
          throw AuthError.notSignedIn
        }
        return tokenResult.token
      } else {
        NSLog(
          "OMI AUTH: Firebase SDK user mismatch (firebase: %@, expected: %@) - not using",
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

  /// Returns an authorization header whose token subject is bound to the
  /// durable operation owner. This is intentionally stricter than the
  /// general request path: a sign-out/account switch must make an outbox
  /// delivery retry rather than send it with the next user's credentials.
  func getAuthHeader(
    forceRefresh: Bool = false,
    expectedUserId: String
  ) async throws -> String {
    let expected = expectedUserId.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !expected.isEmpty,
      UserDefaults.standard.string(forKey: .authUserId)?
        .trimmingCharacters(in: .whitespacesAndNewlines) == expected
    else {
      throw AuthError.userChangedDuringRequest
    }

    let token = try await getIdToken(forceRefresh: forceRefresh)
    guard
      UserDefaults.standard.string(forKey: .authUserId)?
        .trimmingCharacters(in: .whitespacesAndNewlines) == expected,
      Self.tokenOwnerId(from: token) == expected
    else {
      throw AuthError.userChangedDuringRequest
    }
    return "Bearer \(token)"
  }

  nonisolated static func tokenOwnerId(from token: String) -> String? {
    let parts = token.split(separator: ".", omittingEmptySubsequences: false)
    guard parts.count == 3 else { return nil }
    var payload = String(parts[1])
      .replacingOccurrences(of: "-", with: "+")
      .replacingOccurrences(of: "_", with: "/")
    let remainder = payload.count % 4
    if remainder != 0 {
      payload.append(String(repeating: "=", count: 4 - remainder))
    }
    guard let data = Data(base64Encoded: payload),
      let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
    else { return nil }
    for claim in ["user_id", "sub"] {
      if let value = json[claim] as? String,
        !value.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
      {
        return value
      }
    }
    return nil
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
          log(
            "[\(index + 1)] \(conversation.structured.emoji) \(conversation.title) (\(conversation.formattedDuration))")
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

  func signOut() async throws {
    let sessionAttempt = beginSessionAttempt()
    // Track sign out and reset analytics
    AnalyticsManager.shared.signedOut()
    AnalyticsManager.shared.reset()

    // Clear Sentry user context (skip in dev builds)
    if !AnalyticsManager.isDevBuild {
      SentrySDK.setUser(nil)
    }

    let signingOutUserID = UserDefaults.standard.string(forKey: .authUserId)
    try Auth.auth().signOut()
    // Reset coordinator only after Firebase sign-out succeeds so the state
    // transition is atomic — if signOut() throws (e.g. keychain error), the
    // coordinator stays in its previous phase rather than falsely reporting
    // .signedOut while local tokens remain intact.
    sessionCoordinator.resetAfterNuclearSignOut()
    CredentialHealthManager.shared.reset()
    APIKeyService.shared.clear()
    ChatDraftStore.shared.clearAll(ownerID: signingOutUserID)
    // Clear credentials before the awaited owner/SQLite transition. If a
    // newer sign-in starts while the old pool is closing, this stale
    // sign-out has no later token deletion that could wipe the new session.
    guard
      await commitSignedOutSession(
        attempt: sessionAttempt,
        phase: .signedOut)
    else {
      log("AuthService: stale sign-out completion ignored")
      return
    }
    guard sessionAttemptFence.isCurrent(sessionAttempt) else {
      log("AuthService: sign-out superseded by a newer session")
      return
    }

    // Stop trial polling and reset banner state for this user session
    if let state = AppState.current {
      state.stopTrialMetadataRefresh()
      state.trialMetadata = nil
      state.isPaywalled = false
    }
    TrialBannerService.shared.stop()

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
      "returnSecureToken": true,
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

    guard let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
      NSLog("OMI AUTH: Failed to parse Firebase signInWithIdp response")
      throw AuthError.invalidResponse
    }

    let tokens: FirebaseTokenResult
    do {
      tokens = try Self.decodeFirebaseTokenResult(from: data)
    } catch {
      NSLog(
        "OMI AUTH: Failed to parse Firebase signInWithIdp response: %@", String(data: data, encoding: .utf8) ?? "nil")
      throw error
    }

    // Get email from response if not already set
    if AuthState.shared.userEmail == nil {
      if let email = json["email"] as? String {
        AuthState.shared.userEmail = email
      }
    }

    return tokens
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

private class AppleSignInDelegate: NSObject, ASAuthorizationControllerDelegate,
  ASAuthorizationControllerPresentationContextProviding
{
  private var continuation: CheckedContinuation<ASAuthorizationAppleIDCredential, Error>?

  init(continuation: CheckedContinuation<ASAuthorizationAppleIDCredential, Error>) {
    self.continuation = continuation
    super.init()
  }

  func authorizationController(
    controller: ASAuthorizationController, didCompleteWithAuthorization authorization: ASAuthorization
  ) {
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
  case invalidConfiguration
  case userChangedDuringRequest

  var errorDescription: String? {
    switch self {
    case .invalidCredential:
      return "Invalid Apple credential"
    case .invalidNonce:
      return "Invalid nonce - please try again"
    case .missingToken:
      return "Missing identity token from Apple"
    case .missingFirebaseApiKey:
      return
        "Sign-in is not ready yet (Firebase API key unavailable). Please check your connection and try again in a moment."
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
    case .invalidConfiguration:
      return "Local harness auth is misconfigured (Firebase auth emulator host missing)"
    case .userChangedDuringRequest:
      return "The signed-in account changed while the request was being prepared"
    }
  }
}
