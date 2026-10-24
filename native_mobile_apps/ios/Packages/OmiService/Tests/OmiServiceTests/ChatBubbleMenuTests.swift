import Foundation
import OmiCore
@testable import OmiService
import OmiTestSupport
import Testing

/// What the bubbles' long-press menu does: reply with a quote, delete on this iPhone, try again,
/// and the day dividers' names.
@MainActor
struct ChatBubbleMenuTests {
    @Test func aReplyGoesOutWithItsQuote() async {
        let api = FakeAPIClient()
        api.existingSessions = [("main", "Chat")]
        let chat = ChatStore(api: api, preferences: freshPreferences())
        await chat.loadHistory()
        chat.replyingTo = chat.messages.first
        chat.send("  Thanks!  ")
        await chat.streamTask?.value
        #expect(api.chatExtras.sentTexts == ["> Omi: Hi! How can I help?\n\nThanks!"])
        #expect(chat.replyingTo == nil)
        // The thread shows the question with its quote drawn apart.
        let question = chat.messages.first { $0.sender == .user }
        #expect(ChatQuote.split(question?.text ?? "").body == "Thanks!")
    }

    @Test func nothingTypedSendsNothingAndKeepsTheReply() {
        let chat = ChatStore(api: FakeAPIClient(), preferences: freshPreferences())
        let target = ChatMessage(id: "a", text: "Hi", sender: .omi, createdAt: .now)
        chat.replyingTo = target
        chat.send("   ")
        #expect(chat.messages.isEmpty)
        #expect(chat.replyingTo == target)
    }

    @Test func aDeletedMessageStaysHiddenOnTheNextLoad() async {
        let api = FakeAPIClient()
        api.existingSessions = [("main", "Chat")]
        api.chatArchive = [
            ChatMessage(id: "q", text: "What's on today?", sender: .user, createdAt: Fixtures.now.addingTimeInterval(-60)),
            ChatMessage(id: "a", text: "Lunch at 1.", sender: .omi, createdAt: Fixtures.now),
        ]
        let preferences = freshPreferences()
        let chat = ChatStore(api: api, preferences: preferences)
        await chat.loadHistory()
        chat.replyingTo = chat.messages.last
        chat.hide("a")
        #expect(chat.messages.map(\.id) == ["q"])
        #expect(chat.replyingTo == nil)

        let again = ChatStore(api: api, preferences: preferences)
        await again.loadHistory()
        #expect(again.messages.map(\.id) == ["q"])
    }

    @Test func onlyAFailedAnswerOffersTryAgain() {
        let chat = ChatStore(api: FakeAPIClient(), preferences: freshPreferences())
        chat.messages = [
            ChatMessage(id: "q1", text: "One", sender: .user, createdAt: .now),
            ChatMessage(id: "a1", text: "", sender: .omi, createdAt: .now, failure: .offline),
            ChatMessage(id: "q2", text: "Two", sender: .user, createdAt: .now),
            ChatMessage(id: "a2", text: "Fine.", sender: .omi, createdAt: .now),
            ChatMessage(id: "q3", text: "Three", sender: .user, createdAt: .now),
            ChatMessage(id: "a3", text: "Half", sender: .omi, createdAt: .now, failure: .stopped),
        ]
        #expect(chat.failedAnswer(after: "q1")?.id == "a1")
        #expect(chat.failedAnswer(after: "q2") == nil)
        #expect(chat.failedAnswer(after: "q3") == nil)
        #expect(chat.failedAnswer(after: "a1") == nil)
    }

    @Test func daysAreNamedRelativeToToday() throws {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = try #require(TimeZone(identifier: "Europe/Berlin"))
        let now = try #require(calendar.date(from: DateComponents(year: 2026, month: 10, day: 8, hour: 9)))
        func day(_ offset: Int, hour: Int = 22) throws -> Date {
            let date = try #require(calendar.date(byAdding: .day, value: -offset, to: now))
            return try #require(calendar.date(bySettingHour: hour, minute: 0, second: 0, of: date))
        }
        #expect(try ChatDay(day(0, hour: 0), now: now, calendar: calendar) == .today)
        #expect(try ChatDay(day(1), now: now, calendar: calendar) == .yesterday)
        let threeDaysAgo = try day(3)
        #expect(ChatDay(threeDaysAgo, now: now, calendar: calendar) == .weekday(calendar.startOfDay(for: threeDaysAgo)))
        let lastMonth = try day(30)
        #expect(ChatDay(lastMonth, now: now, calendar: calendar) == .date(calendar.startOfDay(for: lastMonth), showsYear: false))
        let lastYear = try day(400)
        #expect(ChatDay(lastYear, now: now, calendar: calendar) == .date(calendar.startOfDay(for: lastYear), showsYear: true))
    }
}
