import Foundation
import OmiCore

/// The rest of the conversation page and list: summary templates, calendar links, feedback,
/// photos and screenshots, other devices' recordings, audio parts, the developer test prompt and
/// the list's day/discarded queries. Contracts from `backend/routers/conversations.py`, `apps.py`,
/// `users.py`, `google_calendar.py`, `mobile_feedback.py`, `screen_frames.py`, `frame_requests.py`
/// and `sync.py`.
public extension APIClient {
    /// `GET v1/conversations` with discarded ones and/or a date range (`start_date`/`end_date`, inclusive).
    func conversations(limit: Int, offset: Int, query: ConversationQuery) async throws -> [Conversation] {
        var items = [
            URLQueryItem(name: "include_discarded", value: String(query.includeDiscarded)),
            URLQueryItem(name: "limit", value: String(limit)),
            URLQueryItem(name: "offset", value: String(offset)),
            URLQueryItem(name: "statuses", value: "processing,completed"),
        ]
        switch query.filter {
        case .all: break
        case .starred: items.append(URLQueryItem(name: "starred", value: "true"))
        case let .folder(id): items.append(URLQueryItem(name: "folder_id", value: id))
        }
        if let start = query.start { items.append(URLQueryItem(name: "start_date", value: Self.utc(start))) }
        if let end = query.end { items.append(URLQueryItem(name: "end_date", value: Self.utc(end))) }
        let data = try await data(.get, "v1/conversations", query: items)
        return try decode([OmiAPI.Conversation].self, from: data).map(ConversationMapper.map)
    }

    // MARK: Summary templates

    /// `POST v1/conversations/{id}/reprocess?app_id=`: summarizes again with that app only.
    func reprocessConversation(id: String, appID: String) async throws -> ConversationDetail {
        var request = try await request(.post, "v1/conversations/\(id)/reprocess", query: [URLQueryItem(name: "app_id", value: appID)])
        request.timeoutInterval = 120
        return try await ConversationMapper.detail(decode(OmiAPI.Conversation.self, from: send(request)))
    }

    /// `GET v1/conversations/{id}/suggested-apps`: the apps Omi suggests for this conversation.
    func suggestedSummaryApps(conversationID: String) async throws -> [OmiApp] {
        let object = try await JSONSerialization.jsonObject(with: data(.get, "v1/conversations/\(conversationID)/suggested-apps"))
        return ((object as? [String: Any])?["suggested_apps"] as? [[String: Any]] ?? []).compactMap(OmiApp.from)
    }

    /// `GET v2/apps/search?installed_apps=true`, kept to enabled apps that summarize conversations.
    func summaryApps() async throws -> [OmiApp] {
        let items = [
            URLQueryItem(name: "installed_apps", value: "true"),
            URLQueryItem(name: "offset", value: "0"),
            URLQueryItem(name: "limit", value: "100"),
        ]
        let object = try await JSONSerialization.jsonObject(with: data(.get, "v2/apps/search", query: items)) as? [String: Any]
        return (object?["data"] as? [[String: Any]] ?? []).compactMap(OmiApp.from)
            .filter { $0.isEnabled && $0.capabilities.contains("memories") }
    }

    /// `PUT v1/users/preferences/app?app_id=`: the app future conversations are summarized with.
    func setPreferredSummaryApp(id: String) async throws {
        _ = try await data(.put, "v1/users/preferences/app", query: [URLQueryItem(name: "app_id", value: id)])
    }

    /// `POST v1/app/generate-description-emoji`; Flutter's fallback when it fails.
    func generateAppDescription(name: String, prompt: String) async throws -> (description: String, emoji: String) {
        let body = try JSONSerialization.data(withJSONObject: ["name": name, "prompt": prompt])
        let object = try await JSONSerialization.jsonObject(with: data(.post, "v1/app/generate-description-emoji", body: .json(body)))
        let json = object as? [String: Any] ?? [:]
        let description = (json["description"] as? String).flatMap { $0.isEmpty ? nil : $0 } ?? "A custom app that \(prompt)"
        let emoji = (json["emoji"] as? String).flatMap { $0.isEmpty ? nil : $0 } ?? "✨"
        return (description, emoji)
    }

    /// `POST v1/apps` (multipart `app_data` JSON + `file` icon): a private or public summary app.
    /// Returns its id; the backend files it under review.
    func createSummaryApp(_ draft: SummaryTemplateDraft, description: String, icon: Data) async throws -> String {
        let app: [String: Any] = [
            "name": draft.name.trimmingCharacters(in: .whitespacesAndNewlines),
            "description": description,
            "capabilities": ["memories"],
            "deleted": false,
            "category": "conversation-analysis",
            "private": !draft.isPublic,
            "is_paid": false,
            "price": 0.0,
            "memory_prompt": draft.prompt.trimmingCharacters(in: .whitespacesAndNewlines),
            "thumbnails": [String](),
        ]
        let json = try String(bytes: JSONSerialization.data(withJSONObject: app), encoding: .utf8) ?? "{}"
        var request = try await request(.post, "v1/apps")
        let boundary = "omi-\(UUID().uuidString)"
        request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        var body = Data()
        body.append(Data("--\(boundary)\r\nContent-Disposition: form-data; name=\"app_data\"\r\n\r\n\(json)\r\n".utf8))
        body.append(Data("--\(boundary)\r\nContent-Disposition: form-data; name=\"file\"; filename=\"icon.png\"\r\n".utf8))
        body.append(Data("Content-Type: image/png\r\n\r\n".utf8))
        body.append(icon)
        body.append(Data("\r\n--\(boundary)--\r\n".utf8))
        request.httpBody = body
        request.timeoutInterval = 60
        let object = try await JSONSerialization.jsonObject(with: send(request)) as? [String: Any]
        guard let id = object?["app_id"] as? String else { throw APIError.decoding("app_id") }
        return id
    }

    // MARK: Calendar

    /// `GET v1/calendar/google/events` between two times (30 at most).
    func calendarEvents(from start: Date, to end: Date) async throws -> [CalendarEventCandidate] {
        let items = [
            URLQueryItem(name: "max_results", value: "30"),
            URLQueryItem(name: "time_min", value: Self.utc(start)),
            URLQueryItem(name: "time_max", value: Self.utc(end)),
        ]
        let array = try await JSONSerialization.jsonObject(with: data(.get, "v1/calendar/google/events", query: items)) as? [[String: Any]]
        return (array ?? []).compactMap(CalendarMapper.candidate)
    }

    /// `POST v1/conversations/{id}/calendar-event` `{event_id}`: links it (and writes the
    /// conversation's link into the event).
    func linkCalendarEvent(conversationID: String, eventID: String) async throws -> CalendarEventLink {
        let body = try JSONSerialization.data(withJSONObject: ["event_id": eventID])
        let data = try await data(.post, "v1/conversations/\(conversationID)/calendar-event", body: .json(body))
        guard let link = try ConversationMapper.calendarEvent(decode(OmiAPI.CalendarEventLink.self, from: data)) else {
            throw APIError.decoding("calendar_event")
        }
        return link
    }

    /// `DELETE v1/conversations/{id}/calendar-event`.
    func unlinkCalendarEvent(conversationID: String) async throws {
        _ = try await data(.delete, "v1/conversations/\(conversationID)/calendar-event")
    }

    /// `PATCH v1/conversations/{id}/events` `{events_idx, values}`: marks found events as added.
    func setEventsCreated(conversationID: String, indexes: [Int], created: Bool) async throws {
        let body = try JSONSerialization.data(withJSONObject: ["events_idx": indexes, "values": indexes.map { _ in created }])
        _ = try await data(.patch, "v1/conversations/\(conversationID)/events", body: .json(body))
    }

    // MARK: Test prompt

    /// `POST v1/conversations/{id}/test-prompt` `{prompt}`: one summary with this prompt, not saved.
    func testConversationPrompt(conversationID: String, prompt: String) async throws -> String {
        let body = try JSONSerialization.data(withJSONObject: ["prompt": prompt])
        var request = try await request(.post, "v1/conversations/\(conversationID)/test-prompt", body: .json(body))
        request.timeoutInterval = 120
        let object = try await JSONSerialization.jsonObject(with: send(request)) as? [String: Any]
        return object?["summary"] as? String ?? ""
    }

    // MARK: Photos, screenshots

    /// `GET v1/conversations/{id}/photos/{photo_id}/image`: a stored photo's bytes.
    func conversationPhoto(conversationID: String, photoID: String) async throws -> Data {
        try await data(.get, "v1/conversations/\(conversationID)/photos/\(photoID)/image")
    }

    /// `GET v1/conversations/{id}/screenshots`: banner first, then the strip.
    func conversationScreenshots(conversationID: String) async throws -> [ConversationScreenshot] {
        try await ScreenshotMapper.map(JSONSerialization.jsonObject(with: data(.get, "v1/conversations/\(conversationID)/screenshots")))
    }

    /// `DELETE v1/conversations/{id}/screenshots/{frame_id}`; returns what is left.
    func deleteConversationScreenshot(conversationID: String, screenshotID: String) async throws -> [ConversationScreenshot] {
        try await ScreenshotMapper.map(
            JSONSerialization.jsonObject(with: data(.delete, "v1/conversations/\(conversationID)/screenshots/\(screenshotID)"))
        )
    }

    // MARK: Recordings, audio

    /// `POST v1/conversations/{id}/capture-group/separate`: that recording leaves its group for good.
    func separateRecording(conversationID: String) async throws {
        _ = try await data(.post, "v1/conversations/\(conversationID)/capture-group/separate")
    }

    /// `POST v1/sync/audio/{id}/precache`: builds the playback files in the background.
    func precacheConversationAudio(id: String) async throws {
        _ = try await data(.post, "v1/sync/audio/\(id)/precache")
    }

    // MARK: Helpers

    /// Sends a prepared request (custom timeout or body) with the usual status check.
    private func send(_ request: URLRequest) async throws -> Data {
        let (data, response): (Data, URLResponse)
        do {
            (data, response) = try await session.data(for: request)
        } catch {
            throw APIError.transport(error.localizedDescription)
        }
        let status = (response as? HTTPURLResponse)?.statusCode ?? 0
        guard (200 ..< 300).contains(status) else {
            throw APIError.http(status: status, body: String(bytes: data.prefix(500), encoding: .utf8) ?? "")
        }
        return data
    }

    internal static func utc(_ date: Date) -> String {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime]
        return formatter.string(from: date)
    }
}

enum CalendarMapper {
    static func candidate(_ json: [String: Any]) -> CalendarEventCandidate? {
        guard let id = json["event_id"] as? String,
              let start = BackendDate.parse(json["start_time"] as? String),
              let end = BackendDate.parse(json["end_time"] as? String) else { return nil }
        return CalendarEventCandidate(
            id: id, title: json["title"] as? String ?? "", start: start, end: end, attendees: json["attendees"] as? [String] ?? []
        )
    }
}

enum ScreenshotMapper {
    /// `ConversationScreenFrameSet`: the banner, then the strip by rank.
    static func map(_ object: Any) -> [ConversationScreenshot] {
        guard let json = object as? [String: Any] else { return [] }
        let banner = (json["banner"] as? [String: Any]).map { [$0] } ?? []
        let strip = (json["strip"] as? [[String: Any]] ?? []).sorted { ($0["rank"] as? Int ?? 0) < ($1["rank"] as? Int ?? 0) }
        return (banner + strip).compactMap { frame in
            guard let id = frame["id"] as? String else { return nil }
            return ConversationScreenshot(
                id: id,
                caption: frame["caption"] as? String ?? "",
                imageURL: (frame["content_url"] as? String).flatMap(URL.init(string:)),
                thumbnailURL: (frame["thumbnail_url"] as? String).flatMap(URL.init(string:)),
                capturedAt: BackendDate.parse(frame["captured_at"] as? String)
            )
        }
    }
}
