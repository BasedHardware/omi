import Foundation

/// Backend transport for the Google Calendar OAuth grant — the same grant the
/// mobile app connects, held server-side.
///
/// The desktop's original Calendar path decrypts Google auth cookies out of a
/// Chromium profile. That mechanism fails for whole classes of user with no
/// recoverable action: no Chromium browser installed (Safari/Firefox), cookies
/// re-encrypted under a scheme the reader can't open, or a declined Keychain
/// "Safe Storage" prompt. See issue #10459. This transport is the durable
/// alternative — the backend already owns the token, so nothing on this machine
/// needs to read a browser at all.
/// The `app_key` path parameter for both integration routes. Kept as an
/// interpolated value rather than baked into the literal because these are the
/// templated `/v1/integrations/{app_key}` routes, not routes of their own —
/// `test_desktop_rest_inventory` extracts the literal and matches it against the
/// app-client OpenAPI spec, so a hardcoded key reads as a route the spec lacks.
private let googleCalendarAppKey = "google_calendar"

extension APIClient {
  func googleCalendarSelection(
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  ) async throws -> GoogleCalendarSelection {
    try await get("v1/calendar/google/calendars", authorizationSnapshot: authorizationSnapshot)
  }

  func saveGoogleCalendarSelection(
    accountID: String,
    selectedIDs: Set<String>,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  ) async throws -> GoogleCalendarSelection {
    let policy = try resolvedRequestAuthPolicy(expectedOwnerId: nil, authorizationSnapshot: authorizationSnapshot)
    try validateExpectedOwner(policy)
    guard let url = URL(string: baseURL + "v1/calendar/google/calendars") else { throw APIError.invalidResponse }
    var request = URLRequest(url: url)
    request.httpMethod = "PUT"
    request.httpBody = try JSONSerialization.data(withJSONObject: [
      "account_id": accountID, "selected_ids": selectedIDs.sorted(),
    ])
    request.allHTTPHeaderFields = try await buildHeaders(
      requireAuth: true, expectedAuthOwnerId: authorizationSnapshot.ownerID)
    try validateExpectedOwner(policy)
    return try await performRequest(request, authPolicy: policy)
  }
  /// Whether this account holds a live Google Calendar grant.
  func googleCalendarGrantConnected(
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil
  ) async throws -> Bool {
    let response: IntegrationConnectionResponse = try await get(
      "v1/integrations/\(googleCalendarAppKey)",
      authorizationSnapshot: authorizationSnapshot)
    return response.connected
  }

  /// Google's consent URL for the Calendar grant. The backend owns the redirect
  /// and the CSRF state, so the desktop only has to open what it returns.
  func googleCalendarOAuthURL() async throws -> URL {
    let response: IntegrationOAuthURLResponse = try await get(
      "v1/integrations/\(googleCalendarAppKey)/oauth-url")
    guard let url = URL(string: response.authUrl) else { throw APIError.invalidResponse }
    return url
  }

  /// Revoke the backend-owned Google Calendar grant for the current account.
  func disconnectGoogleCalendarGrant(
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  ) async throws {
    try await delete(
      "v1/integrations/\(googleCalendarAppKey)",
      expectedAuthOwnerId: authorizationSnapshot.ownerID,
      authorizationSnapshot: authorizationSnapshot)
  }

  /// Read events through the backend grant. Mirrors the window the cookie
  /// reader uses so both sources produce the same shape for callers.
  func googleCalendarGrantEvents(
    daysBack: Int,
    daysForward: Int,
    maxResults: Int,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil
  ) async throws -> [CalendarEvent] {
    let formatter = ISO8601DateFormatter()
    let now = Date()
    let timeMin = formatter.string(from: now.addingTimeInterval(-Double(daysBack) * 86_400))
    let timeMax = formatter.string(from: now.addingTimeInterval(Double(daysForward) * 86_400))

    func encoded(_ value: String) -> String {
      value.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? value
    }

    // The endpoint's ceiling is 500; asking for more is a 422, not a clamp.
    let capped = min(max(maxResults, 1), 500)
    let events: [GoogleCalendarGrantEvent] = try await get(
      "v1/calendar/google/events?time_min=\(encoded(timeMin))&time_max=\(encoded(timeMax))&max_results=\(capped)",
      authorizationSnapshot: authorizationSnapshot
    )
    return events.map(\.asCalendarEvent)
  }
}

struct GoogleCalendarSelection: Decodable {
  let accountID: String
  let calendars: [ReadableGoogleCalendar]
  let selectedIDs: Set<String>
  enum CodingKeys: String, CodingKey {
    case accountID = "account_id"
    case calendars
    case selectedIDs = "selected_ids"
  }
}

struct ReadableGoogleCalendar: Decodable, Identifiable {
  let id: String
  let name: String
  let primary: Bool
  let available: Bool
}

struct IntegrationConnectionResponse: Decodable {
  let connected: Bool
  let appKey: String?

  enum CodingKeys: String, CodingKey {
    case connected
    case appKey = "app_key"
  }
}

struct IntegrationOAuthURLResponse: Decodable {
  let authUrl: String

  enum CodingKeys: String, CodingKey {
    case authUrl = "auth_url"
  }
}

/// Wire shape of `GET /v1/calendar/google/events`.
struct GoogleCalendarGrantEvent: Decodable {
  let eventId: String
  let title: String
  let attendees: [String]
  let startTime: String
  let endTime: String
  let location: String
  let description: String
  let allDay: Bool

  enum CodingKeys: String, CodingKey {
    case eventId = "event_id"
    case title
    case attendees
    case startTime = "start_time"
    case endTime = "end_time"
    case location
    case description
    case allDay = "all_day"
  }

  var asCalendarEvent: CalendarEvent {
    CalendarEvent(
      id: eventId,
      summary: title,
      startTime: startTime,
      endTime: endTime,
      attendees: attendees,
      location: location,
      description: description,
      isAllDay: allDay
    )
  }
}
