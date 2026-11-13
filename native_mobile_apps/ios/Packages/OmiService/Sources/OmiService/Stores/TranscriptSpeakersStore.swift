import Foundation
import Observation
import OmiCore
import OmiNetwork

/// Naming the voices in one conversation's transcript (Flutter `name_speaker_sheet`,
/// `speaker_summary_action`, `earlier_voice_matches_sheet`). Edits show at once and roll back
/// if the backend refuses them; the server's answer then replaces the transcript.
@MainActor
@Observable
public final class TranscriptSpeakersStore {
    public enum Scope: Sendable { case line, voice }

    public enum Choice: Hashable, Sendable {
        case me
        case person(Person)
        case newPerson(String)
        /// TV, podcast, music: clears the label and Omi stops asking about the voice.
        case notAPerson
    }

    /// Earlier conversations where the person just named seems to speak too.
    public struct Matches: Sendable {
        public let person: Person
        public var items: [VoiceMatch]
    }

    /// A name changed: the summary may still say "Speaker 2".
    public private(set) var offersSummaryRefresh = false
    public private(set) var isRefreshingSummary = false
    public private(set) var matches: Matches?
    public private(set) var lastError: String?
    /// Set while a save is in flight so the sheet cannot double-submit.
    public private(set) var isSaving = false

    private let store: ConversationDetailStore
    private var api: any APIClientProtocol {
        store.api
    }

    public init(detail: ConversationDetailStore) {
        store = detail
    }

    /// Lines with the same voice, the tapped one included.
    public func lines(sameVoiceAs line: ConversationDetail.Line) -> [ConversationDetail.Line] {
        guard let speakerID = line.speakerID else { return [line] }
        return (store.detail?.transcript ?? []).filter { $0.speakerID == speakerID }
    }

    /// Names `line` (or its whole voice). Returns the person a new name created, so the caller can
    /// refresh its people list; `nil` otherwise.
    @discardableResult
    public func assign(_ line: ConversationDetail.Line, to choice: Choice, scope: Scope) async -> Person? {
        guard !isSaving, let detail = store.detail else { return nil }
        isSaving = true
        lastError = nil
        defer { isSaving = false }
        let speakerID = scope == .voice ? line.speakerID : nil
        let affected = speakerID == nil ? [line] : lines(sameVoiceAs: line)
        let segmentIDs = affected.compactMap(\.segmentID)
        guard !segmentIDs.isEmpty, choice != .notAPerson || line.speakerID != nil else {
            lastError = "missing segment ids"
            return nil
        }
        var created: Person?
        if case let .newPerson(name) = choice {
            do {
                created = try await api.createPerson(named: name.trimmingCharacters(in: .whitespacesAndNewlines))
            } catch {
                lastError = String(describing: error)
                return nil
            }
        }
        let target = choice.target(created: created)
        let ids = Set(affected.map(\.id))
        store.detail = detail.replacingLines(ids) { line in
            switch target {
            case .user: line.relabeled(isUser: true, personID: nil)
            case let .person(id): line.relabeled(isUser: false, personID: id)
            case nil: line.relabeled(isUser: false, personID: nil)
            }
        }
        do {
            let updated = try await send(target, line: line, segmentIDs: segmentIDs, voice: speakerID, scope: scope)
            store.detail = updated
            offersSummaryRefresh = true
        } catch {
            store.detail = detail
            lastError = String(describing: error)
            return created
        }
        if case let .person(id) = target, let person = created ?? choice.person, person.id == id {
            await loadMatches(for: person, excluding: detail.conversation.id)
        }
        return created
    }

    private func send(
        _ target: SpeakerTarget?, line: ConversationDetail.Line, segmentIDs: [String], voice: Int?, scope: Scope
    ) async throws -> ConversationDetail {
        let id = store.conversation.id
        guard let target else {
            return try await api.rejectSpeaker(
                conversationID: id, speakerID: line.speakerID ?? -1, kind: .notAPerson,
                personID: nil, segmentIDs: scope == .line ? segmentIDs : nil
            )
        }
        return try await api.assignSpeaker(conversationID: id, segmentIDs: segmentIDs, speakerID: voice, to: target)
    }

    /// "Update summary with new names": the backend summarizes the conversation again.
    public func refreshSummary() async {
        guard !isRefreshingSummary else { return }
        let id = store.conversation.id
        isRefreshingSummary = true
        lastError = nil
        defer { isRefreshingSummary = false }
        do {
            store.detail = try await api.reprocessConversation(id: id)
            offersSummaryRefresh = false
        } catch {
            lastError = String(describing: error)
        }
    }

    /// "Is this also <name>?" for one earlier conversation. The match leaves the list once answered.
    public func answer(_ match: VoiceMatch, same: Bool) async {
        guard let current = matches else { return }
        matches?.items.removeAll { $0.id == match.id }
        do {
            if same {
                _ = try await api.assignSpeaker(
                    conversationID: match.conversationID, segmentIDs: match.segmentIDs, speakerID: match.speakerID,
                    to: .person(current.person.id)
                )
            } else {
                _ = try await api.rejectSpeaker(
                    conversationID: match.conversationID, speakerID: match.speakerID, kind: .notPerson,
                    personID: current.person.id, segmentIDs: nil
                )
            }
        } catch {
            matches = current
            lastError = String(describing: error)
        }
    }

    public func dismissMatches() {
        matches = nil
    }

    /// WAV bytes of the voice in an earlier conversation (`nil` when no audio was stored).
    public func clip(for match: VoiceMatch) async -> Data? {
        try? await api.speakerClip(conversationID: match.conversationID, start: match.clipStart, end: match.clipEnd)
    }

    private func loadMatches(for person: Person, excluding conversationID: String) async {
        let found = await (try? api.voiceMatches(personID: person.id)) ?? []
        let items = found.filter { $0.conversationID != conversationID }
        matches = items.isEmpty ? nil : Matches(person: person, items: items)
    }
}

private extension TranscriptSpeakersStore.Choice {
    var person: Person? {
        if case let .person(person) = self { return person }
        return nil
    }

    /// `nil` for Not a Person (and for a new name that could not be created).
    func target(created: Person?) -> SpeakerTarget? {
        switch self {
        case .me: .user
        case let .person(person): .person(person.id)
        case .newPerson: created.map { .person($0.id) }
        case .notAPerson: nil
        }
    }
}

extension ConversationDetail {
    func replacingLines(_ ids: Set<Int>, _ transform: (Line) -> Line) -> ConversationDetail {
        ConversationDetail(
            conversation: conversation, summaryActionItems: summaryActionItems,
            transcript: transcript.map { ids.contains($0.id) ? transform($0) : $0 }
        )
    }
}
