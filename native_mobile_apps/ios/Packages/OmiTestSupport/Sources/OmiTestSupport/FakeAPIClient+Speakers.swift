import Foundation
import OmiCore
import OmiNetwork

/// What the fake backend knows about voices. Tests seed it and read the log.
public struct FakeSpeakerBackend: Sendable {
    /// Transcripts by conversation id, edited by assign/reject like the server does.
    public var transcripts: [String: [ConversationDetail.Line]] = [:]
    public var matches: [String: [VoiceMatch]] = [:]
    public var prompts: [SpeakerPrompt] = []
    public var settings = VoiceProfileSettings(asksToTag: true, savesOtherVoices: true)
    public var ignored: [IgnoredVoice] = []
    public var personConversations: [String: [Conversation]] = [:]
    /// Calls that fail with HTTP 500 (`assign`, `reject`, `reprocess`, `pin`, `deleteSample`,
    /// `answer`, `dismiss`, `settings`, `restore`, `createPerson`).
    public var failing: Set<String> = []
    /// One entry per call, e.g. `assign:c1:voice=1:person:p1`.
    public var log: [String] = []

    public init() {}
}

public extension FakeAPIClient {
    func peopleWithStats() async throws -> [Person] {
        try fail("people")
        return fakePeople
    }

    func createPerson(named name: String) async throws -> Person {
        try fail("createPerson")
        if let existing = fakePeople.first(where: { $0.name == name }) { return existing }
        let person = Person(id: "p\(fakePeople.count)", name: name, sampleCount: 0)
        fakePeople.append(person)
        return person
    }

    func setPersonPinned(_ id: String, pinned: Bool) async throws {
        try fail("pin")
        if let index = fakePeople.firstIndex(where: { $0.id == id }) { fakePeople[index].isPinned = pinned }
    }

    func deleteSpeechSample(personID: String, index: Int) async throws {
        try fail("deleteSample")
        speakers.log.append("deleteSample:\(personID):\(index)")
    }

    func conversations(withPerson personID: String, page: Int, perPage: Int) async throws -> [Conversation] {
        try fail("personConversations")
        return Array((speakers.personConversations[personID] ?? []).dropFirst((page - 1) * perPage).prefix(perPage))
    }

    func assignSpeaker(
        conversationID: String, segmentIDs: [String], speakerID: Int?, to target: SpeakerTarget
    ) async throws -> ConversationDetail {
        let label = switch target {
        case .user: "user"
        case let .person(id): "person:\(id)"
        }
        speakers.log.append("assign:\(conversationID):\(speakerID.map { "voice=\($0)" } ?? segmentIDs.joined(separator: ",")):\(label)")
        try fail("assign")
        let isUser = target == .user
        let personID: String? = if case let .person(id) = target { id } else { nil }
        return relabel(conversationID) { line in
            let matches = speakerID.map { line.speakerID == $0 } ?? segmentIDs.contains(line.segmentID ?? "")
            return matches ? line.relabeled(isUser: isUser, personID: personID) : line
        }
    }

    func rejectSpeaker(
        conversationID: String, speakerID: Int, kind: SpeakerRejection, personID _: String?, segmentIDs: [String]?
    ) async throws -> ConversationDetail {
        speakers.log.append("reject:\(conversationID):\(speakerID):\(kind.rawValue)")
        try fail("reject")
        if kind == .notAPerson {
            let voice = IgnoredVoice(conversationID: conversationID, speakerID: speakerID, conversationTitle: "", ignoredAt: nil)
            speakers.ignored.append(voice)
        }
        return relabel(conversationID) { line in
            let matches = line.speakerID == speakerID && (segmentIDs.map { $0.contains(line.segmentID ?? "") } ?? true)
            return matches ? line.relabeled(isUser: false, personID: nil) : line
        }
    }

    func voiceMatches(personID: String) async throws -> [VoiceMatch] {
        speakers.matches[personID] ?? []
    }

    func speakerPrompts() async throws -> [SpeakerPrompt] {
        try fail("prompts")
        return speakers.prompts
    }

    func markSpeakerPromptsShown(_ ids: [String]) async throws {
        speakers.log.append("shown:\(ids.joined(separator: ","))")
    }

    func dismissSpeakerPrompts() async throws {
        speakers.log.append("dismiss")
        try fail("dismiss")
    }

    func answerSpeakerPrompt(_ prompt: SpeakerPrompt, answer: SpeakerPromptAnswer) async throws {
        speakers.log.append("answer:\(prompt.id):\(answer)")
        try fail("answer")
        speakers.prompts.removeAll { $0.id == prompt.id }
    }

    func speakerClip(conversationID _: String, start _: Double, end _: Double) async throws -> Data {
        try fail("clip")
        return Data("RIFF".utf8)
    }

    func voiceProfileSettings() async throws -> VoiceProfileSettings {
        speakers.settings
    }

    func updateVoiceProfileSettings(asksToTag: Bool?, savesOtherVoices: Bool?) async throws -> VoiceProfileSettings {
        try fail("settings")
        if let asksToTag { speakers.settings.asksToTag = asksToTag }
        if let savesOtherVoices { speakers.settings.savesOtherVoices = savesOtherVoices }
        return speakers.settings
    }

    func ignoredVoices() async throws -> [IgnoredVoice] {
        speakers.ignored
    }

    func restoreIgnoredVoice(conversationID: String, speakerID: Int) async throws {
        try fail("restore")
        speakers.ignored.removeAll { $0.conversationID == conversationID && $0.speakerID == speakerID }
    }

    private func fail(_ call: String) throws {
        if speakers.failing.contains(call) { throw APIError.http(status: 500, body: call) }
        if let failure = lock.withLock({ _error }) { throw failure }
    }

    private func relabel(_ id: String, _ transform: (ConversationDetail.Line) -> ConversationDetail.Line) -> ConversationDetail {
        let lines = (speakers.transcripts[id] ?? []).map(transform)
        speakers.transcripts[id] = lines
        let conversation = _conversations.first { $0.id == id } ?? Fixtures.conversation(id: id, title: "Conversation", minutesAgo: 10)
        return ConversationDetail(conversation: conversation, summaryActionItems: [], transcript: lines)
    }
}
