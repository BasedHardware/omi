import Foundation
import OmiCore

/// Who said a line: the user or one of their people.
public enum SpeakerTarget: Hashable, Sendable {
    case user
    case person(String)
}

/// Why a label on a voice is wrong (`POST …/speakers/{id}/reject`).
public enum SpeakerRejection: String, Sendable {
    case notMe = "not_me"
    case notPerson = "not_person"
    /// TV, podcast, music: Omi stops asking about this voice (it shows under Ignored voices).
    case notAPerson = "not_a_person"
}

/// An unnamed voice in an earlier conversation that sounds like a person (`GET …/voice-matches`).
public struct VoiceMatch: Identifiable, Hashable, Sendable {
    public var id: String {
        "\(conversationID)#\(speakerID)"
    }

    public let conversationID: String
    public let title: String
    public let startedAt: Date?
    public let speakerID: Int
    public let talkSeconds: Double
    public let segmentIDs: [String]
    public let clipStart: Double
    public let clipEnd: Double
    public let isStrong: Bool

    public init(
        conversationID: String, title: String, startedAt: Date?, speakerID: Int, talkSeconds: Double,
        segmentIDs: [String], clipStart: Double, clipEnd: Double, isStrong: Bool
    ) {
        self.conversationID = conversationID
        self.title = title
        self.startedAt = startedAt
        self.speakerID = speakerID
        self.talkSeconds = talkSeconds
        self.segmentIDs = segmentIDs
        self.clipStart = clipStart
        self.clipEnd = clipEnd
        self.isStrong = isStrong
    }
}

/// "Is this you?" / "Is this <name>?" / "Who is this?" about one voice in a recent conversation
/// (`GET v1/speaker-tag-prompts`).
public struct SpeakerPrompt: Identifiable, Hashable, Sendable {
    public enum Kind: String, Sendable { case ownerCheck = "owner_check", confirmPerson = "confirm_person", identify }

    public struct Candidate: Identifiable, Hashable, Sendable {
        public let id: String
        public let name: String

        public init(id: String, name: String) {
            self.id = id
            self.name = name
        }
    }

    public let id: String
    public let kind: Kind
    /// Backend `origin` (auto_user | auto_person | unnamed), echoed back with the answer.
    public let origin: String
    public let conversationID: String
    public let conversationTitle: String
    public let speakerID: Int
    public let segmentIDs: [String]
    public let clipStart: Double
    public let clipEnd: Double
    public let excerpt: String
    public let suggestedPersonID: String?
    public let suggestedPersonName: String?
    public let candidates: [Candidate]

    public init(
        id: String, kind: Kind, origin: String = "unnamed", conversationID: String, conversationTitle: String = "",
        speakerID: Int, segmentIDs: [String], clipStart: Double = 0, clipEnd: Double = 0, excerpt: String = "",
        suggestedPersonID: String? = nil, suggestedPersonName: String? = nil, candidates: [Candidate] = []
    ) {
        self.id = id
        self.kind = kind
        self.origin = origin
        self.conversationID = conversationID
        self.conversationTitle = conversationTitle
        self.speakerID = speakerID
        self.segmentIDs = segmentIDs
        self.clipStart = clipStart
        self.clipEnd = clipEnd
        self.excerpt = excerpt
        self.suggestedPersonID = suggestedPersonID
        self.suggestedPersonName = suggestedPersonName
        self.candidates = candidates
    }
}

/// The user's answer to a prompt (backend `SpeakerTagPromptAnswer`).
public enum SpeakerPromptAnswer: Hashable, Sendable {
    case me
    case notMe
    case person(String)
    case newPerson(String)
    /// Not the suggested person, and the user does not say who.
    case someoneElse
    case notAPerson
    case skip

    var wire: String {
        switch self {
        case .me: "me"
        case .notMe: "not_me"
        case .person: "person"
        case .newPerson: "new_person"
        case .someoneElse: "someone_else"
        case .notAPerson: "not_a_person"
        case .skip: "skip"
        }
    }
}

/// A voice the user marked Not a Person (`GET v1/speaker-tag-prompts/ignored-voices`).
public struct IgnoredVoice: Identifiable, Hashable, Sendable {
    public var id: String {
        "\(conversationID)#\(speakerID)"
    }

    public let conversationID: String
    public let speakerID: Int
    public let conversationTitle: String
    public let ignoredAt: Date?

    public init(conversationID: String, speakerID: Int, conversationTitle: String, ignoredAt: Date?) {
        self.conversationID = conversationID
        self.speakerID = speakerID
        self.conversationTitle = conversationTitle
        self.ignoredAt = ignoredAt
    }
}

/// Voice-learning switches (`v1/users/voice-profile-settings`).
public struct VoiceProfileSettings: Equatable, Sendable {
    /// "Ask me to tag voices": Omi asks who spoke in recent conversations.
    public var asksToTag: Bool
    /// "Remember voices of people you name": naming someone keeps a short voice sample.
    public var savesOtherVoices: Bool

    public init(asksToTag: Bool, savesOtherVoices: Bool) {
        self.asksToTag = asksToTag
        self.savesOtherVoices = savesOtherVoices
    }
}

enum PersonMapper {
    static func map(_ item: [String: Any]) -> Person? {
        guard let id = item["id"] as? String else { return nil }
        let samples = (item["speech_samples"] as? [String] ?? []).compactMap(URL.init(string:))
        return Person(
            id: id,
            name: item["name"] as? String ?? "",
            sampleCount: (item["speech_samples"] as? [Any])?.count ?? 0,
            sampleURLs: samples,
            isPinned: item["pinned"] as? Bool ?? false,
            confidence: (item["confidence"] as? String).flatMap(Person.Confidence.init(rawValue:)) ?? .unknown,
            conversationCount: item["conversation_count"] as? Int,
            talkSeconds: (item["talk_seconds"] as? NSNumber)?.doubleValue,
            lastHeardAt: BackendDate.parse(item["last_heard_at"] as? String)
        )
    }
}

enum SpeakerMapper {
    static func voiceMatch(_ item: [String: Any]) -> VoiceMatch? {
        guard let conversationID = item["conversation_id"] as? String, let speakerID = item["speaker_id"] as? Int else { return nil }
        return VoiceMatch(
            conversationID: conversationID,
            title: item["title"] as? String ?? "",
            startedAt: BackendDate.parse(item["started_at"] as? String),
            speakerID: speakerID,
            talkSeconds: (item["talk_seconds"] as? NSNumber)?.doubleValue ?? 0,
            segmentIDs: item["segment_ids"] as? [String] ?? [],
            clipStart: (item["clip_start"] as? NSNumber)?.doubleValue ?? 0,
            clipEnd: (item["clip_end"] as? NSNumber)?.doubleValue ?? 0,
            isStrong: item["match_level"] as? String == "strong"
        )
    }

    static func prompt(_ item: [String: Any]) -> SpeakerPrompt? {
        guard let id = item["id"] as? String,
              let kind = (item["kind"] as? String).flatMap(SpeakerPrompt.Kind.init(rawValue:)),
              let conversationID = item["conversation_id"] as? String,
              let speakerID = item["speaker_id"] as? Int else { return nil }
        let candidates = (item["candidates"] as? [[String: Any]] ?? []).compactMap { candidate -> SpeakerPrompt.Candidate? in
            guard let id = candidate["person_id"] as? String, let name = candidate["name"] as? String else { return nil }
            return SpeakerPrompt.Candidate(id: id, name: name)
        }
        return SpeakerPrompt(
            id: id, kind: kind, origin: item["origin"] as? String ?? "unnamed",
            conversationID: conversationID, conversationTitle: item["conversation_title"] as? String ?? "",
            speakerID: speakerID, segmentIDs: item["segment_ids"] as? [String] ?? [],
            clipStart: (item["clip_start"] as? NSNumber)?.doubleValue ?? 0,
            clipEnd: (item["clip_end"] as? NSNumber)?.doubleValue ?? 0,
            excerpt: item["excerpt"] as? String ?? "",
            suggestedPersonID: item["suggested_person_id"] as? String,
            suggestedPersonName: item["suggested_person_name"] as? String,
            candidates: candidates
        )
    }

    static func ignoredVoice(_ item: [String: Any]) -> IgnoredVoice? {
        guard let conversationID = item["conversation_id"] as? String, let speakerID = item["speaker_id"] as? Int else { return nil }
        return IgnoredVoice(
            conversationID: conversationID, speakerID: speakerID,
            conversationTitle: item["conversation_title"] as? String ?? "",
            ignoredAt: BackendDate.parse(item["ignored_at"] as? String)
        )
    }

    static func settings(_ item: [String: Any]) -> VoiceProfileSettings {
        VoiceProfileSettings(
            asksToTag: item["speaker_tag_prompts_enabled"] as? Bool ?? true,
            savesOtherVoices: item["save_other_voice_profiles"] as? Bool ?? true
        )
    }
}
