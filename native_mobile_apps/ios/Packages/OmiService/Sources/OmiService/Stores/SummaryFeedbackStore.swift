import CryptoKit
import Foundation
import Observation
import OmiCore
import OmiNetwork
import OmiPersistence

/// "Was this helpful?" under Omi's own summary, or "What issues did you experience?" about a finished
/// recording (Flutter `SummaryFeedbackPrompt`, `RecordingQualityFeedbackPrompt` and
/// `FeedbackPromptPolicy`): one question per conversation, a quarter of conversations, at most once
/// a week across both questions, once per conversation.
@MainActor
@Observable
public final class SummaryFeedbackStore {
    public enum State: Equatable, Sendable {
        case hidden
        case asking
        case sending
        /// The answer was stored; the row says thanks for a moment.
        case thanked
        /// Not stored; the row stays so the user can try again.
        case failed
    }

    public private(set) var state: State = .hidden
    /// What the row asks about, chosen when it starts.
    public private(set) var kind: ConversationFeedbackKind = .summary

    static let sampleFraction = 0.25
    static let cooldown: TimeInterval = 7 * 24 * 3600
    static let remembered = 64

    let api: any APIClientProtocol
    let preferences: Preferences?
    let conversationID: String
    let now: () -> Date
    /// Reused when a send is retried (`feedback_id`).
    private var feedbackID = UUID().uuidString

    public init(api: any APIClientProtocol, preferences: Preferences?, conversationID: String, now: @escaping () -> Date = Date.init) {
        self.api = api
        self.preferences = preferences
        self.conversationID = conversationID
        self.now = now
    }

    /// Shows the row when the conversation is sampled, not answered yet, and none showed this week.
    /// Only Omi's own summary asks about the summary (an app's result does not); a finished
    /// recording with audio asks about the recording.
    public func start(hasOwnSummary: Bool, hasRecording: Bool = false) {
        guard state == .hidden, let kind = Self.kind(for: conversationID, hasSummary: hasOwnSummary, hasRecording: hasRecording),
              eligible else { return }
        self.kind = kind
        state = .asking
        preferences?.set(String(now().timeIntervalSince1970), for: .feedbackPromptLastShown)
    }

    /// +1 ("All good") or -1 with a reason.
    public func send(helpful: Bool, reason: SummaryFeedbackReason? = nil) async {
        guard state == .asking || state == .failed else { return }
        state = .sending
        let stored = await (try? api.sendConversationFeedback(
            conversationID: conversationID, kind: kind, helpful: helpful,
            reason: helpful ? nil : reason, feedbackID: feedbackID
        )) ?? false
        guard stored else {
            state = .failed
            return
        }
        remember()
        state = .thanked
    }

    /// The close button: nothing is sent, the conversation does not ask again.
    public func dismiss() {
        remember()
        state = .hidden
    }

    /// The row finished thanking.
    public func finish() {
        if state == .thanked { state = .hidden }
    }

    var eligible: Bool {
        guard !conversationID.isEmpty, conversationID.count <= 256, Self.sampled(conversationID) else { return false }
        if let last = preferences?.string(.feedbackPromptLastShown).flatMap(Double.init),
           now().timeIntervalSince1970 - last < Self.cooldown { return false }
        return !(preferences?.strings(.feedbackPromptDone) ?? []).contains(conversationID)
    }

    private func remember() {
        guard let preferences else { return }
        let done = preferences.strings(.feedbackPromptDone).filter { $0 != conversationID } + [conversationID]
        preferences.set(Array(done.suffix(Self.remembered)), for: .feedbackPromptDone)
    }

    /// Which question a conversation asks (Flutter `feedbackPromptKindForTarget`): the one it can ask,
    /// and with both, bit 0 of byte 4 of SHA-256(id), a byte the sampling does not read.
    static func kind(for id: String, hasSummary: Bool, hasRecording: Bool) -> ConversationFeedbackKind? {
        switch (hasSummary, hasRecording) {
        case (false, false): return nil
        case (true, false): return .summary
        case (false, true): return .recording
        case (true, true):
            guard !id.isEmpty, id.count <= 256 else { return nil }
            return Array(SHA256.hash(data: Data(id.utf8)))[4] & 1 == 0 ? .summary : .recording
        }
    }

    /// The first four bytes of SHA-256(id) as a fraction of 2^32, below the sample fraction.
    static func sampled(_ id: String) -> Bool {
        let digest = Array(SHA256.hash(data: Data(id.utf8)))
        let bucket = digest.prefix(4).reduce(UInt64(0)) { $0 << 8 | UInt64($1) }
        return Double(bucket) / 4_294_967_296 < sampleFraction
    }
}

/// "What was on screen": a meeting's screenshots, with delete (Flutter `conversation_screenshots_section`).
@MainActor
@Observable
public final class ConversationScreenshotsStore {
    public private(set) var screenshots: [ConversationScreenshot] = []
    public private(set) var failedToDelete = false

    let api: any APIClientProtocol
    let conversationID: String

    public init(api: any APIClientProtocol, conversationID: String) {
        self.api = api
        self.conversationID = conversationID
    }

    public func load() async {
        if let loaded = try? await api.conversationScreenshots(conversationID: conversationID) { screenshots = loaded }
    }

    public func delete(_ screenshot: ConversationScreenshot) async {
        failedToDelete = false
        do {
            screenshots = try await api.deleteConversationScreenshot(conversationID: conversationID, screenshotID: screenshot.id)
        } catch {
            failedToDelete = true
        }
    }
}

/// The detail page makes these from the long-lived list store (its client and preferences).
public extension ConversationsStore {
    func makeTemplatesStore() -> SummaryTemplatesStore {
        SummaryTemplatesStore(api: api, preferences: preferences)
    }

    func makeFeedbackStore(conversationID: String) -> SummaryFeedbackStore {
        SummaryFeedbackStore(api: api, preferences: preferences, conversationID: conversationID)
    }

    func makeScreenshotsStore(conversationID: String) -> ConversationScreenshotsStore {
        ConversationScreenshotsStore(api: api, conversationID: conversationID)
    }
}
