import Foundation

enum GoogleOAuthReaderError: LocalizedError {
  case reconnectRequired
  case http(Int)
  case network(String)

  var errorDescription: String? {
    switch self {
    case .reconnectRequired:
      return "This Google connection needs to be reconnected."
    case .http(let status):
      return "Google returned HTTP \(status)."
    case .network(let detail):
      return "Network error: \(detail)"
    }
  }
}

/// Gmail reads over the Google API with a grant's access token. Message
/// metadata only — subject and sender, never bodies.
enum GoogleOAuthGmailReader {
  static let messagesURL = URL(
    // swiftlint:disable:next force_unwrapping — fixed literal cannot fail
    string: "https://gmail.googleapis.com/gmail/v1/users/me/messages")!

  static func readRecentEmails(
    token: String,
    maxResults: Int = 50,
    query: String = "newer_than:1d",
    session: URLSession = .shared
  ) async throws -> [GmailEmail] {
    // swiftlint:disable:next force_unwrapping — fixed endpoint constant cannot fail
    var components = URLComponents(url: messagesURL, resolvingAgainstBaseURL: false)!
    components.queryItems = [
      URLQueryItem(name: "maxResults", value: "\(maxResults)"),
      URLQueryItem(name: "q", value: query),
    ]
    // swiftlint:disable:next force_unwrapping — fixed components cannot fail
    let body = try await get(components.url!, token: token, session: session)
    let ids =
      (body["messages"] as? [[String: Any]] ?? [])
      .compactMap { $0["id"] as? String }
    var emails: [GmailEmail] = []
    for id in ids.prefix(maxResults) {
      let detail = try await get(
        messagesURL.appendingPathComponent(id).appending(
          queryItems: [
            URLQueryItem(name: "format", value: "metadata"),
            URLQueryItem(name: "metadataHeaders", value: "Subject"),
            URLQueryItem(name: "metadataHeaders", value: "From"),
          ]),
        token: token,
        session: session
      )
      if let email = parseMessage(detail) {
        emails.append(email)
      }
    }
    return emails.sorted { $0.date > $1.date }
  }

  static func parseMessage(_ body: [String: Any]) -> GmailEmail? {
    guard let id = body["id"] as? String else { return nil }
    let headers = headers(from: body["payload"] as? [String: Any])
    let millis = Double(body["internalDate"] as? String ?? "")
    return GmailEmail(
      id: id,
      from: headers["From"] ?? "",
      subject: headers["Subject"] ?? "(no subject)",
      snippet: body["snippet"] as? String ?? "",
      date: millis.map { Date(timeIntervalSince1970: $0 / 1000) } ?? Date(),
      isUnread: (body["labelIds"] as? [String])?.contains("UNREAD") ?? false
    )
  }

  static func headers(from payload: [String: Any]?) -> [String: String] {
    guard let headers = payload?["headers"] as? [[String: Any]] else {
      return [:]
    }
    var result: [String: String] = [:]
    for header in headers {
      guard let name = header["name"] as? String,
        let value = header["value"] as? String
      else {
        continue
      }
      result[name] = value
    }
    return result
  }

  static func get(
    _ url: URL, token: String, session: URLSession
  ) async throws -> [String: Any] {
    var request = URLRequest(url: url)
    request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
    request.setValue("application/json", forHTTPHeaderField: "Accept")
    do {
      let (data, response) = try await session.data(for: request)
      let status = (response as? HTTPURLResponse)?.statusCode ?? 0
      if status == 401 || status == 403 {
        throw GoogleOAuthReaderError.reconnectRequired
      }
      guard status >= 200 && status < 300 else {
        throw GoogleOAuthReaderError.http(status)
      }
      return (try? JSONSerialization.jsonObject(with: data)) as? [String: Any] ?? [:]
    } catch let error as GoogleOAuthReaderError {
      throw error
    } catch {
      throw GoogleOAuthReaderError.network(error.localizedDescription)
    }
  }
}

/// Calendar reads over the Google API with a grant's access token. Title,
/// time, attendees, location, and description — nothing writes.
enum GoogleOAuthCalendarReader {
  static let eventsURL = URL(
    // swiftlint:disable:next force_unwrapping — fixed literal cannot fail
    string: "https://www.googleapis.com/calendar/v3/calendars/primary/events")!

  static func readEvents(
    token: String,
    daysBack: Int = 90,
    daysForward: Int = 14,
    maxResults: Int = 200,
    session: URLSession = .shared
  ) async throws -> [CalendarEvent] {
    let now = Date()
    let iso = ISO8601DateFormatter()
    let timeMin = iso.string(
      from: now.addingTimeInterval(-Double(daysBack) * 86_400))
    let timeMax = iso.string(
      from: now.addingTimeInterval(Double(daysForward) * 86_400))
    // swiftlint:disable:next force_unwrapping — fixed endpoint constant cannot fail
    var components = URLComponents(url: eventsURL, resolvingAgainstBaseURL: false)!
    components.queryItems = [
      URLQueryItem(name: "timeMin", value: timeMin),
      URLQueryItem(name: "timeMax", value: timeMax),
      URLQueryItem(name: "maxResults", value: "\(maxResults)"),
      URLQueryItem(name: "singleEvents", value: "true"),
      URLQueryItem(name: "orderBy", value: "startTime"),
    ]
    let body = try await GoogleOAuthGmailReader.get(
      // swiftlint:disable:next force_unwrapping — fixed components cannot fail
      components.url!, token: token, session: session)
    let events =
      (body["items"] as? [[String: Any]] ?? []).compactMap(parseEvent)
    return events.sorted { $0.startTime > $1.startTime }
  }

  static func parseEvent(_ dict: [String: Any]) -> CalendarEvent? {
    guard let id = dict["id"] as? String,
      let summary = dict["summary"] as? String
    else {
      return nil
    }
    let start = dict["start"] as? [String: Any] ?? [:]
    let end = dict["end"] as? [String: Any] ?? [:]
    let isAllDay = start["date"] is String
    return CalendarEvent(
      id: id,
      summary: summary,
      startTime: Self.timeString(start, allDay: isAllDay),
      endTime: Self.timeString(end, allDay: isAllDay),
      attendees: Self.attendees(dict["attendees"] as? [[String: Any]] ?? []),
      location: dict["location"] as? String ?? "",
      description: dict["description"] as? String ?? "",
      isAllDay: isAllDay
    )
  }

  static func timeString(_ start: [String: Any], allDay: Bool) -> String {
    if allDay {
      return start["date"] as? String ?? ""
    }
    guard let raw = start["dateTime"] as? String,
      let date = ISO8601DateFormatter().date(from: raw)
    else {
      return ""
    }
    let formatter = DateFormatter()
    formatter.locale = Locale(identifier: "en_US_POSIX")
    formatter.dateFormat = "yyyy-MM-dd'T'HH:mm:ss'Z'"
    formatter.timeZone = TimeZone(identifier: "UTC")
    return formatter.string(from: date)
  }

  static func attendees(_ raw: [[String: Any]]) -> [String] {
    raw.compactMap {
      ($0["displayName"] as? String) ?? ($0["email"] as? String)
    }
  }
}
