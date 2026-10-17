import Foundation

/// Everything the conversation detail renders.
public struct ConversationDetail: Hashable, Sendable {
    public struct Line: Identifiable, Hashable, Sendable {
        public let id: Int
        public let speaker: String
        public let isUser: Bool
        public var text: String
        public let start: TimeInterval
        /// Where the line ends on the recording's clock (`start` when the backend did not say).
        public let end: TimeInterval
        /// The line in other languages, as Omi translated it (`translations[].text`).
        public let translations: [String]
        /// The backend segment id (editing, speaker labeling), speaker number and named person.
        public let segmentID: String?
        public let speakerID: Int?
        public let personID: String?

        public init(
            id: Int, speaker: String, isUser: Bool, text: String, start: TimeInterval,
            segmentID: String? = nil, speakerID: Int? = nil, personID: String? = nil,
            end: TimeInterval? = nil, translations: [String] = []
        ) {
            self.id = id
            self.speaker = speaker
            self.isUser = isUser
            self.text = text
            self.start = start
            self.end = max(end ?? start, start)
            self.translations = translations
            self.segmentID = segmentID
            self.speakerID = speakerID
            self.personID = personID
        }

        /// The same line, said by the user or by a person (`nil` for nobody named).
        public func relabeled(isUser: Bool, personID: String?) -> Line {
            Line(
                id: id, speaker: speaker, isUser: isUser, text: text, start: start,
                segmentID: segmentID, speakerID: speakerID, personID: isUser ? nil : personID,
                end: end, translations: translations
            )
        }
    }

    /// A summary another app (a summary template) wrote for this conversation.
    public struct AppSummary: Hashable, Sendable {
        public let appID: String?
        public let content: String

        public init(appID: String?, content: String) {
            self.appID = appID
            self.content = content
        }
    }

    /// A calendar event Omi found in the conversation.
    public struct Event: Hashable, Sendable {
        public let title: String
        public let description: String
        public let start: Date?
        /// Minutes.
        public let duration: Int
        /// Already added to a calendar (`created`).
        public var isCreated: Bool

        public init(title: String, description: String, start: Date?, duration: Int, isCreated: Bool = false) {
            self.title = title
            self.description = description
            self.start = start
            self.duration = duration
            self.isCreated = isCreated
        }
    }

    public var conversation: Conversation
    /// Action items extracted into the summary (the canonical tasks come from TasksStore).
    public let summaryActionItems: [String]
    public var transcript: [Line]
    /// The summary as Markdown: the first app's result, else the overview, else the structured
    /// sections (the Flutter app's `ConversationSummarySelection`).
    public var summary: String
    /// The gist in two or three sentences (`structured.short_summary`), when the backend kept it.
    public var gist: String?
    /// App results after the one shown as the summary.
    public let otherSummaries: [AppSummary]
    /// Key points (`structured.insights`).
    public let keyPoints: [String]
    public var events: [Event]
    /// Audio was stored for this conversation (`audio_files`).
    public let hasAudio: Bool
    /// The app whose result is shown as the summary (`nil`: Omi's own summary).
    public let summaryAppID: String?
    /// The summary shown is Omi's own, not an app's result. A result from an app that did not
    /// send its id cannot be addressed by the summary PATCH, so it stays read-only.
    public let summaryIsOmiOwn: Bool
    /// Omi could not tell the other voices apart across recordings (`speaker_resolution.status`
    /// "unavailable"): the transcript says so once.
    public var speakersUnresolved = false
    public var calendarEvent: CalendarEventLink?
    public let photos: [ConversationPhoto]
    /// Other devices' recordings of the same moment, this one included (empty below two).
    public let recordings: [CaptureRecording]
    /// The stored audio pieces, oldest first (start times for playing several in order).
    public let audioParts: [AudioPart]
    /// Speakers Omi could count (`speaker_resolution` resolved or capture); `nil` when it could not.
    public let participantSpeakerIDs: [Int]?
    /// What each extracted action item was based on, keyed by its normalized description
    /// (`ConversationDigest.normalized`): the cited transcript segments and the one-line context.
    public var actionItemSources: [String: ActionItemSource] = [:]
    /// The notes' sections with the transcript segments each cites (`structured.sections`), in
    /// order: the transcript's chapters.
    public var chapters: [Chapter] = []

    public struct Chapter: Hashable, Sendable {
        public let heading: String
        public let segmentIDs: [String]

        public init(heading: String, segmentIDs: [String]) {
            self.heading = heading
            self.segmentIDs = segmentIDs
        }
    }

    public struct ActionItemSource: Hashable, Sendable {
        public let context: String
        public let segmentIDs: [String]

        public init(context: String, segmentIDs: [String]) {
            self.context = context
            self.segmentIDs = segmentIDs
        }
    }

    public init(
        conversation: Conversation,
        summaryActionItems: [String],
        transcript: [Line],
        summary: String? = nil,
        gist: String? = nil,
        otherSummaries: [AppSummary] = [],
        keyPoints: [String] = [],
        events: [Event] = [],
        hasAudio: Bool = false,
        summaryAppID: String? = nil,
        summaryIsOmiOwn: Bool = true,
        calendarEvent: CalendarEventLink? = nil,
        photos: [ConversationPhoto] = [],
        recordings: [CaptureRecording] = [],
        audioParts: [AudioPart] = [],
        participantSpeakerIDs: [Int]? = nil
    ) {
        self.conversation = conversation
        self.summaryActionItems = summaryActionItems
        self.transcript = transcript
        self.summary = summary ?? conversation.overview
        self.gist = gist
        self.otherSummaries = otherSummaries
        self.keyPoints = keyPoints
        self.events = events
        self.hasAudio = hasAudio
        self.summaryAppID = summaryAppID
        self.summaryIsOmiOwn = summaryIsOmiOwn
        self.calendarEvent = calendarEvent
        self.photos = photos
        self.recordings = recordings
        self.audioParts = audioParts
        self.participantSpeakerIDs = participantSpeakerIDs
    }

    /// The transcript as plain text, one "Speaker: words" line each (copy and share).
    public var transcriptText: String {
        transcript.map { "\($0.speaker): \($0.text)" }.joined(separator: "\n")
    }

    /// Lines containing `query` (case and diacritics ignored), in order.
    public func lines(matching query: String) -> [Line.ID] {
        let query = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !query.isEmpty else { return [] }
        return transcript.filter { $0.text.range(of: query, options: Self.searchOptions) != nil }.map(\.id)
    }

    /// How often `query` occurs in the summary (case and diacritics ignored).
    public func summaryMatches(_ query: String) -> Int {
        let query = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !query.isEmpty else { return 0 }
        var count = 0
        var rest = summary[...]
        while let range = rest.range(of: query, options: Self.searchOptions) {
            count += 1
            rest = rest[range.upperBound...]
        }
        return count
    }

    static let searchOptions: String.CompareOptions = [.caseInsensitive, .diacriticInsensitive]

    /// The line playing at `seconds` (start inclusive, end exclusive), `nil` in silence.
    public func line(playingAt seconds: TimeInterval) -> Line? {
        transcript.last { $0.start <= seconds && seconds < max($0.end, $0.start + 0.5) }
    }

    /// Where a following transcript scrolls at `seconds`: the line playing, else the next one
    /// (the last one past the end).
    public func lineToFollow(at seconds: TimeInterval) -> Line? {
        line(playingAt: seconds) ?? transcript.first { $0.start > seconds } ?? transcript.last
    }

    /// The recording's speech as `count` levels in 0...1 (how much of each slice someone spoke),
    /// for the player's waveform. Spans `0` to `end` (the last line's end when `nil`).
    public func speechLevels(_ count: Int, end: TimeInterval? = nil) -> [Double] {
        guard count > 0 else { return [] }
        guard !transcript.isEmpty else { return Array(repeating: 0, count: count) }
        let span = end ?? transcript.map(\.end).max() ?? 0
        guard span > 0 else { return Array(repeating: 1, count: count) }
        let slice = span / Double(count)
        var levels = Array(repeating: 0.0, count: count)
        for line in transcript {
            var index = min(max(Int(line.start / slice), 0), count - 1)
            while index < count, Double(index) * slice < line.end {
                let overlap = min(line.end, Double(index + 1) * slice) - max(line.start, Double(index) * slice)
                if overlap > 0 { levels[index] += overlap / slice }
                index += 1
            }
        }
        return levels.map { min(max($0, 0), 1) }
    }
}
