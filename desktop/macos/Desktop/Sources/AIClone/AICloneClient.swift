import Foundation

/// Async HTTP client for the AI Clone plugin service.
///
/// Each plugin (Telegram, WhatsApp) exposes the same shape of REST API:
/// - `GET /health` — liveness, no auth
/// - `POST /setup` — register credentials, returns deep link
/// - `POST /toggle` — flip auto_reply_enabled for a chat
///
/// All authenticated endpoints require `Authorization: Bearer <token>` where
/// the token matches the plugin service's `AI_CLONE_PLUGIN_TOKEN` env var.
///
/// **Secret handling:** bot_token and access_token are treated as top-tier
/// secrets. They NEVER appear in error messages or logs. The `bodyForLogging`
/// helper returns a JSON dict with credential fields redacted.
actor AICloneClient {
    static let shared = AICloneClient()

    private let session: URLSession
    private let decoder: JSONDecoder

    init(session: URLSession = AICloneClient.makeSession(), decoder: JSONDecoder? = nil) {
        self.session = session
        let d = decoder ?? JSONDecoder()
        d.dateDecodingStrategy = .iso8601
        self.decoder = d
    }

    private static func makeSession() -> URLSession {
        let config = URLSessionConfiguration.ephemeral
        config.timeoutIntervalForRequest = 30
        config.timeoutIntervalForResource = 60
        return URLSession(configuration: config)
    }

    // MARK: - Public API

    /// `GET {baseURL}/health` — returns true if the plugin service is reachable
    /// and responding 200.
    func health(baseURL: String) async throws -> Bool {
        let url = try endpointURL(baseURL: baseURL, path: "/health")
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        let (_, response) = try await session.data(for: request)
        guard let http = response as? HTTPURLResponse else { return false }
        return http.statusCode == 200
    }

    /// `GET {baseURL}/status` response.
    ///
    /// Two plugins share the same `/status` endpoint with DIFFERENT
    /// schemas:
    ///
    /// - Bot plugin (omi-telegram-app, omi-whatsapp-app) returns
    ///   `connected_chats`, `auto_reply_enabled`, `first_chat_id`,
    ///   `bot_username`. These are the fields the desktop uses to
    ///   drive the connect sheet's handshake polling.
    ///
    /// - User-account plugin (telegram-user-account) returns
    ///   `connected`, `account_phone`, `account_name`,
    ///   `device_label`, `rate_limit`, `messages_sent_today`.
    ///   These drive the "logged in as Alice" badge and the
    ///   plan §8 rate-limit + daily-sent counter surface.
    ///
    /// All fields are optional so a single struct can decode
    /// either schema. Callers check which fields are present
    /// and adapt the UI accordingly.
    struct StatusResponse: Decodable {
        // Bot plugin fields.
        let connectedChats: Int?
        let autoReplyEnabled: Bool?
        let firstChatId: String?
        let botUsername: String?
        // User-account plugin fields.
        let connected: Bool?
        let accountPhone: String?
        let accountName: String?
        let deviceLabel: String?
        let rateLimit: RateLimitState?
        let messagesSentToday: Int?
        enum CodingKeys: String, CodingKey {
            case connectedChats = "connected_chats"
            case autoReplyEnabled = "auto_reply_enabled"
            case firstChatId = "first_chat_id"
            case botUsername = "bot_username"
            case connected
            case accountPhone = "account_phone"
            case accountName = "account_name"
            case deviceLabel = "device_label"
            case rateLimit = "rate_limit"
            case messagesSentToday = "messages_sent_today"
        }
    }

    /// Subset of the user-account plugin's `rate_limit` field in
    /// the /status response. Surfaced in the desktop's connect
    /// sheet and the plugin card so the user can see how close
    /// they are to the per-hour cap and whether Telegram has
    /// placed a temporary cooldown on the account.
    ///
    /// cubic review 4619143030 P2: nested fields are optional
    /// so a partial or drifted `rate_limit` payload (e.g. a
    /// plugin that adds a new field the desktop doesn't know
    /// about, or omits a field during a graceful degradation)
    /// does NOT fail the entire /status decode. The desktop
    /// only fills in the fields it knows about and treats
    /// the rest as missing. This matches the
    /// StatusResponse-level optionality.
    struct RateLimitState: Decodable {
        let maxPerHour: Int?
        let inWindowCount: Int?
        let isBlocked: Bool?
        let secondsUntilNextSlot: Int?
        enum CodingKeys: String, CodingKey {
            case maxPerHour = "max_per_hour"
            case inWindowCount = "in_window_count"
            case isBlocked = "is_blocked"
            case secondsUntilNextSlot = "seconds_until_next_slot"
        }
    }

    func status(baseURL: String, bearerToken: String) async throws -> StatusResponse {
        let url = try endpointURL(baseURL: baseURL, path: "/status")
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        request.setValue("Bearer \(bearerToken)", forHTTPHeaderField: "Authorization")
        let (data, response) = try await session.data(for: request)
        guard let http = response as? HTTPURLResponse, http.statusCode == 200 else {
            let code = (response as? HTTPURLResponse)?.statusCode ?? -1
            throw AICloneError.network("Plugin returned HTTP \(code)")
        }
        return try JSONDecoder().decode(StatusResponse.self, from: data)
    }

    /// `POST {baseURL}/setup` — register the user's credentials. Returns the
    /// deep link + setup token for the user to click.
    func setup(
        baseURL: String,
        bearerToken: String,
        plugin: AIPlugin,
        body: [String: Any]
    ) async throws -> SetupResponse {
        let url = try endpointURL(baseURL: baseURL, path: "/setup")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("Bearer \(bearerToken)", forHTTPHeaderField: "Authorization")
        request.httpBody = try JSONSerialization.data(withJSONObject: body)

        let (data, response) = try await session.data(for: request)
        try ensureSuccess(response: response, data: data, plugin: plugin)
        return try decoder.decode(SetupResponse.self, from: data)
    }

    /// `POST {baseURL}/toggle` — flip auto-reply on/off for a chat.
    func toggle(
        baseURL: String,
        bearerToken: String,
        plugin: AIPlugin,
        body: [String: Any]
    ) async throws -> ToggleResponse {
        let url = try endpointURL(baseURL: baseURL, path: "/toggle")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("Bearer \(bearerToken)", forHTTPHeaderField: "Authorization")
        request.httpBody = try JSONSerialization.data(withJSONObject: body)

        let (data, response) = try await session.data(for: request)
        try ensureSuccess(response: response, data: data, plugin: plugin)
        return try decoder.decode(ToggleResponse.self, from: data)
    }

    /// `POST {baseURL}/toggle` for the user-account (Telethon)
    /// plugin. Distinct from `toggle(...)` because the request body
    /// shape is different: the user-account plugin keys storage by
    /// Telegram user handle, so the body is `{handle, enabled}`
    /// (where `handle="all"` toggles every user).
    ///
    /// Response is `{auto_reply_enabled, affected_users}` (see
    /// `UserAccountToggleResponse`). The desktop's
    /// ConnectSheet.userAccountSection toggle calls this method.
    func toggleUserAccount(
        baseURL: String,
        bearerToken: String,
        enabled: Bool
    ) async throws -> UserAccountToggleResponse {
        let url = try endpointURL(baseURL: baseURL, path: "/toggle")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("Bearer \(bearerToken)", forHTTPHeaderField: "Authorization")
        let body: [String: Any] = ["handle": "all", "enabled": enabled]
        request.httpBody = try JSONSerialization.data(withJSONObject: body)
        let (data, response) = try await session.data(for: request)
        try ensureSuccess(response: response, data: data, plugin: nil)
        return try decoder.decode(UserAccountToggleResponse.self, from: data)
    }

    // MARK: - Errors

    enum AICloneError: LocalizedError {
        case invalidURL(String)
        case http(status: Int, sanitizedDetail: String)
        case decodingFailed(String)
        case notConfigured
        case network(String)

        var errorDescription: String? {
            switch self {
            case .invalidURL(let s):
                return "Invalid plugin service URL: \(s)"
            case .http(let status, let detail):
                // detail is already sanitized — no secret leak
                return "Plugin returned HTTP \(status): \(detail)"
            case .decodingFailed(let msg):
                return "Plugin returned an unexpected response: \(msg)"
            case .notConfigured:
                return "AI Clone plugin not configured. Set the Plugin Service URL and Bearer Token in Settings → AI Clone."
            case .network(let msg):
                return "Network error: \(msg)"
            }
        }
    }

    // MARK: - Internals

    static func endpointURL(baseURL: String, path: String) throws -> URL {
        // Normalize: strip trailing slashes from base, then append the path.
        // Path is expected to start with `/`; we don't add one to keep the
        // call sites self-documenting.
        let trimmed = baseURL.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        guard !trimmed.isEmpty,
              let url = URL(string: trimmed + path),
              let scheme = url.scheme?.lowercased(),
              scheme == "http" || scheme == "https"
        else {
            throw AICloneError.invalidURL("\(baseURL)\(path)")
        }
        return url
    }

    /// Validates the HTTP response. The `plugin` parameter is
    /// kept for backward compatibility but unused -- error
    /// sanitization is the same across all plugins (only the
    /// `detail` JSON field is surfaced; raw bytes are dropped).
    /// It's optional because the user-account plugin's toggle
    /// path doesn't have an AIPlugin case to pass.
    private func ensureSuccess(
        response: URLResponse, data: Data, plugin: AIPlugin? = nil
    ) throws {
        guard let http = response as? HTTPURLResponse else {
            throw AICloneError.network("non-HTTP response")
        }
        guard (200..<300).contains(http.statusCode) else {
            // Sanitize: pull only the `detail` field if it's a JSON error;
            // never include raw response bytes (which can contain the request
            // body echoed back, including secrets).
            let detail = AICloneClient.extractSanitizedDetail(from: data)
            throw AICloneError.http(status: http.statusCode, sanitizedDetail: detail)
        }
    }

    // Kept as an instance method (not static) because callers go through
    // the actor — but it forwards to the static implementation so test
    // code can exercise the URL composition without an actor instance.
    private func endpointURL(baseURL: String, path: String) throws -> URL {
        try AICloneClient.endpointURL(baseURL: baseURL, path: path)
    }

    /// Pulls the `detail` field from a JSON error body if present; returns a
    /// generic message otherwise. Never returns raw bytes (could echo back
    /// request body including bot_token / access_token). The returned string
    /// is capped at `maxDetailLength` to bound the damage if the server
    /// reflected a long secret-laden string in `detail`.
    static func extractSanitizedDetail(from data: Data) -> String {
        guard let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            return "(no detail)"
        }
        let raw: String
        if let detail = json["detail"] as? String {
            raw = detail
        } else if let msg = json["error"] as? String {
            raw = msg
        } else {
            return "(no detail)"
        }
        // Cap to prevent an over-eager server error message from surfacing
        // a reflected bot_token / access_token that happens to be in `detail`.
        if raw.count <= maxDetailLength {
            return raw
        }
        return String(raw.prefix(maxDetailLength)) + "…"
    }

    /// Max characters surfaced from a server error message before truncation.
    /// Anything longer is treated as suspect (the plugin backend caps its
    /// own error messages at ~80 chars; this is a defense-in-depth ceiling).
    private static let maxDetailLength = 200
}

// MARK: - Response models

struct SetupResponse: Decodable {
    let deepLink: String
    let setupToken: String

    // The plugin-specific extra field (phone_number_id for WhatsApp).
    let phoneNumberId: String?

    enum CodingKeys: String, CodingKey {
        case deepLink = "deep_link"
        case setupToken = "setup_token"
        case phoneNumberId = "phone_number_id"
    }
}

struct ToggleResponse: Decodable {
    let autoReplyEnabled: Bool

    enum CodingKeys: String, CodingKey {
        case autoReplyEnabled = "auto_reply_enabled"
    }
}

/// Response from the user-account plugin's `POST /toggle`.
/// Distinct from `ToggleResponse` (which is the bot plugin's
/// shape) because the user-account plugin also reports
/// `affected_users` -- the number of user records updated by the
/// handle="all" call.
struct UserAccountToggleResponse: Decodable {
    let autoReplyEnabled: Bool
    let affectedUsers: Int

    enum CodingKeys: String, CodingKey {
        case autoReplyEnabled = "auto_reply_enabled"
        case affectedUsers = "affected_users"
    }
}