// Credential custody for the privileged HTTP bridge.
//
// The surface still sends only method + origin-relative path + JSON body.
// Base URL and bearer token stay in the shell. This file is the Keychain seam
// plus a launch-time bootstrap that prefers Keychain, then a scratch dev
// issuer, then the OMI_API_TOKEN env fallback.
//
// Concurrency: resolve() is synchronous. SecItem* for one generic-password
// item is fast enough to run inline at launch (before the webview loads). The
// optional issuer POST may block that same launch path briefly; keeping it
// synchronous avoids restructuring AppDelegate around an async handshake.
// Never put a token in logs, argv, URL query strings, or error messages.

import Foundation
import LocalAuthentication
import Security

/// Read/write/delete of a bearer token for a named account.
protocol CredentialStore: Sendable {
  /// Identity for logs. MUST NEVER contain a secret.
  var logDescription: String { get }
  func read(account: String) throws -> String?
  func write(account: String, token: String) throws
  func delete(account: String) throws
}

enum CredentialStoreError: Error, CustomStringConvertible, Sendable {
  case unexpectedStatus(OSStatus)
  case encodingFailed
  case emptyToken
  /// The item exists but this binary is not on its ACL, and we refused to
  /// raise a blocking UI prompt. Expected after any unsigned rebuild.
  case interactionRequired(OSStatus)

  var description: String {
    switch self {
    case .unexpectedStatus(let status):
      return "CredentialStoreError.unexpectedStatus(\(status))"
    case .encodingFailed:
      return "CredentialStoreError.encodingFailed"
    case .emptyToken:
      return "CredentialStoreError.emptyToken"
    case .interactionRequired(let status):
      return
        "CredentialStoreError.interactionRequired(\(status)) — item exists but this build is not on its ACL; not prompting on the launch path"
    }
  }
}

/// Real macOS Keychain custody via Security.framework generic passwords.
/// Service name is scratch-derived from the bundle so it cannot collide with a
/// shipping Omi keychain item.
struct KeychainCredentialStore: CredentialStore {
  let service: String

  var logDescription: String { "KeychainCredentialStore(service:\(service))" }

  /// Non-interactive authentication context. `kSecUseAuthenticationUI` is
  /// deprecated since macOS 11; the supported spelling is an `LAContext` with
  /// `interactionNotAllowed`. Same intent either way: a Keychain call on the
  /// launch path must never raise a blocking SecurityAgent dialog.
  private static func nonInteractiveContext() -> LAContext {
    let context = LAContext()
    context.interactionNotAllowed = true
    return context
  }

  init(service: String? = nil) {
    if let service, !service.isEmpty {
      self.service = service
    } else {
      let bundleName =
        (Bundle.main.object(forInfoDictionaryKey: "CFBundleName") as? String)
        .flatMap { $0.isEmpty ? nil : $0 }
        ?? "omi-on-fe-shells"
      self.service = "scratch.\(bundleName).credential"
    }
  }

  func read(account: String) throws -> String? {
    let query: [String: Any] = [
      kSecClass as String: kSecClassGenericPassword,
      kSecAttrService as String: service,
      kSecAttrAccount as String: account,
      kSecReturnData as String: true,
      kSecMatchLimit as String: kSecMatchLimitOne,
      // NEVER PROMPT ON THE LAUNCH PATH. A Keychain item's ACL trusts the exact
      // binary that created it, and an unsigned scratch build gets a fresh
      // ad-hoc identity on every rebuild — so the next launch raises a blocking
      // SecurityAgent dialog. Because bootstrap is synchronous and runs before
      // the webview loads, that dialog HANGS THE APP on a blank window until a
      // human clicks Allow. Observed directly on this branch: the process
      // stalled after the loopback line with SecurityAgent waiting.
      //
      // Failing closed instead lets bootstrap fall through to the dev issuer or
      // the environment, which is the correct dev-loop behavior: custody is used
      // when it is available and never blocks startup when it is not.
      kSecUseAuthenticationContext as String: Self.nonInteractiveContext(),
    ]
    var item: CFTypeRef?
    let status = SecItemCopyMatching(query as CFDictionary, &item)
    if status == errSecItemNotFound { return nil }
    if status == errSecInteractionNotAllowed || status == errSecAuthFailed {
      // Not an error worth failing the launch over — say so and move on.
      throw CredentialStoreError.interactionRequired(status)
    }
    guard status == errSecSuccess else {
      throw CredentialStoreError.unexpectedStatus(status)
    }
    guard let data = item as? Data else {
      throw CredentialStoreError.encodingFailed
    }
    guard let token = String(data: data, encoding: .utf8), !token.isEmpty else {
      return nil
    }
    return token
  }

  func write(account: String, token: String) throws {
    guard !token.isEmpty else { throw CredentialStoreError.emptyToken }
    let data = Data(token.utf8)
    let base: [String: Any] = [
      kSecClass as String: kSecClassGenericPassword,
      kSecAttrService as String: service,
      kSecAttrAccount as String: account,
    ]
    var add = base
    add[kSecValueData as String] = data
    let addStatus = SecItemAdd(add as CFDictionary, nil)
    if addStatus == errSecSuccess { return }
    if addStatus == errSecDuplicateItem {
      // Same non-prompting rule as read(): updating an item created by an
      // earlier unsigned build would otherwise raise a blocking dialog.
      var updateQuery = base
      updateQuery[kSecUseAuthenticationContext as String] = Self.nonInteractiveContext()
      let updateStatus = SecItemUpdate(
        updateQuery as CFDictionary,
        [kSecValueData as String: data] as CFDictionary)
      if updateStatus == errSecInteractionNotAllowed || updateStatus == errSecAuthFailed {
        throw CredentialStoreError.interactionRequired(updateStatus)
      }
      guard updateStatus == errSecSuccess else {
        throw CredentialStoreError.unexpectedStatus(updateStatus)
      }
      return
    }
    throw CredentialStoreError.unexpectedStatus(addStatus)
  }

  func delete(account: String) throws {
    let query: [String: Any] = [
      kSecClass as String: kSecClassGenericPassword,
      kSecAttrService as String: service,
      kSecAttrAccount as String: account,
    ]
    let status = SecItemDelete(query as CFDictionary)
    if status == errSecSuccess || status == errSecItemNotFound { return }
    throw CredentialStoreError.unexpectedStatus(status)
  }
}

/// Dev fallback: reads `OMI_API_TOKEN`. Write/delete are intentional no-ops.
struct EnvironmentCredentialStore: CredentialStore {
  let environment: [String: String]

  var logDescription: String { "EnvironmentCredentialStore(OMI_API_TOKEN)" }

  init(environment: [String: String] = ProcessInfo.processInfo.environment) {
    self.environment = environment
  }

  func read(account: String) throws -> String? {
    _ = account
    guard let token = environment["OMI_API_TOKEN"], !token.isEmpty else { return nil }
    return token
  }

  func write(account: String, token: String) throws {
    _ = account
    _ = token
  }

  func delete(account: String) throws {
    _ = account
  }
}

enum SessionBootstrapError: Error, CustomStringConvertible, Sendable {
  case issuerInvalidURL
  case issuerHTTPStatus(Int)
  case issuerEmptyBody
  case issuerNoTokenField
  case issuerTransport(Int)
  /// Custody did not answer within the launch deadline (ACL prompt, most likely).
  case keychainTimedOut
  case keychainUnavailable(String)

  var description: String {
    switch self {
    case .issuerInvalidURL:
      return "SessionBootstrapError.issuerInvalidURL"
    case .issuerHTTPStatus(let code):
      return "SessionBootstrapError.issuerHTTPStatus(\(code))"
    case .issuerEmptyBody:
      return "SessionBootstrapError.issuerEmptyBody"
    case .issuerNoTokenField:
      return "SessionBootstrapError.issuerNoTokenField"
    case .issuerTransport(let code):
      return "SessionBootstrapError.issuerTransport(\(code))"
    case .keychainTimedOut:
      return "SessionBootstrapError.keychainTimedOut (ACL prompt suspected; launch not blocked)"
    case .keychainUnavailable(let detail):
      return "SessionBootstrapError.keychainUnavailable(\(detail))"
    }
  }
}

/// Resolves API base URL + bearer token before the webview loads.
enum SessionBootstrap {
  enum Path: String, Sendable {
    case keychain
    case devIssuer
    case environment
    case none
  }

  struct Result: Sendable {
    let baseURL: URL?
    let token: String?
    let path: Path
    /// Which store was consulted for the chosen path (never contains a secret).
    let storeLogDescription: String

    var tokenPresent: Bool { token.map { !$0.isEmpty } ?? false }
  }

  static let defaultAccount = "api"

  /// Keychain account, SCOPED TO THE BACKEND ORIGIN.
  ///
  /// A single "api" account is wrong the moment you repoint the shell: running
  /// against 127.0.0.1:4747 and then against 127.0.0.1:4801 would reuse the
  /// first backend's token against the second, and the app would render an
  /// empty or 401 screen that looks exactly like a UI bug. Scoping by
  /// scheme+host+port keeps one credential per backend.
  static func account(for baseURL: URL?) -> String {
    guard let baseURL, let scheme = baseURL.scheme, let host = baseURL.host else {
      return defaultAccount
    }
    let port = baseURL.port.map { ":\($0)" } ?? ""
    return "\(defaultAccount)@\(scheme)://\(host)\(port)"
  }

  /// Synchronous launch-path bootstrap. See file header for the concurrency choice.
  ///
  /// PRECEDENCE — explicit configuration beats cached custody. An operator who
  /// exports OMI_API_TOKEN is stating an intent; if the Keychain silently won,
  /// a rotated dev token would be ignored and the shell would keep presenting a
  /// stale credential with no visible signal. So an explicit env token is used
  /// AND written through to the Keychain, which keeps the custody path real
  /// without letting the cache override the operator.
  static func resolve(
    account explicitAccount: String? = nil,
    environment: [String: String] = ProcessInfo.processInfo.environment,
    keychain: KeychainCredentialStore = KeychainCredentialStore(),
    urlSession: URLSession = SessionBootstrap.makeIssuerSession()
  ) -> Result {
    let baseURL = Self.resolveBaseURL(environment: environment)
    let account = explicitAccount ?? Self.account(for: baseURL)
    let envStore = EnvironmentCredentialStore(environment: environment)

    // 1. Explicit env token wins, and refreshes custody.
    if let token = (try? envStore.read(account: account)) ?? nil {
      do {
        try keychain.write(account: account, token: token)
      } catch {
        log("keychain-persist-failed after-env store=\(keychain.logDescription) error=\(error)")
      }
      return Result(
        baseURL: baseURL, token: token, path: .environment,
        storeLogDescription: envStore.logDescription)
    }

    // 2. Previously persisted custody for THIS backend.
    // BOUNDED. Neither kSecUseAuthenticationUI nor an LAContext with
    // interactionNotAllowed suppresses the LEGACY KEYCHAIN ACL PROMPT: that
    // prompt is about which binary is trusted for the item, not about
    // biometric/passcode UI. An unsigned scratch build gets a fresh ad-hoc
    // identity on every rebuild, so the first launch after ANY rebuild blocks
    // inside SecItemCopyMatching behind a SecurityAgent dialog — verified twice
    // on this branch, with the app stalled on a blank window after the loopback
    // line. A launch path must never be able to hang, so the read runs off the
    // main thread with a hard deadline and simply loses its turn on timeout.
    switch Self.readWithDeadline(keychain, account: account, seconds: 2.0) {
    case .success(let token?):
      return Result(
        baseURL: baseURL, token: token, path: .keychain,
        storeLogDescription: keychain.logDescription)
    case .success(nil):
      break
    case .failure(let error):
      log("keychain-read-skipped store=\(keychain.logDescription) reason=\(error)")
    }

    // 3. Acquire from the dev-mode issuer and persist.
    if let issuerRaw = environment["OMI_DEV_TOKEN_ISSUER_URL"], !issuerRaw.isEmpty {
      do {
        let token = try acquireFromDevIssuer(urlString: issuerRaw, session: urlSession)
        do {
          try keychain.write(account: account, token: token)
        } catch {
          log(
            "keychain-persist-failed after-issuer store=\(keychain.logDescription) error=\(error)")
        }
        return Result(
          baseURL: baseURL, token: token, path: .devIssuer,
          storeLogDescription: keychain.logDescription)
      } catch {
        log("dev-issuer-failed error=\(error)")
      }
    }

    return Result(
      baseURL: baseURL, token: nil, path: .none,
      storeLogDescription: keychain.logDescription)
  }

  /// Reads custody with a hard deadline. Returns .failure(timedOut) rather than
  /// blocking the launch path when the Keychain wants to show an ACL prompt.
  static func readWithDeadline(
    _ store: CredentialStore, account: String, seconds: Double
  ) -> Swift.Result<String?, SessionBootstrapError> {
    let semaphore = DispatchSemaphore(value: 0)
    // Unchecked box: only one writer, and the reader runs strictly after wait().
    final class Box: @unchecked Sendable { var value: Swift.Result<String?, Error>? }
    let box = Box()
    DispatchQueue.global(qos: .userInitiated).async {
      box.value = Swift.Result { try store.read(account: account) }
      semaphore.signal()
    }
    if semaphore.wait(timeout: .now() + seconds) == .timedOut {
      // The worker thread stays parked on the dialog; it is abandoned, never
      // joined, and its result is discarded. Bootstrap continues without it.
      return .failure(.keychainTimedOut)
    }
    switch box.value {
    case .success(let token): return .success(token)
    case .failure(let error): return .failure(.keychainUnavailable(String(describing: error)))
    case .none: return .success(nil)
    }
  }

  static func makeIssuerSession() -> URLSession {
    let cfg = URLSessionConfiguration.ephemeral
    cfg.timeoutIntervalForRequest = 10
    cfg.timeoutIntervalForResource = 15
    cfg.httpCookieStorage = nil
    cfg.httpShouldSetCookies = false
    cfg.httpCookieAcceptPolicy = .never
    return URLSession(configuration: cfg)
  }

  private static func resolveBaseURL(environment: [String: String]) -> URL? {
    guard let raw = environment["OMI_API_BASE_URL"], !raw.isEmpty,
      let base = URL(string: raw), base.scheme != nil, base.host != nil
    else { return nil }
    return base
  }

  /// POST to the scratch issuer. Token travels only in the response body —
  /// never in the request URL query, logs, or thrown error text.
  private static func acquireFromDevIssuer(urlString: String, session: URLSession) throws -> String {
    guard let url = URL(string: urlString), url.scheme != nil, url.host != nil else {
      throw SessionBootstrapError.issuerInvalidURL
    }
    // Refuse query strings so a misconfigured issuer URL cannot smuggle secrets
    // into process logs that print the redacted request URL.
    if let query = URLComponents(url: url, resolvingAgainstBaseURL: false)?.query, !query.isEmpty {
      throw SessionBootstrapError.issuerInvalidURL
    }

    var request = URLRequest(url: url)
    request.httpMethod = "POST"
    request.setValue("application/json", forHTTPHeaderField: "accept")
    request.httpBody = Data("{}".utf8)
    request.setValue("application/json", forHTTPHeaderField: "content-type")

    let data: Data
    let response: URLResponse
    do {
      // Launch-only: block this thread until the issuer answers or times out.
      (data, response) = try session.syncData(for: request)
    } catch {
      let code = (error as NSError).code
      throw SessionBootstrapError.issuerTransport(code)
    }
    guard let http = response as? HTTPURLResponse else {
      throw SessionBootstrapError.issuerTransport(-1)
    }
    guard (200..<300).contains(http.statusCode) else {
      throw SessionBootstrapError.issuerHTTPStatus(http.statusCode)
    }
    guard !data.isEmpty else { throw SessionBootstrapError.issuerEmptyBody }
    guard let token = extractToken(from: data), !token.isEmpty else {
      throw SessionBootstrapError.issuerNoTokenField
    }
    return token
  }

  /// Accepts `{"token":"..."}` / `{"access_token":"..."}`, or a raw UTF-8 token body.
  private static func extractToken(from data: Data) -> String? {
    if let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
      for key in ["token", "access_token"] {
        if let value = obj[key] as? String, !value.isEmpty { return value }
      }
      return nil
    }
    guard let text = String(data: data, encoding: .utf8)?
      .trimmingCharacters(in: .whitespacesAndNewlines), !text.isEmpty
    else { return nil }
    // Reject obvious JSON objects we failed to parse as token carriers.
    if text.hasPrefix("{") { return nil }
    return text
  }

  private static func log(_ line: String) {
    FileHandle.standardError.write(Data("session-bootstrap: \(line)\n".utf8))
  }
}

extension URLSession {
  /// Blocking data task for launch-time bootstrap only. Prefer async APIs elsewhere.
  fileprivate func syncData(for request: URLRequest) throws -> (Data, URLResponse) {
    let lock = DispatchSemaphore(value: 0)
    var result: Result<(Data, URLResponse), Error>?
    let task = dataTask(with: request) { data, response, error in
      if let error {
        result = .failure(error)
      } else if let data, let response {
        result = .success((data, response))
      } else {
        result = .failure(URLError(.badServerResponse))
      }
      lock.signal()
    }
    task.resume()
    lock.wait()
    switch result {
    case .success(let value): return value
    case .failure(let error): throw error
    case .none: throw URLError(.unknown)
    }
  }
}
