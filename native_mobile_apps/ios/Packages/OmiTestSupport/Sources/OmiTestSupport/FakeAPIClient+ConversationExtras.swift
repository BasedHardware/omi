import Foundation
import OmiCore
import OmiNetwork

/// Backend state for summary templates, calendar links, feedback, screenshots, recordings, the
/// test prompt and the list's day/discarded queries.
public final class FakeConversationExtras: @unchecked Sendable {
    /// One entry per call, e.g. `reprocess:c1@app-1`, `link:c1>ev1`.
    public internal(set) var log: [String] = []
    /// Fails just these calls (by log prefix), leaving the rest working.
    public var failing: Set<String> = []
    public var summaryApps: [OmiApp] = [
        OmiApp(id: "app-notes", name: "Meeting Notes", description: "Decisions and owners.", author: "Omi", imageURL: nil,
               category: nil, rating: nil, installs: 0, isEnabled: true, capabilities: ["memories"]),
    ]
    public var suggestedApps: [OmiApp] = [
        OmiApp(id: "app-coach", name: "Coach", description: "How you came across.", author: "Omi", imageURL: nil,
               category: nil, rating: nil, installs: 0, isEnabled: false, capabilities: ["memories"]),
    ]
    public var preferredAppID: String?
    public var calendarEvents: [CalendarEventCandidate] = []
    public var linked: [String: CalendarEventLink] = [:]
    public var testPromptReply = "Three decisions, two owners."
    public var screenshots: [ConversationScreenshot] = []
    /// What `generate-description-emoji` answers.
    public var generated = (description: "Pulls out tasks.", emoji: "📝")
    public var feedbackPersists = true
    /// What the backend holds for a conversation's own summary after a successful `PATCH`.
    public var savedSummaries: [String: String] = [:]
    /// Two results from the same app: editing either of them fails the way the backend does.
    public var duplicateSummaryApps = false
    /// The conversation is gone: editing Omi's own summary answers 404 the way the backend does.
    public var summaryConversationGone = false
    /// What `capture-gaps` answers inside the asked window.
    public var captureGaps: [CaptureGap] = []
    /// Detail answered instead of the one built from the conversation list.
    public var details: [String: ConversationDetail] = [:]
    /// Every list query, newest last.
    public internal(set) var queries: [ConversationQuery] = []

    public init() {}
}

public extension FakeAPIClient {
    private func extra(_ kind: String, _ entry: String) throws {
        try lock.withLock {
            if let _error { throw _error }
            conversationExtras.log.append("\(kind):\(entry)")
            if conversationExtras.failing.contains(kind) { throw APIError.http(status: 500, body: kind) }
        }
    }

    func conversations(limit: Int, offset: Int, query: ConversationQuery) async throws -> [Conversation] {
        let all = try await conversations(limit: Int.max, offset: 0, filter: query.filter)
        lock.withLock { conversationExtras.queries.append(query) }
        let matching = all.filter { conversation in
            (query.includeDiscarded || !conversation.isDiscarded)
                && query.start.map { conversation.date >= $0 } ?? true
                && query.end.map { conversation.date <= $0 } ?? true
        }
        return Array(matching.dropFirst(offset).prefix(limit))
    }

    func reprocessConversation(id: String, appID: String) async throws -> ConversationDetail {
        try extra("reprocess", "\(id)@\(appID)")
        let detail = try await conversationDetail(id: id)
        var conversation = detail.conversation
        conversation.status = .completed
        return ConversationDetail(
            conversation: conversation, summaryActionItems: [], transcript: detail.transcript,
            summary: "Summary by \(appID).", summaryAppID: appID
        )
    }

    func suggestedSummaryApps(conversationID: String) async throws -> [OmiApp] {
        try extra("suggested", conversationID)
        return lock.withLock { conversationExtras.suggestedApps }
    }

    func summaryApps() async throws -> [OmiApp] {
        try extra("apps", "installed")
        return lock.withLock { conversationExtras.summaryApps }
    }

    func setPreferredSummaryApp(id: String) async throws {
        try extra("preferred", id)
        lock.withLock { conversationExtras.preferredAppID = id }
    }

    func generateAppDescription(name: String, prompt _: String) async throws -> (description: String, emoji: String) {
        try extra("describe", name)
        return lock.withLock { conversationExtras.generated }
    }

    func createSummaryApp(_ draft: SummaryTemplateDraft, description _: String, icon: Data) async throws -> String {
        try extra("create-app", "\(draft.name)|\(draft.isPublic ? "public" : "private")|\(icon.count)")
        return "app-new"
    }

    func calendarEvents(from start: Date, to end: Date) async throws -> [CalendarEventCandidate] {
        try extra("events", "list")
        return lock.withLock { conversationExtras.calendarEvents.filter { $0.end >= start && $0.start <= end } }
    }

    func linkCalendarEvent(conversationID: String, eventID: String) async throws -> CalendarEventLink {
        try extra("link", "\(conversationID)>\(eventID)")
        return try lock.withLock {
            guard let event = conversationExtras.calendarEvents.first(where: { $0.id == eventID }) else {
                throw APIError.http(status: 404, body: "event")
            }
            let link = CalendarEventLink(
                eventID: event.id, title: event.title, attendees: event.attendees,
                attendeeEmails: event.attendees.map { "\($0.lowercased())@example.com" },
                start: event.start, end: event.end, htmlLink: URL(string: "https://calendar.google.com/event?eid=\(event.id)")
            )
            conversationExtras.linked[conversationID] = link
            return link
        }
    }

    func unlinkCalendarEvent(conversationID: String) async throws {
        try extra("unlink", conversationID)
        _ = lock.withLock { conversationExtras.linked.removeValue(forKey: conversationID) }
    }

    func setEventsCreated(conversationID: String, indexes: [Int], created: Bool) async throws {
        try extra("events-created", "\(conversationID)=\(indexes.map(String.init).joined(separator: ","))=\(created)")
    }

    func sendConversationFeedback(conversationID: String, kind: ConversationFeedbackKind, helpful: Bool,
                                  reason: SummaryFeedbackReason?, feedbackID: String) async throws -> Bool
    {
        try extra("feedback", "\(conversationID)=\(kind.rawValue)=\(helpful ? 1 : -1)\(reason.map { ":\($0.rawValue)" } ?? "")")
        return lock.withLock { conversationExtras.feedbackPersists }
    }

    /// Logs `summary:<id>@<appID|own>=<content>`; fails the way the backend does for a bad app id.
    func updateConversationSummary(conversationID: String, appID: String?, content: String) async throws {
        try extra("summary", "\(conversationID)@\(appID ?? "own")=\(content)")
        if let appID {
            let duplicated = lock.withLock {
                conversationExtras.duplicateSummaryApps && conversationExtras.summaryApps.contains { $0.id == appID }
            }
            if duplicated { throw APIError.http(status: 409, body: "app_result_ambiguous") }
        }
        if let appID, lock.withLock({ !conversationExtras.summaryApps.map(\.id).contains(appID) }) {
            throw APIError.http(status: 404, body: "app_result_not_found")
        }
        if appID == nil, lock.withLock({ conversationExtras.summaryConversationGone }) {
            throw APIError.http(status: 404, body: "Conversation not found")
        }
        lock.withLock { conversationExtras.savedSummaries[conversationID] = content }
    }

    /// Calendar meetings in the window that no kept conversation covers; empty when there is none.
    func captureGaps(from start: Date, to end: Date) async throws -> [CaptureGap] {
        try extra("capture-gaps", "\(Int(start.timeIntervalSince1970))-\(Int(end.timeIntervalSince1970))")
        return lock.withLock { conversationExtras.captureGaps.filter { $0.start < end && $0.end > start } }
    }

    func testConversationPrompt(conversationID: String, prompt: String) async throws -> String {
        try extra("test-prompt", "\(conversationID)=\(prompt)")
        return lock.withLock { conversationExtras.testPromptReply }
    }

    func conversationPhoto(conversationID: String, photoID: String) async throws -> Data {
        try extra("photo", "\(conversationID)/\(photoID)")
        return Data([0x89, 0x50, 0x4E, 0x47])
    }

    func conversationScreenshots(conversationID: String) async throws -> [ConversationScreenshot] {
        try extra("screenshots", conversationID)
        return lock.withLock { conversationExtras.screenshots }
    }

    func deleteConversationScreenshot(conversationID: String, screenshotID: String) async throws -> [ConversationScreenshot] {
        try extra("delete-screenshot", "\(conversationID)/\(screenshotID)")
        return lock.withLock {
            conversationExtras.screenshots.removeAll { $0.id == screenshotID }
            return conversationExtras.screenshots
        }
    }

    func separateRecording(conversationID: String) async throws {
        try extra("separate", conversationID)
    }

    func precacheConversationAudio(id: String) async throws {
        try extra("precache", id)
    }
}
