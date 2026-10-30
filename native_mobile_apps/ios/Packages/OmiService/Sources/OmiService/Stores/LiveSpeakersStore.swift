import Foundation
import Observation
import OmiCore
import OmiNetwork

/// Naming a voice in the conversation being recorded (Flutter `conversation_capturing` →
/// `assignSpeakerToConversation`): the in-progress conversation gets the same REST assignment as a
/// finished one, the listen session hears `speaker_assigned`, and the live transcript shows the name
/// at once, also on later lines of a voice named as a whole.
@MainActor
@Observable
public final class LiveSpeakersStore {
    /// Who said a line: the user, a person, or nobody named yet.
    public struct Label: Equatable, Sendable {
        public let isUser: Bool
        public let personID: String?
    }

    public private(set) var isSaving = false
    public private(set) var lastError: String?

    /// Lines named one by one, and voices named as a whole (they cover lines still to come).
    private var lines: [String: Label] = [:]
    private var voices: [Int: Label] = [:]
    /// Names chosen here, for people the people list does not know yet.
    private var names: [String: String] = [:]
    /// The in-progress conversation the labels belong to.
    private var conversationID: String?

    private let api: any APIClientProtocol
    private let capture: CaptureStore

    public init(api: any APIClientProtocol, capture: CaptureStore) {
        self.api = api
        self.capture = capture
    }

    private var isCurrent: Bool {
        conversationID != nil && (capture.liveConversationID == nil || capture.liveConversationID == conversationID)
    }

    /// The name chosen here for `personID`, if any.
    public func name(for personID: String) -> String? {
        names[personID]
    }

    public func label(for segment: LiveSegment) -> Label {
        if isCurrent {
            if let label = lines[segment.id] { return label }
            if let speakerID = segment.speakerID, let label = voices[speakerID] { return label }
        }
        return Label(isUser: segment.isUser, personID: segment.isUser ? nil : segment.personID)
    }

    /// The live lines with the same voice, the tapped one included.
    public func lines(sameVoiceAs segment: LiveSegment) -> [LiveSegment] {
        guard let speakerID = segment.speakerID else { return [segment] }
        return capture.segments.filter { $0.speakerID == speakerID }
    }

    /// Names `segment` (or its whole voice). Not a Person is not offered while recording.
    /// Returns the person a new name created, so the caller can refresh its people list.
    @discardableResult
    public func assign(_ segment: LiveSegment, to choice: TranscriptSpeakersStore.Choice, scope: TranscriptSpeakersStore.Scope) async
        -> Person?
    {
        guard !isSaving, choice != .notAPerson else { return nil }
        isSaving = true
        lastError = nil
        defer { isSaving = false }
        let voice = scope == .voice ? segment.speakerID : nil
        let segmentIDs = (voice == nil ? [segment] : lines(sameVoiceAs: segment)).map(\.id)
        do {
            guard let id = try await currentConversationID() else { throw APIError.http(status: 404, body: "no in-progress conversation") }
            var created: Person?
            let target: SpeakerTarget, personName: String
            switch choice {
            case .me: (target, personName) = (.user, "")
            case let .person(person): (target, personName) = (.person(person.id), person.name)
            case let .newPerson(name):
                let person = try await api.createPerson(named: name.trimmingCharacters(in: .whitespacesAndNewlines))
                (created, target, personName) = (person, .person(person.id), person.name)
            case .notAPerson: return nil
            }
            _ = try await api.assignSpeaker(conversationID: id, segmentIDs: segmentIDs, speakerID: voice, to: target)
            apply(target, name: personName, conversationID: id, segmentIDs: segmentIDs, voice: voice)
            capture.sendSpeakerAssigned(
                speakerID: segment.speakerID, personID: target.wireID, personName: personName, segmentIDs: segmentIDs
            )
            return created
        } catch {
            lastError = String(describing: error)
            return nil
        }
    }

    private func currentConversationID() async throws -> String? {
        if let live = capture.liveConversationID { return live }
        return try await api.inProgressConversationID()
    }

    private func apply(_ target: SpeakerTarget, name: String, conversationID id: String, segmentIDs: [String], voice: Int?) {
        if id != conversationID {
            (lines, voices, conversationID) = ([:], [:], id)
        }
        let label = switch target {
        case .user: Label(isUser: true, personID: nil)
        case let .person(personID): Label(isUser: false, personID: personID)
        }
        if case let .person(personID) = target, !name.isEmpty { names[personID] = name }
        if let voice {
            voices[voice] = label
            // Lines of this voice named one by one before now follow the voice.
            for segmentID in segmentIDs {
                lines[segmentID] = nil
            }
        } else {
            for segmentID in segmentIDs {
                lines[segmentID] = label
            }
        }
    }
}

private extension SpeakerTarget {
    /// Flutter sends `user` for the wearer.
    var wireID: String {
        switch self {
        case .user: "user"
        case let .person(id): id
        }
    }
}
