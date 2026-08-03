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
    guard maxResults > 0 else { return [] }
    var ids: [String] = []
    var pageToken: String?
    repeat {
      guard var components = URLComponents(url: messagesURL, resolvingAgainstBaseURL: false) else {
        throw GoogleOAuthReaderError.network("Could not construct the Gmail request.")
      }
      var queryItems = [
        URLQueryItem(name: "maxResults", value: "\(min(maxResults, 500))"),
        URLQueryItem(name: "q", value: query),
      ]
      if let pageToken {
        queryItems.append(URLQueryItem(name: "pageToken", value: pageToken))
      }
      components.queryItems = queryItems
      guard let url = components.url else {
        throw GoogleOAuthReaderError.network("Could not construct the Gmail request.")
      }
      let body = try await get(url, token: token, session: session)
      ids.append(contentsOf: (body["messages"] as? [[String: Any]] ?? []).compactMap { $0["id"] as? String })
      pageToken = body["nextPageToken"] as? String
    } while ids.count < maxResults && pageToken != nil

    let requestedIDs = Array(ids.prefix(maxResults))
    var emails: [GmailEmail] = []
    var nextIndex = 0
    try await withThrowingTaskGroup(of: GmailEmail?.self) { group in
      func addTask(for id: String) {
        group.addTask {
          do {
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
            return parseMessage(detail)
          } catch let error as GoogleOAuthReaderError {
            if case .http(404) = error { return nil }
            throw error
          }
        }
      }

      for _ in 0..<min(8, requestedIDs.count) {
        addTask(for: requestedIDs[nextIndex])
        nextIndex += 1
      }
      while let email = try await group.next() {
        if let email { emails.append(email) }
        guard nextIndex < requestedIDs.count else { continue }
        addTask(for: requestedIDs[nextIndex])
        nextIndex += 1
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
      from: headers["from"] ?? "",
      subject: headers["subject"] ?? "(no subject)",
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
      result[name.lowercased()] = value
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
    var pageToken: String?
    var events: [CalendarEvent] = []
    repeat {
      guard var components = URLComponents(url: eventsURL, resolvingAgainstBaseURL: false) else {
        throw GoogleOAuthReaderError.network("Could not construct the Calendar request.")
      }
      var queryItems = [
        URLQueryItem(name: "timeMin", value: timeMin),
        URLQueryItem(name: "timeMax", value: timeMax),
        URLQueryItem(name: "maxResults", value: "\(min(maxResults, 2500))"),
        URLQueryItem(name: "singleEvents", value: "true"),
        URLQueryItem(name: "orderBy", value: "startTime"),
      ]
      if let pageToken {
        queryItems.append(URLQueryItem(name: "pageToken", value: pageToken))
      }
      components.queryItems = queryItems
      guard let url = components.url else {
        throw GoogleOAuthReaderError.network("Could not construct the Calendar request.")
      }
      let body = try await GoogleOAuthGmailReader.get(url, token: token, session: session)
      events.append(contentsOf: (body["items"] as? [[String: Any]] ?? []).compactMap(parseEvent))
      pageToken = body["nextPageToken"] as? String
    } while events.count < maxResults && pageToken != nil
    return Array(events.prefix(maxResults)).sorted { $0.startTime > $1.startTime }
  }

  static func parseEvent(_ dict: [String: Any]) -> CalendarEvent? {
    guard let id = dict["id"] as? String else {
      return nil
    }
    let summary = (dict["summary"] as? String) ?? "Untitled"
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
      let date = Self.parseDateTime(raw)
    else {
      return ""
    }
    let formatter = DateFormatter()
    formatter.locale = Locale(identifier: "en_US_POSIX")
    formatter.dateFormat = "yyyy-MM-dd'T'HH:mm:ss'Z'"
    formatter.timeZone = TimeZone(identifier: "UTC")
    return formatter.string(from: date)
  }

  /// Google `dateTime` strings can carry fractional seconds; the default
  /// ISO8601 formatter rejects them, which silently dropped the event times.
  private static func parseDateTime(_ raw: String) -> Date? {
    let fractional = ISO8601DateFormatter()
    fractional.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    if let date = fractional.date(from: raw) { return date }
    return ISO8601DateFormatter().date(from: raw)
  }

  static func attendees(_ raw: [[String: Any]]) -> [String] {
    raw.compactMap {
      guard !($0["self"] as? Bool ?? false) else { return nil }
      return ($0["displayName"] as? String) ?? ($0["email"] as? String)
    }
  }
}
