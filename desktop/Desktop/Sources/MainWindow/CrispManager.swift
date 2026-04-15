import AppKit
import Foundation

/// Fetches Crisp operator messages on app activation and Cmd+R,
/// fires macOS notifications, and tracks unread count for the sidebar badge.
@MainActor
class CrispManager: ObservableObject {
    static let shared = CrispManager()

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
    /// - Parameter performInitialPoll: If `true` (default), kicks off an immediate
    ///   `pollForMessages()` call that hits `APIClient.shared`. Pass `false` only
    ///   from lifecycle unit tests that want to exercise observer registration
    ///   without touching the network, auth state, or firing real notifications.
    func start(performInitialPoll: Bool = true) {
        guard !isStarted else { return }
        isStarted = true

        // Only set lastSeenTimestamp to "now" on first-ever launch.
        // On subsequent launches, keep the persisted value so the first
        // poll picks up messages that arrived while the app was closed.
        if lastSeenTimestamp == 0 {
            lastSeenTimestamp = UInt64(Date().timeIntervalSince1970)
        }

        if performInitialPoll {
            pollForMessages()
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
    func stop() {
        if let obs = activationObserver { NotificationCenter.default.removeObserver(obs) }
        if let obs = refreshAllObserver { NotificationCenter.default.removeObserver(obs) }
        activationObserver = nil
        refreshAllObserver = nil
        isStarted = false
        unreadCount = 0
        // Clear persisted timestamps so next sign-in starts fresh
        UserDefaults.standard.removeObject(forKey: "crisp_lastSeenTimestamp")
        UserDefaults.standard.removeObject(forKey: "crisp_latestOperatorTimestamp")
        notifiedMessages.removeAll()
    }

    // MARK: - Private

    private func pollForMessages() {
        pollInvocations += 1
        Task {
            // Skip if in auth backoff period (recent 401 errors)
            guard !AuthBackoffTracker.shared.shouldSkipRequest() else { return }
            do {
                let messages = try await fetchUnreadMessages()
                log("CrispManager: poll returned \(messages.count) messages (since=\(self.lastSeenTimestamp))")

                var newMessageCount = 0
                for msg in messages {
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
                        title: "Help from Founder",
                        message: preview,
                        assistantId: "crisp"
                    )
                }

                // Batch update: single @Published write instead of per-message increments
                if newMessageCount > 0 && !isViewingHelp {
                    unreadCount += newMessageCount
                }
                AuthBackoffTracker.shared.reportSuccess()
            } catch {
                if case APIError.unauthorized = error {
                    AuthBackoffTracker.shared.reportAuthFailure()
                }
                log("CrispManager: poll failed: \(error)")
            }
        }
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

    private func fetchUnreadMessages() async throws -> [CrispOperatorMessage] {
        let api = APIClient.shared
        let baseURL = await api.rustBackendURL
        let headers = try await api.buildHeaders(requireAuth: true)

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

        guard let httpResponse = response as? HTTPURLResponse else {
            throw URLError(.badServerResponse)
        }

        // 503 means Crisp is not configured - silently return empty
        if httpResponse.statusCode == 503 {
            return []
        }

        guard httpResponse.statusCode == 200 else {
            log("CrispManager: backend returned \(httpResponse.statusCode)")
            return []
        }

        let decoded = try JSONDecoder().decode(CrispUnreadResponse.self, from: data)
        return decoded.messages
    }
}
