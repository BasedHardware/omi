import Foundation

/// Polls the backend Crisp API endpoint for unread operator messages,
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
    private var lastSeenTimestamp: UInt64 {
        get { UInt64(UserDefaults.standard.double(forKey: "crisp_lastSeenTimestamp")) }
        set { UserDefaults.standard.set(Double(newValue), forKey: "crisp_lastSeenTimestamp") }
    }

    /// Track the latest operator message timestamp from any poll.
    /// Persisted to UserDefaults so we don't re-notify after restart.
    private var latestOperatorTimestamp: UInt64 {
        get { UInt64(UserDefaults.standard.double(forKey: "crisp_latestOperatorTimestamp")) }
        set { UserDefaults.standard.set(Double(newValue), forKey: "crisp_latestOperatorTimestamp") }
    }

    /// Track message texts we've already sent notifications for (to avoid duplicates)
    private var notifiedMessages = Set<String>()

    /// Polling timer
    private var pollTimer: Timer?

    /// Whether polling has started
    private var isStarted = false

    private init() {}

    /// Call once after sign-in to start polling for Crisp messages
    func start() {
        guard !isStarted else { return }
        isStarted = true

        // Only set lastSeenTimestamp to "now" on first-ever launch.
        // On subsequent launches, keep the persisted value so the first
        // poll picks up messages that arrived while the app was closed.
        if lastSeenTimestamp == 0 {
            lastSeenTimestamp = UInt64(Date().timeIntervalSince1970)
        }

        // Poll immediately, then every 30 seconds
        pollForMessages()
        pollTimer = Timer.scheduledTimer(withTimeInterval: 30, repeats: true) { [weak self] _ in
            Task { @MainActor in
                self?.pollForMessages()
            }
        }

        log("CrispManager: started polling for operator messages")
    }

    /// Mark messages as read (called when user opens Help tab)
    func markAsRead() {
        unreadCount = 0
        lastSeenTimestamp = latestOperatorTimestamp
    }

    /// Stop polling (called on sign-out)
    func stop() {
        pollTimer?.invalidate()
        pollTimer = nil
        isStarted = false
        unreadCount = 0
        // Clear persisted timestamps so next sign-in starts fresh
        UserDefaults.standard.removeObject(forKey: "crisp_lastSeenTimestamp")
        UserDefaults.standard.removeObject(forKey: "crisp_latestOperatorTimestamp")
        notifiedMessages.removeAll()
    }

    // MARK: - Private

    private func pollForMessages() {
        Task {
            do {
                let messages = try await fetchUnreadMessages()
                log("CrispManager: poll returned \(messages.count) messages (since=\(self.lastSeenTimestamp))")

                for msg in messages {
                    let key = String(msg.text.prefix(80)) + "_\(msg.timestamp)"

                    // Track the latest operator timestamp
                    if msg.timestamp > latestOperatorTimestamp {
                        latestOperatorTimestamp = msg.timestamp
                    }

                    // Skip if already notified
                    guard !notifiedMessages.contains(key) else { continue }
                    notifiedMessages.insert(key)

                    // Update unread count if not currently viewing help
                    if !isViewingHelp {
                        unreadCount += 1
                    }

                    // Send macOS notification
                    let preview = msg.text.count > 100 ? String(msg.text.prefix(100)) + "..." : msg.text
                    log("CrispManager: new operator message: \(preview)")

                    NotificationService.shared.sendNotification(
                        title: "Help from Founder",
                        message: preview,
                        assistantId: "crisp"
                    )
                }
            } catch {
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
        let baseURL = await api.baseURL
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
