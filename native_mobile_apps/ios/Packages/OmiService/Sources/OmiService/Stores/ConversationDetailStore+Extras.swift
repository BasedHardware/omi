import Foundation
import OmiCore
import OmiNetwork

/// The detail page's other actions: staying current while the backend processes, the linked
/// calendar event, events added to a calendar, photos, other devices' recordings and the
/// developer test prompt.
public extension ConversationDetailStore {
    /// Loads again without the loading state (a failure keeps what is shown).
    func refresh() async {
        if let fresh = try? await api.conversationDetail(id: preview.id) { detail = fresh }
    }

    /// Reloads every `interval` while the conversation is processing, at most `attempts` times
    /// (Flutter's activity strip: 5 s, 36 times). Returns when it is done or the task is cancelled.
    func followProcessing(in list: ConversationsStore, interval: Duration = .seconds(5), attempts: Int = 36) async {
        for _ in 0 ..< attempts {
            guard conversation.status == .processing || conversation.status == .inProgress, !Task.isCancelled else { return }
            try? await Task.sleep(for: interval)
            guard !Task.isCancelled else { return }
            await refresh()
            list.remember(conversation)
        }
    }

    // MARK: Calendar

    /// Google Calendar is connected (linking needs it).
    func isCalendarConnected() async -> Bool {
        await (try? api.integrationConnected("google_calendar")) ?? false
    }

    /// Events from two hours before to two hours after the conversation (an hour long if it has no end).
    func calendarCandidates() async -> [CalendarEventCandidate]? {
        let (start, end) = window
        return try? await api.calendarEvents(from: start.addingTimeInterval(-7200), to: end.addingTimeInterval(7200))
    }

    /// When the conversation ran, for the "Suggested" event.
    var window: (start: Date, end: Date) {
        let start = conversation.startedAt ?? conversation.createdAt
        return (start, conversation.finishedAt ?? start.addingTimeInterval(3600))
    }

    @discardableResult
    func linkCalendarEvent(_ eventID: String) async -> CalendarEventLink? {
        guard let link = try? await api.linkCalendarEvent(conversationID: conversation.id, eventID: eventID) else { return nil }
        detail?.calendarEvent = link
        return link
    }

    /// Optimistic; the link comes back if the backend refuses.
    @discardableResult
    func unlinkCalendarEvent() async -> Bool {
        let old = detail?.calendarEvent
        detail?.calendarEvent = nil
        do {
            try await api.unlinkCalendarEvent(conversationID: conversation.id)
            return true
        } catch {
            detail?.calendarEvent = old
            return false
        }
    }

    /// An event Omi found was added to the user's calendar (`created`).
    func markEventAdded(_ index: Int) async {
        guard let events = detail?.events, events.indices.contains(index), !events[index].isCreated else { return }
        detail?.events[index].isCreated = true
        do {
            try await api.setEventsCreated(conversationID: conversation.id, indexes: [index], created: true)
        } catch {
            detail?.events[index].isCreated = false
        }
    }

    // MARK: Photos, recordings, test prompt

    /// A photo's image: inline bytes, else fetched (stored photos).
    func image(for photo: ConversationPhoto) async -> Data? {
        if let data = photo.data { return data }
        guard photo.isStored else { return nil }
        return try? await api.conversationPhoto(conversationID: conversation.id, photoID: photo.id)
    }

    /// Takes a recording out of this conversation's group for good, then reloads the page and the list.
    @discardableResult
    func separate(_ recording: CaptureRecording, in list: ConversationsStore) async -> Bool {
        do {
            try await api.separateRecording(conversationID: recording.id)
        } catch {
            return false
        }
        await refresh()
        await list.load()
        return true
    }

    /// A store for another conversation (a recording of the same moment) on the same client.
    func sibling(_ conversation: Conversation) -> ConversationDetailStore {
        ConversationDetailStore(preview: conversation, api: api)
    }

    /// Runs `prompt` over the transcript once (nothing saved); `nil` when it failed.
    func testPrompt(_ prompt: String) async -> String? {
        let prompt = prompt.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !prompt.isEmpty else { return nil }
        guard let summary = try? await api.testConversationPrompt(conversationID: conversation.id, prompt: prompt) else { return nil }
        return summary.replacingOccurrences(of: "**", with: "")
    }
}
