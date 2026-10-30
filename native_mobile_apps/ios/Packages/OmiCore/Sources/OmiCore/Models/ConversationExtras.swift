import Foundation

/// The Google Calendar event a conversation is linked to (`conversation.calendar_event`).
public struct CalendarEventLink: Hashable, Sendable {
    public let eventID: String
    public let title: String
    /// Display names (the owner left out), and the addresses "Share with attendees" writes to.
    public let attendees: [String]
    public let attendeeEmails: [String]
    public let start: Date
    public let end: Date
    /// Opens the event in Google Calendar.
    public let htmlLink: URL?

    public init(eventID: String, title: String, attendees: [String], attendeeEmails: [String], start: Date, end: Date, htmlLink: URL?) {
        self.eventID = eventID
        self.title = title
        self.attendees = attendees
        self.attendeeEmails = attendeeEmails
        self.start = start
        self.end = end
        self.htmlLink = htmlLink
    }

    /// `mailto:` to every attendee with "Notes: <title>" as subject (Flutter `calendar_event_sheets`).
    public func shareURL(subject: String) -> URL? {
        guard !attendeeEmails.isEmpty else { return nil }
        var components = URLComponents()
        components.scheme = "mailto"
        components.path = attendeeEmails.joined(separator: ",")
        components.queryItems = [URLQueryItem(name: "subject", value: subject)]
        return components.url
    }
}

/// An event from the user's Google Calendar, offered when linking a conversation.
public struct CalendarEventCandidate: Identifiable, Hashable, Sendable {
    public let id: String
    public let title: String
    public let start: Date
    public let end: Date
    public let attendees: [String]

    public init(id: String, title: String, start: Date, end: Date, attendees: [String]) {
        self.id = id
        self.title = title
        self.start = start
        self.end = end
        self.attendees = attendees
    }

    /// The event Flutter marks "Suggested": the biggest overlap of at least five minutes or half the event.
    public static func suggested(_ events: [CalendarEventCandidate], start: Date, end: Date) -> CalendarEventCandidate? {
        events.compactMap { event -> (CalendarEventCandidate, TimeInterval)? in
            let overlap = min(event.end, end).timeIntervalSince(max(event.start, start))
            let length = event.end.timeIntervalSince(event.start)
            guard overlap > 0, overlap >= 300 || (length > 0 && overlap >= length / 2) else { return nil }
            return (event, overlap)
        }
        .max { $0.1 < $1.1 }?.0
    }
}

/// A photo taken during the conversation (Omi Glass, `conversation.photos`).
public struct ConversationPhoto: Identifiable, Hashable, Sendable {
    public let id: String
    /// Inline image bytes; when empty the image is fetched by `id` (`storage_id` photos).
    public let data: Data?
    public let description: String?
    public let isDiscarded: Bool
    public let isStored: Bool

    public init(id: String, data: Data?, description: String?, isDiscarded: Bool, isStored: Bool) {
        self.id = id
        self.data = data
        self.description = description
        self.isDiscarded = isDiscarded
        self.isStored = isStored
    }

    /// Omi is still describing it.
    public var isDescribing: Bool {
        !isDiscarded && description == nil
    }
}

/// A screenshot of what was on screen during a meeting (`v1/conversations/{id}/screenshots`).
public struct ConversationScreenshot: Identifiable, Hashable, Sendable {
    public let id: String
    public let caption: String
    public let imageURL: URL?
    public let thumbnailURL: URL?
    public let capturedAt: Date?

    public init(id: String, caption: String, imageURL: URL?, thumbnailURL: URL?, capturedAt: Date?) {
        self.id = id
        self.caption = caption
        self.imageURL = imageURL
        self.thumbnailURL = thumbnailURL
        self.capturedAt = capturedAt
    }
}

/// Another device's recording of the same moment (`conversation.capture_group`); each is a
/// conversation of its own.
public struct CaptureRecording: Identifiable, Hashable, Sendable {
    public let id: String
    /// `omi`, `phone`, `desktop`, `apple_watch` …
    public let source: String?
    public let start: Date?
    public let end: Date?
    public let isCurrent: Bool

    public init(id: String, source: String?, start: Date?, end: Date?, isCurrent: Bool) {
        self.id = id
        self.source = source
        self.start = start
        self.end = end
        self.isCurrent = isCurrent
    }

    /// The group as Flutter's `CaptureGroupPresentation.recordings`: unique members plus the
    /// current conversation, by start (unknown last, then id); empty below two.
    public static func list(
        members: [CaptureRecording], current id: String, source: String?, start: Date?, end: Date?
    ) -> [CaptureRecording] {
        var seen = Set<String>()
        var all = members.filter { seen.insert($0.id).inserted }
            .map { CaptureRecording(id: $0.id, source: $0.source, start: $0.start, end: $0.end, isCurrent: $0.id == id) }
        if !seen.contains(id) { all.append(CaptureRecording(id: id, source: source, start: start, end: end, isCurrent: true)) }
        guard all.count > 1 else { return [] }
        return all.sorted { lhs, rhs in
            switch (lhs.start, rhs.start) {
            case let (left?, right?) where left != right: left < right
            case (.some, nil): true
            case (nil, .some): false
            default: lhs.id < rhs.id
            }
        }
    }
}

/// One stored piece of a conversation's audio (`audio_files`), and where it can be played.
public struct AudioPart: Identifiable, Hashable, Sendable {
    public enum Status: String, Sendable { case cached, pending, unavailable }

    public let id: String
    public let status: Status
    /// Signed, playable without auth headers.
    public let url: URL?
    public let duration: TimeInterval
    public let startedAt: Date?
    /// `audio/mpeg` or `audio/wav`.
    public let contentType: String?

    public init(id: String, status: Status, url: URL?, duration: TimeInterval, startedAt: Date? = nil, contentType: String? = nil) {
        self.id = id
        self.status = status
        self.url = url
        self.duration = duration
        self.startedAt = startedAt
        self.contentType = contentType
    }

    public var isWAV: Bool {
        contentType == "audio/wav" || url?.pathExtension.lowercased() == "wav"
    }
}

/// Who took part: "You", the people named in the transcript, unnamed voices Omi could count, else
/// the calendar attendees (Flutter `conversation_detail_meta.dart`).
public struct Participants: Hashable, Sendable {
    public let names: [String]
    /// People beyond `names` Omi heard but could not name.
    public let unnamed: Int
    /// Omi could not count the unnamed voices ("+ others").
    public let uncounted: Bool

    public init(names: [String], unnamed: Int, uncounted: Bool) {
        self.names = names
        self.unnamed = unnamed
        self.uncounted = uncounted
    }

    public var isEmpty: Bool {
        names.isEmpty
    }

    /// Everyone after the first name.
    public var others: Int {
        names.count - 1 + unnamed
    }
}

public extension ConversationDetail {
    /// `you` is the word for the user; `personName` names a person id (`nil` when unknown).
    func participants(you: String, personName: (String) -> String?) -> Participants {
        var names: [String] = []
        if transcript.contains(where: \.isUser) { names.append(you) }
        var unnamedSpeakers = Set<Int>()
        for line in transcript where !line.isUser {
            if let person = line.personID, let name = personName(person) {
                if !names.contains(name) { names.append(name) }
            } else if let speaker = line.speakerID {
                unnamedSpeakers.insert(speaker)
            }
        }
        var unnamed = 0
        var uncounted = false
        if let countable = participantSpeakerIDs {
            unnamed = Set(countable).intersection(unnamedSpeakers).count
        } else if !unnamedSpeakers.isEmpty {
            uncounted = true
        }
        if names.isEmpty || names == [you], let event = calendarEvent, !event.attendees.isEmpty {
            let attendees = event.attendees.map(Self.attendeeName)
            return Participants(names: names + attendees, unnamed: 0, uncounted: false)
        }
        return Participants(names: names, unnamed: unnamed, uncounted: uncounted && names.count > 0)
    }

    /// An email becomes its capitalised local part, a name its first word.
    static func attendeeName(_ value: String) -> String {
        if let at = value.firstIndex(of: "@") {
            let local = value[..<at]
            return local.prefix(1).uppercased() + local.dropFirst()
        }
        return value.split(separator: " ").first.map(String.init) ?? value
    }
}

/// Why a summary or a recording did not help (`mobile_feedback.v1` reasons).
public enum SummaryFeedbackReason: String, CaseIterable, Sendable {
    case inaccurate = "summary_inaccurate"
    case incomplete = "summary_incomplete"
    case irrelevant = "summary_irrelevant"
    case wrongContext = "summary_wrong_context"
    case other = "summary_other"
    case missingAudio = "recording_missing_audio"
    case poorTranscription = "recording_poor_transcription"
    case wrongSpeaker = "recording_wrong_speaker"
    case delayedOrStuck = "recording_delayed_or_stuck"
    case fragmentedOrDuplicated = "recording_fragmented_or_duplicated"
    case recordingOther = "recording_other"

    /// The reasons one kind of prompt offers.
    public static func reasons(for kind: ConversationFeedbackKind) -> [Self] {
        switch kind {
        case .summary: [.inaccurate, .incomplete, .irrelevant, .wrongContext, .other]
        case .recording: [.missingAudio, .poorTranscription, .wrongSpeaker, .delayedOrStuck, .fragmentedOrDuplicated, .recordingOther]
        }
    }
}

/// What "Was this helpful?" asks about (`mobile_feedback.v1` `kind`): the summary, or how the
/// recording and its transcript came out.
public enum ConversationFeedbackKind: String, Sendable {
    case summary = "summary_helpfulness"
    case recording = "recording_quality"
}

/// Which conversations the list asks the backend for (`GET v1/conversations`).
public struct ConversationQuery: Hashable, Sendable {
    public var filter: ConversationFilter
    public var includeDiscarded: Bool
    /// Inclusive bounds (the one-day page).
    public var start: Date?
    public var end: Date?

    public init(filter: ConversationFilter = .all, includeDiscarded: Bool = false, start: Date? = nil, end: Date? = nil) {
        self.filter = filter
        self.includeDiscarded = includeDiscarded
        self.start = start
        self.end = end
    }
}

/// What the conversation list hides on the device (Flutter "Conversation display"): discarded
/// conversations unless shown, and short ones under a threshold.
public struct ConversationDisplay: Hashable, Sendable {
    public var showsDiscarded: Bool
    public var showsShort: Bool
    /// Seconds; 0 hides nothing.
    public var shortThreshold: Int

    public init(showsDiscarded: Bool = false, showsShort: Bool = false, shortThreshold: Int = 0) {
        self.showsDiscarded = showsDiscarded
        self.showsShort = showsShort
        self.shortThreshold = shortThreshold
    }

    /// The list keeps this conversation.
    public func keeps(_ conversation: Conversation) -> Bool {
        if conversation.isDiscarded, !showsDiscarded { return false }
        if !showsShort, shortThreshold > 0, let duration = conversation.duration, duration < TimeInterval(shortThreshold) { return false }
        return true
    }

    /// One row per capture group (Flutter `CaptureGroupPresentation`): the group's primary
    /// recording when it is loaded, else the first one; the others open from its page.
    public static func oneRowPerCaptureGroup(_ list: [Conversation]) -> [Conversation] {
        var shown: [String: String] = [:]
        for conversation in list {
            guard let group = conversation.captureGroupID else { continue }
            if shown[group] == nil || conversation.id == conversation.captureGroupPrimaryID { shown[group] = conversation.id }
        }
        return list.filter { conversation in conversation.captureGroupID.map { shown[$0] == conversation.id } ?? true }
    }

    /// The threshold the list hides below, `nil` when every length shows.
    public var hidesShorterThan: Int? {
        !showsShort && shortThreshold > 0 ? shortThreshold : nil
    }
}

/// A summary template the user writes: a name and the prompt the app runs on each conversation.
public struct SummaryTemplateDraft: Hashable, Sendable {
    public var name: String
    public var prompt: String
    public var isPublic: Bool

    public init(name: String, prompt: String, isPublic: Bool = false) {
        self.name = name
        self.prompt = prompt
        self.isPublic = isPublic
    }

    public enum Problem: Equatable, Sendable { case nameMissing, nameTooShort, promptMissing, promptTooShort }

    /// Flutter's form rules: a name of three characters, a prompt of ten.
    public var problem: Problem? {
        let name = name.trimmingCharacters(in: .whitespacesAndNewlines)
        let prompt = prompt.trimmingCharacters(in: .whitespacesAndNewlines)
        if name.isEmpty { return .nameMissing }
        if name.count < 3 { return .nameTooShort }
        if prompt.isEmpty { return .promptMissing }
        if prompt.count < 10 { return .promptTooShort }
        return nil
    }
}
