import AppKit
import Foundation

/// Fetches Crisp operator messages on app activation and Cmd+R,
/// fires macOS notifications, and tracks unread count for the sidebar badge.
@MainActor
class CrispManager: ObservableObject {
  static let shared = CrispManager()

  /// First-launch polling watermark, in epoch MILLISECONDS to match Crisp
  /// message timestamps (`CrispOperatorMessage.timestamp` and the `?since=`
  /// filter in the Rust route). Seeding this in seconds (~1e9) left it ~1000x
  /// below every real message timestamp (~1e12), so the first poll treated all
  /// historical operator messages as new and fired a notification for each.
  nonisolated static func initialWatermark(now: Date = Date()) -> UInt64 {
    UInt64(now.timeIntervalSince1970 * 1000)
  }

  /// Number of unread operator messages (shown as badge in sidebar)
  @Published private(set) var unreadCount = 0

  /// Whether the user is currently viewing the Help tab
  var isViewingHelp = false {
    didSet {
      if isViewingHelp {
        unreadCount = 0
        // Update lastSeenTimestamp so these messages aren't re-notified
        lastSeenTimestamp = latestOperatorTimestamp
      }
    }
  }

  /// Timestamp of the most recent operator message we've already notified about.
  /// Persisted to UserDefaults so unread messages survive app restarts.
  /// Stored as Double because UserDefaults can't round-trip UInt64.
  /// Non-`private` so `CrispManagerLifecycleTests` can assert `markAsRead()` advances it.
  var lastSeenTimestamp: UInt64 {
    get { UInt64(UserDefaults.standard.double(forKey: "crisp_lastSeenTimestamp")) }
    set { UserDefaults.standard.set(Double(newValue), forKey: "crisp_lastSeenTimestamp") }
  }

  /// Track the latest operator message timestamp from any poll.
  /// Persisted to UserDefaults so we don't re-notify after restart.
  /// Non-`private` so `CrispManagerLifecycleTests` can seed it before `markAsRead()`.
  var latestOperatorTimestamp: UInt64 {
    get { UInt64(UserDefaults.standard.double(forKey: "crisp_latestOperatorTimestamp")) }
    set { UserDefaults.standard.set(Double(newValue), forKey: "crisp_latestOperatorTimestamp") }
  }

  /// Track message texts we've already sent notifications for (to avoid duplicates)
  private var notifiedMessages = Set<String>()

  /// Whether start() has been called. Non-`private` so lifecycle tests can
  /// assert idempotency after calling `start()` twice.
  var isStarted = false

  /// Non-`private` so lifecycle tests can assert `stop()` clears both observers.
  var activationObserver: NSObjectProtocol?
  var refreshAllObserver: NSObjectProtocol?

  /// Retained so a delayed startup poll cannot fire after sign-out/stop.
  private var initialPollTask: Task<Void, Never>?

  /// Counter bumped at the top of `pollForMessages()`, before the auth-backoff
  /// guard and the network task. Lets `CrispManagerLifecycleTests` prove that
  /// posting `didBecomeActive` / `.refreshAllData` actually reaches the poll
  /// method — if an observer subscribes to the wrong notification name or a
  /// future edit drops the wiring, the counter stays flat and the test fails.
  /// Deliberately **not** `@Published` — publishing on every activation/Cmd+R
  /// refresh would emit `objectWillChange` and invalidate any SwiftUI view
  /// observing `CrispManager`, which is a pure production cost for a value
  /// nothing drives UI from.
  private(set) var pollInvocations: Int = 0

  /// Call once after sign-in to fetch Crisp messages and listen for activation/Cmd+R.
  ///
  /// - Parameters:
  ///   - performInitialPoll: If `true` (default), schedules an initial
  ///     `pollForMessages()` call that hits `APIClient.shared`. Pass `false` only
  ///     from lifecycle unit tests that want to exercise observer registration
  ///     without touching the network, auth state, or firing real notifications.
  ///   - initialPollDelay: Optional delay before the initial poll. Activation and
  ///     Cmd+R events still poll immediately.
  func start(performInitialPoll: Bool = true, initialPollDelay: TimeInterval = 0, sessionUserId: String? = nil) {
    guard !isStarted else { return }
    isStarted = true

    // Only set lastSeenTimestamp to "now" on first-ever launch.
    // On subsequent launches, keep the persisted value so the first
    // poll picks up messages that arrived while the app was closed.
    if lastSeenTimestamp == 0 {
      lastSeenTimestamp = Self.initialWatermark()
    }

    if performInitialPoll {
      if initialPollDelay > 0 {
        initialPollTask?.cancel()
        initialPollTask = Task { [weak self] in
          try? await Task.sleep(nanoseconds: UInt64(initialPollDelay * 1_000_000_000))
          guard !Task.isCancelled else { return }
          guard let self, self.isStarted else { return }
          guard
            StartupWarmupSessionScope(userId: sessionUserId).matches(
              currentUserId: UserDefaults.standard.string(forKey: "auth_userId"),
              isSignedIn: AuthState.shared.isSignedIn
            )
          else { return }
          self.pollForMessages()
        }
      } else {
        pollForMessages()
      }
    }

    // Refresh on app activation and Cmd+R (no periodic timer)
    activationObserver = NotificationCenter.default.addObserver(
      forName: NSApplication.didBecomeActiveNotification, object: nil, queue: .main
    ) { [weak self] _ in Task { @MainActor in self?.pollForMessages() } }

    refreshAllObserver = NotificationCenter.default.addObserver(
      forName: .refreshAllData, object: nil, queue: .main
    ) { [weak self] _ in Task { @MainActor in self?.pollForMessages() } }

    log("CrispManager: started (event-driven, no polling timer)")
  }

  /// Mark messages as read (called when user opens Help tab)
  func markAsRead() {
    unreadCount = 0
    lastSeenTimestamp = latestOperatorTimestamp
  }

  /// Stop observing (called on sign-out)
  func stop(preserveReadState: Bool = false) {
    initialPollTask?.cancel()
    initialPollTask = nil
    if let obs = activationObserver { NotificationCenter.default.removeObserver(obs) }
    if let obs = refreshAllObserver { NotificationCenter.default.removeObserver(obs) }
    activationObserver = nil
    refreshAllObserver = nil
    isStarted = false
    unreadCount = 0
    if !preserveReadState {
      // Clear persisted timestamps so next sign-in starts fresh.
      UserDefaults.standard.removeObject(forKey: "crisp_lastSeenTimestamp")
      UserDefaults.standard.removeObject(forKey: "crisp_latestOperatorTimestamp")
      notifiedMessages.removeAll()
    }
  }

  // MARK: - Private

  private func pollForMessages() {
    pollInvocations += 1
    guard !isRunningUnderXCTest else { return }
    guard let ownerID = RuntimeOwnerIdentity.currentOwnerId() else { return }
    Task { [ownerID] in
      do {
        let messages = try await fetchUnreadMessages(ownerID: ownerID)
        guard RuntimeOwnerIdentity.currentOwnerId() == ownerID else { return }
        log("CrispManager: poll returned \(messages.count) messages (since=\(self.lastSeenTimestamp))")

        var newMessageCount = 0
        for msg in messages {
          guard RuntimeOwnerIdentity.currentOwnerId() == ownerID else { return }
          let key = String(msg.text.prefix(80)) + "_\(msg.timestamp)"

          // Track the latest operator timestamp
          if msg.timestamp > latestOperatorTimestamp {
            latestOperatorTimestamp = msg.timestamp
          }

          // Skip if already notified
          guard !notifiedMessages.contains(key) else { continue }
          notifiedMessages.insert(key)

          newMessageCount += 1

          // Send macOS notification
          let preview = msg.text.count > 100 ? String(msg.text.prefix(100)) + "..." : msg.text
          log("CrispManager: new operator message: \(preview)")

          NotificationService.shared.sendNotification(
            ownerID: ownerID,
            title: "Help from Founder",
            message: preview,
            assistantId: "crisp",
            respectFrequency: false
          )
        }

        // Batch update: single @Published write instead of per-message increments
        guard RuntimeOwnerIdentity.currentOwnerId() == ownerID else { return }
        if newMessageCount > 0 && !isViewingHelp {
          unreadCount += newMessageCount
        }
      } catch {
        log("CrispManager: poll failed: \(error)")
      }
    }
  }

  private var isRunningUnderXCTest: Bool {
    ProcessInfo.processInfo.environment["XCTestConfigurationFilePath"] != nil
      || NSClassFromString("XCTestCase") != nil
  }

  private struct CrispUnreadResponse: Codable {
    let unread_count: Int
    let messages: [CrispOperatorMessage]
  }

  private struct CrispOperatorMessage: Codable {
    let text: String
    let timestamp: UInt64
    let from: String
  }

  private func fetchUnreadMessages(ownerID: String) async throws -> [CrispOperatorMessage] {
    guard RuntimeOwnerIdentity.currentOwnerId() == ownerID else {
      throw AuthError.userChangedDuringRequest
    }
    let api = APIClient.shared
    let baseURL = await api.rustBackendURL
    guard RuntimeOwnerIdentity.currentOwnerId() == ownerID else {
      throw AuthError.userChangedDuringRequest
    }
    let headers = try await api.buildHeaders(
      requireAuth: true,
      expectedAuthOwnerId: ownerID
    )
    guard RuntimeOwnerIdentity.currentOwnerId() == ownerID else {
      throw AuthError.userChangedDuringRequest
    }

    var urlString = "\(baseURL)v1/crisp/unread"
    if lastSeenTimestamp > 0 {
      urlString += "?since=\(lastSeenTimestamp)"
    }

    log("CrispManager: fetching \(urlString)")
    guard let url = URL(string: urlString) else {
      throw URLError(.badURL)
    }

    var request = URLRequest(url: url)
    request.httpMethod = "GET"
    for (key, value) in headers {
      request.setValue(value, forHTTPHeaderField: key)
    }

    let session = api.session
    let (data, response) = try await session.data(for: request)
    guard RuntimeOwnerIdentity.currentOwnerId() == ownerID else {
      throw AuthError.userChangedDuringRequest
    }

    guard let httpResponse = response as? HTTPURLResponse else {
      throw URLError(.badServerResponse)
    }

    // 503 means Crisp is not configured - silently return empty
    if httpResponse.statusCode == 503 {
      return []
    }

    if httpResponse.statusCode == 401 {
      throw APIError.unauthorized
    }

    guard httpResponse.statusCode == 200 else {
      log("CrispManager: backend returned \(httpResponse.statusCode)")
      return []
    }

    let decoded = try JSONDecoder().decode(CrispUnreadResponse.self, from: data)
    return decoded.messages
  }
}
