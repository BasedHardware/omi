import Foundation
import OmiCore

/// A verified caller ID (`GET v1/phone/numbers`): the number people you call see.
public struct VerifiedPhoneNumber: Identifiable, Hashable, Sendable {
    public let id: String
    /// E.164, e.g. `+15551234567`.
    public let phoneNumber: String
    public let verifiedAt: Date?
    public let isPrimary: Bool

    public init(id: String, phoneNumber: String, verifiedAt: Date?, isPrimary: Bool) {
        self.id = id
        self.phoneNumber = phoneNumber
        self.verifiedAt = verifiedAt
        self.isPrimary = isPrimary
    }
}

/// `POST v1/phone/numbers/verify`: Twilio calls the number; the person types `validationCode`.
public struct PhoneVerification: Hashable, Sendable {
    public let phoneNumber: String
    public let validationCode: String?
    /// Twilio's status; `verified` when the number already was.
    public let status: String

    public init(phoneNumber: String, validationCode: String?, status: String) {
        self.phoneNumber = phoneNumber
        self.validationCode = validationCode
        self.status = status
    }
}

/// `POST v1/phone/token`: a Twilio Voice access token for one call.
public struct PhoneCallToken: Hashable, Sendable {
    public let accessToken: String
    public let ttl: Int
    public let identity: String

    public init(accessToken: String, ttl: Int, identity: String) {
        self.accessToken = accessToken
        self.ttl = ttl
        self.identity = identity
    }
}

/// `phone_call_quota` of `GET v1/users/me/subscription` (backend `models/users.py` `PhoneCallQuota`).
public struct PhoneCallQuota: Hashable, Sendable {
    public let hasAccess: Bool
    public let isPaid: Bool
    /// `nil` unlimited, `0` calling is off for the plan.
    public let monthlyLimit: Int?
    public let monthlyUsed: Int
    public let remaining: Int?
    public let maxDurationSeconds: Int?

    public init(hasAccess: Bool, isPaid: Bool, monthlyLimit: Int?, monthlyUsed: Int, remaining: Int?, maxDurationSeconds: Int?) {
        self.hasAccess = hasAccess
        self.isPaid = isPaid
        self.monthlyLimit = monthlyLimit
        self.monthlyUsed = monthlyUsed
        self.remaining = remaining
        self.maxDurationSeconds = maxDurationSeconds
    }
}

/// The reason in a FastAPI error body. Phone endpoints answer with a string, the quota error with a
/// map (`check_call_access` in `backend/utils/phone_calls.py`); Flutter `errorDetailMessage`.
public enum PhoneCallErrorDetail: Equatable, Sendable {
    case message(String)
    case quotaExceeded(monthlyLimit: Int?)

    public init?(body: String) {
        guard let data = body.data(using: .utf8),
              let object = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any] else { return nil }
        if let text = object["detail"] as? String {
            let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !trimmed.isEmpty else { return nil }
            self = .message(trimmed)
        } else if let map = object["detail"] as? [String: Any], let code = map["error"] as? String {
            self = code == "phone_call_quota_exceeded" ? .quotaExceeded(monthlyLimit: map["monthly_limit"] as? Int) : .message(code)
        } else {
            return nil
        }
    }
}

/// Phone calls through Omi's Twilio number service. Contract: `backend/routers/phone_calls.py`,
/// Flutter `app/lib/backend/http/api/phone_calls.dart`.
public extension APIClient {
    /// `GET v1/phone/numbers`.
    func verifiedPhoneNumbers() async throws -> [VerifiedPhoneNumber] {
        let object = try await phoneObject(.get, "v1/phone/numbers")
        return (object["numbers"] as? [[String: Any]] ?? []).compactMap { item in
            guard let id = item["id"] as? String, let number = item["phone_number"] as? String else { return nil }
            let verifiedAt = (item["verified_at"] as? String).flatMap(Self.parsePhoneDate)
            return VerifiedPhoneNumber(id: id, phoneNumber: number, verifiedAt: verifiedAt, isPrimary: item["is_primary"] as? Bool ?? false)
        }
    }

    /// `POST v1/phone/numbers/verify` (rate limited: 5 an hour).
    func startPhoneVerification(phoneNumber: String) async throws -> PhoneVerification {
        let object = try await phoneObject(.post, "v1/phone/numbers/verify", json: ["phone_number": phoneNumber])
        return PhoneVerification(
            phoneNumber: object["phone_number"] as? String ?? phoneNumber,
            validationCode: (object["validation_code"] as? String).flatMap { $0.isEmpty ? nil : $0 },
            status: object["status"] as? String ?? ""
        )
    }

    /// `POST v1/phone/numbers/verify/check`: `true` once the code was entered on the call (poll it).
    func checkPhoneVerification(phoneNumber: String) async throws -> Bool {
        let object = try await phoneObject(.post, "v1/phone/numbers/verify/check", json: ["phone_number": phoneNumber])
        return object["verified"] as? Bool ?? false
    }

    /// `DELETE v1/phone/numbers/{id}`.
    func deletePhoneNumber(id: String) async throws {
        _ = try await phoneObject(.delete, "v1/phone/numbers/\(id)")
    }

    /// `POST v1/phone/token`.
    func phoneCallToken() async throws -> PhoneCallToken {
        let object = try await phoneObject(.post, "v1/phone/token")
        guard let token = object["access_token"] as? String else { throw APIError.decoding("phone token without access_token") }
        return PhoneCallToken(accessToken: token, ttl: object["ttl"] as? Int ?? 3600, identity: object["identity"] as? String ?? "")
    }

    /// The `phone_call_quota` of `GET v1/users/me/subscription`.
    func phoneCallQuota() async throws -> PhoneCallQuota? {
        let object = try await phoneObject(.get, "v1/users/me/subscription")
        guard let quota = object["phone_call_quota"] as? [String: Any] else { return nil }
        return PhoneCallQuota(
            hasAccess: quota["has_access"] as? Bool ?? false,
            isPaid: quota["is_paid"] as? Bool ?? false,
            monthlyLimit: quota["monthly_limit"] as? Int,
            monthlyUsed: quota["monthly_used"] as? Int ?? 0,
            remaining: quota["remaining"] as? Int,
            maxDurationSeconds: quota["max_duration_seconds"] as? Int
        )
    }

    /// Past calls: the conversations the call transcripts became (`GET v1/conversations?sources=phone_call`).
    func phoneCallConversations(limit: Int, offset: Int) async throws -> [Conversation] {
        let query = [
            URLQueryItem(name: "include_discarded", value: "false"),
            URLQueryItem(name: "limit", value: String(limit)),
            URLQueryItem(name: "offset", value: String(offset)),
            URLQueryItem(name: "statuses", value: "processing,completed"),
            URLQueryItem(name: "sources", value: "phone_call"),
        ]
        let data = try await data(.get, "v1/conversations", query: query)
        return try decode([OmiAPI.Conversation].self, from: data).map(ConversationMapper.map)
    }

    /// The call's two-channel transcription stream (`/v4/listen?source=phone_call&channels=2`).
    func openPhoneCallSocket(uid: String, callID: String, language: String) async throws -> any PhoneCallTranscriptChannel {
        var request = URLRequest(url: PhoneCallSocket.url(base: configuration.apiBaseURL, uid: uid, callID: callID, language: language))
        let token = try await tokens.idToken(forceRefresh: false)
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        request.setValue("ios", forHTTPHeaderField: "X-App-Platform")
        request.setValue(configuration.appVersion, forHTTPHeaderField: "X-App-Version")
        let socket = PhoneCallSocket(request: request, session: session)
        socket.open()
        return socket
    }

    private func phoneObject(_ method: Method, _ path: String, json: [String: Any]? = nil) async throws -> [String: Any] {
        let body: Body = try json.map { try .json(JSONSerialization.data(withJSONObject: $0)) } ?? .none
        let data = try await data(method, path, body: body)
        return (try? JSONSerialization.jsonObject(with: data) as? [String: Any]) ?? [:]
    }

    /// `verified_at` is Python `isoformat()`: `2026-10-01T10:00:00.123456+00:00`.
    internal static func parsePhoneDate(_ text: String) -> Date? {
        let fractional = ISO8601DateFormatter()
        fractional.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let date = fractional.date(from: text) { return date }
        // Microseconds (6 digits) are more than the formatter reads; drop the fraction.
        let trimmed = text.replacingOccurrences(of: #"\.\d+"#, with: "", options: .regularExpression)
        return ISO8601DateFormatter().date(from: trimmed)
    }
}
